import threading
from typing import Any, Dict, List, Optional
try:
    import networkx as nx
    HAS_NETWORKX = True
except ImportError:
    HAS_NETWORKX = False

class GraphProjection:
    """
    In-memory graph projection of the SQLite kg_triples store.
    Maintains a strictly bounded, read-only (from outside) snapshot
    of the relational knowledge graph.
    """
    
    def __init__(self, max_edges: int = 10000):
        if not isinstance(max_edges, int) or isinstance(max_edges, bool) or max_edges <= 0:
            raise ValueError("max_edges must be a positive integer")
            
        self.max_edges = max_edges
        self._graph = nx.MultiDiGraph() if HAS_NETWORKX else None
        self._lock = threading.RLock()
        
        self._is_built = False
        self._status = "unavailable" if not HAS_NETWORKX else "empty"
        self._edge_count = 0
        self._node_count = 0
        self._source_revision = 0
        self._projected_revision = 0
        self._loaded_at = None
        self._last_refresh_status = "pending"
        self._failure_category = "dependency_unavailable" if not HAS_NETWORKX else None

    @property
    def is_built(self) -> bool:
        with self._lock:
            return self._is_built

    def status(self) -> Dict[str, Any]:
        """Returns JSON-serializable status model."""
        with self._lock:
            return {
                "available": HAS_NETWORKX and self._is_built and self._status != "stale",
                "complete": self._status == "complete",
                "stale": self._status == "stale",
                "status": self._status,
                "edge_count": self._edge_count,
                "node_count": self._node_count,
                "source_revision": self._source_revision,
                "projected_revision": self._projected_revision,
                "loaded_at": self._loaded_at,
                "last_refresh_status": self._last_refresh_status,
                "failure_category": self._failure_category,
            }

    def build_projection(self, triples: List[dict], source_revision: int, total_store_count: int, timestamp: str) -> bool:
        """
        Atomically replaces the current graph with a new MultiDiGraph built
        from the provided triples.
        """
        if not HAS_NETWORKX:
            return False
            
        # Check capacity
        is_complete = total_store_count <= self.max_edges
        
        if not is_complete:
            # Over-limit behavior: preserve previous graph if one exists, mark incomplete/stale
            with self._lock:
                if self._is_built:
                    self._status = "stale"
                    self._last_refresh_status = "failed"
                    self._failure_category = "limit_exceeded"
                    return False
                else:
                    self._status = "incomplete"
                    self._last_refresh_status = "failed"
                    self._failure_category = "limit_exceeded"
                    return False

        # Construct temporary graph (lock-free)
        new_graph = nx.MultiDiGraph()
        
        try:
            for t in triples:
                new_graph.add_edge(
                    t["subject"],
                    t["object"],
                    key=t["id"],
                    triple_id=t["id"],
                    predicate=t["predicate"],
                    weight=t["weight"],
                    first_seen=t["first_seen"],
                    last_seen=t["last_seen"]
                )
        except Exception as e:
            with self._lock:
                self._last_refresh_status = "failed"
                self._failure_category = "build_failure"
            return False
            
        with self._lock:
            # Revision race check
            if source_revision < self._source_revision:
                self._last_refresh_status = "failed"
                self._failure_category = "revision_change"
                return False
                
            self._graph = new_graph
            self._is_built = True
            self._status = "complete"
            self._last_refresh_status = "success"
            self._failure_category = None
            self._edge_count = new_graph.number_of_edges()
            self._node_count = new_graph.number_of_nodes()
            self._projected_revision = source_revision
            self._source_revision = source_revision
            self._loaded_at = timestamp
            return True

    def sync_edge(self, triple_id: int, subject: str, predicate: str, obj: str, weight: float, first_seen: str, last_seen: str, new_revision: int) -> bool:
        """
        Incrementally synchronizes a single edge after an upsert in the DB.
        """
        if not HAS_NETWORKX:
            return False
            
        with self._lock:
            self._source_revision = new_revision
            
            if not self._is_built or self._status != "complete":
                return False
                
            if self._edge_count >= self.max_edges and not self._graph.has_edge(subject, obj, key=triple_id):
                # inserting a new unique triple at exact capacity marks the projection incomplete/stale
                self._status = "stale"
                self._last_refresh_status = "failed"
                self._failure_category = "limit_exceeded"
                return False
                
            try:
                self._graph.add_edge(
                    subject,
                    obj,
                    key=triple_id,
                    triple_id=triple_id,
                    predicate=predicate,
                    weight=weight,
                    first_seen=first_seen,
                    last_seen=last_seen
                )
                self._projected_revision = new_revision
                self._edge_count = self._graph.number_of_edges()
                self._node_count = self._graph.number_of_nodes()
                return True
            except Exception:
                self._status = "stale"
                self._last_refresh_status = "failed"
                self._failure_category = "synchronization_failure"
                return False

    def mark_stale(self, new_revision: int, category: str = "synchronization_failure") -> None:
        """Explicitly marks the projection as stale without rolling back SQLite."""
        with self._lock:
            self._source_revision = new_revision
            if self._is_built:
                self._status = "stale"
            self._last_refresh_status = "failed"
            self._failure_category = category

    def get_snapshot(self) -> Optional[Any]:
        """
        Returns a read-only frozen snapshot of the current graph.
        Returns None if the projection is incomplete, stale, or unavailable.
        """
        if not HAS_NETWORKX:
            return None
            
        with self._lock:
            if not self._is_built or self._status != "complete":
                return None
            return nx.freeze(nx.MultiDiGraph(self._graph))
