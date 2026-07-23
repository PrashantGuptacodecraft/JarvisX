import logging
import networkx as nx
from typing import List, Dict, Any, Optional
from shared_core.memory_engine.relation_types import RelationType
from shared_core.memory_engine.entity_types import EntityType

log = logging.getLogger("memory.query")

class KGQueryService:
    """
    Separated query algorithms for the Knowledge Graph.
    Uses GraphProjection for topology queries and MemoryManager for relational/temporal queries.
    """
    
    def __init__(self, memory_manager):
        self.memory = memory_manager
        
    def _ensure_projection(self) -> Optional[Any]:
        status = self.memory.kg_projection.status()
        
        if status.get("stale"):
            # Attempt one bounded refresh
            self.memory._load_kg_projection()
            status = self.memory.kg_projection.status()
            
        if not status.get("available") or not status.get("complete") or status.get("stale"):
            return None
            
        return self.memory.kg_projection.get_snapshot()

    def neighbors(self, entity: str, direction: str = "both", relation_type: RelationType | None = None, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Retrieves immediate, one-hop neighbors of the given entity.
        direction: 'out' (successors), 'in' (predecessors), or 'both'.
        relation_type: Optional RelationType enum or string to filter by predicate.
        Returns a list of dicts: {'entity': str, 'predicate': str, 'direction': str, 'weight': float, ...}
        """
        if not entity:
            return []
            
        graph = self._ensure_projection()
        if not graph:
            log.warning("Graph projection unavailable for neighbors query")
            return []
            
        if not graph.has_node(entity):
            return []
            
        results = []
        rel_val = relation_type.value if hasattr(relation_type, "value") else relation_type
        proj_rev = getattr(self.memory.kg_projection, "_projected_revision", None)
            
        try:
            if direction in ("out", "both"):
                for u, v, key, data in graph.out_edges(entity, keys=True, data=True):
                    pred = data.get("predicate")
                    if rel_val and pred != rel_val:
                        continue
                    results.append({
                        "entity": entity,
                        "neighbor": v,
                        "predicate": pred,
                        "direction": "out",
                        "triple_id": data.get("triple_id"),
                        "weight": data.get("weight", 1.0),
                        "first_seen": data.get("first_seen"),
                        "last_seen": data.get("last_seen"),
                        "projection_revision": proj_rev
                    })
                    
            if direction in ("in", "both"):
                for u, v, key, data in graph.in_edges(entity, keys=True, data=True):
                    pred = data.get("predicate")
                    if rel_val and pred != rel_val:
                        continue
                    results.append({
                        "entity": entity,
                        "neighbor": u,
                        "predicate": pred,
                        "direction": "in",
                        "triple_id": data.get("triple_id"),
                        "weight": data.get("weight", 1.0),
                        "first_seen": data.get("first_seen"),
                        "last_seen": data.get("last_seen"),
                        "projection_revision": proj_rev
                    })
                    
            # Sort to ensure determinism
            results.sort(key=lambda x: (x["neighbor"], x["predicate"], x["direction"], x["triple_id"] or 0))
            
            return results[:limit]
        except Exception as e:
            log.error(f"Error querying neighbors for {entity}: {e}")
            return []

    def path(self, source: str, target: str, max_length: int = 5) -> Dict[str, Any]:
        """
        Finds the shortest directed path between source and target entities.
        Returns a JSON-serializable dict.
        """
        if type(max_length) is bool or not isinstance(max_length, int) or max_length < 0:
            raise ValueError("max_length must be a positive integer")
            
        # Cap according to centralized limits
        if max_length > 20:
            max_length = 20
            
        if not source or not target:
            return {"found": False, "source": source, "target": target, "status": "invalid_input"}
            
        graph = self._ensure_projection()
        proj_rev = getattr(self.memory.kg_projection, "_projected_revision", None)
        
        if not graph:
            return {"found": False, "source": source, "target": target, "status": "projection_unavailable"}
            
        if not graph.has_node(source) or not graph.has_node(target):
            return {"found": False, "source": source, "target": target, "status": "not_found"}
            
        if source == target:
            return {
                "found": True,
                "source": source,
                "target": target,
                "nodes": [source],
                "hops": [],
                "hop_count": 0,
                "projection_revision": proj_rev,
                "status": "success"
            }
            
        try:
            # Bounded deterministic BFS
            queue = [[source]]
            visited = {source}
            found_path = None
            
            while queue:
                current_path = queue.pop(0)
                current_node = current_path[-1]
                
                if current_node == target:
                    found_path = current_path
                    break
                    
                if len(current_path) - 1 >= max_length:
                    continue
                    
                # Get outgoing edges to explore
                edges = []
                for u, v, key, data in graph.out_edges(current_node, keys=True, data=True):
                    if v not in visited:
                        edges.append((v, data.get("predicate", ""), data.get("triple_id", float('inf'))))
                        
                # Sort for deterministic ordering: 1. next node 2. predicate 3. triple_id
                edges.sort(key=lambda x: (x[0], x[1], x[2]))
                
                seen_next = set()
                for v, pred, tid in edges:
                    if v not in seen_next:
                        seen_next.add(v)
                        queue.append(current_path + [v])
                        visited.add(v)
                        
            if not found_path:
                return {"found": False, "source": source, "target": target, "status": "not_found"}
                
            # Construct hops deterministically picking smallest triple_id for parallel edges
            hops = []
            for i in range(len(found_path) - 1):
                u = found_path[i]
                v = found_path[i+1]
                edge_data = graph.get_edge_data(u, v)
                
                best_edge = None
                best_triple_id = float('inf')
                
                for key, data in edge_data.items():
                    tid = data.get("triple_id", float('inf'))
                    if tid < best_triple_id:
                        best_triple_id = tid
                        best_edge = data
                        
                hops.append({
                    "source": u,
                    "target": v,
                    "triple_id": best_edge.get("triple_id"),
                    "predicate": best_edge.get("predicate"),
                    "weight": best_edge.get("weight")
                })
                
            return {
                "found": True,
                "source": source,
                "target": target,
                "nodes": found_path,
                "hops": hops,
                "hop_count": len(hops),
                "projection_revision": proj_rev,
                "status": "success"
            }
                
        except Exception as e:
            log.error(f"Error querying path from {source} to {target}: {e}")
            return {"found": False, "source": source, "target": target, "status": "error"}

    def by_type(self, entity_type: Any, limit: int = 100) -> List[str]:
        """
        Retrieves all entity IDs that have the given type.
        """
        if not isinstance(entity_type, EntityType):
            raise TypeError("entity_type must be an instance of EntityType Enum")
            
        return self.memory.get_entities_by_type(entity_type, limit=limit)

    def since(self, timestamp: str, limit: int = 1000) -> List[Dict[str, Any]]:
        """
        Retrieves execution events or arbitrary edges observed since a given timestamp.
        Uses SQLite for temporal lookups.
        """
        import datetime
        
        if type(limit) is bool or not isinstance(limit, int):
            raise ValueError("limit must be an integer")
            
        try:
            if not timestamp.endswith('Z') and not timestamp.endswith('+00:00'):
                raise ValueError("timestamp must be canonical UTC")
            dt = datetime.datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            if dt.tzinfo is None:
                raise ValueError("timestamp must be canonical UTC")
        except Exception:
            raise ValueError("Invalid timestamp format")
            
        with self.memory._lock:
            cursor = self.memory.conn.cursor()
            rows = cursor.execute(
                "SELECT subject, predicate, object, weight, first_seen, last_seen, id FROM kg_triples WHERE last_seen >= ? ORDER BY last_seen ASC LIMIT ?",
                (timestamp, limit)
            ).fetchall()
            
            return [
                {
                    "subject": row[0],
                    "predicate": row[1],
                    "object": row[2],
                    "weight": row[3],
                    "first_seen": row[4],
                    "last_seen": row[5],
                    "triple_id": row[6]
                }
                for row in rows
            ]
