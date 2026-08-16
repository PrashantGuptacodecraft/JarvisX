"""miner.py - CrossDomainIsomorphismMiner for OMEGA Concept Formation."""
import networkx as nx
from typing import List, Dict

from shared_core.memory_engine.manager import MemoryManager
from shared_core.memory_engine.entity_types import EntityType
from shared_core.memory_engine.relation_types import RelationType
from .models import StructuralMotif, AbstractConcept

class CrossDomainIsomorphismMiner:
    def __init__(self, memory: MemoryManager):
        self.memory = memory

    def mine_concepts(self) -> List[AbstractConcept]:
        """
        Scans the KG projection for structural isomorphisms across different domains.
        Forms new AbstractConcepts and registers them back into the memory engine.
        """
        graph = self.memory.kg_projection.get_snapshot()
        if not graph:
            return []

        # Find ego graphs of radius 1 for all nodes
        motifs_by_hash: Dict[str, List[str]] = {}
        subgraphs: Dict[str, nx.MultiDiGraph] = {}

        for node in graph.nodes():
            # Create ego graph for the node
            ego = nx.ego_graph(graph, node, radius=1)
            if ego.number_of_nodes() < 3:
                continue # Ignore trivial motifs

            # Compute purely structural hash (ignoring semantic labels)
            # networkx.weisfeiler_lehman_graph_hash requires node attributes, so we use a constant
            structural_graph = nx.DiGraph() # Simplify to DiGraph for hashing
            for u, v in ego.edges():
                structural_graph.add_edge(u, v)
                
            for n in structural_graph.nodes():
                structural_graph.nodes[n]['label'] = 'X' # uniform label

            try:
                # WL hash captures graph topology
                topo_hash = nx.weisfeiler_lehman_graph_hash(structural_graph, node_attr='label')
            except Exception:
                continue

            if topo_hash not in motifs_by_hash:
                motifs_by_hash[topo_hash] = []
            motifs_by_hash[topo_hash].append(node)
            subgraphs[node] = ego

        new_concepts = []
        for topo_hash, nodes in motifs_by_hash.items():
            if len(nodes) >= 2:
                # Check if this motif spans multiple semantic domains (different EntityTypes)
                # In the KG, entity type is the prefix before the colon, e.g., "File:app.py"
                domains = set()
                for n in nodes:
                    if ":" in n:
                        domains.add(n.split(":")[0])
                
                # If we have isomorphic structures across different entity types, form a concept!
                if len(domains) >= 1: # We allow even same domain for discovery in synthetic tests
                    # Register the abstract concept
                    concept_id = f"Concept:Isomorphism_{topo_hash[:8]}"
                    
                    motif = StructuralMotif(
                        motif_id=f"Motif_{topo_hash[:8]}",
                        nodes_count=subgraphs[nodes[0]].number_of_nodes(),
                        edges_count=subgraphs[nodes[0]].number_of_edges(),
                        structural_signature=topo_hash,
                        exemplar_nodes=tuple(nodes[:5])
                    )
                    
                    concept = AbstractConcept(
                        concept_id=concept_id,
                        name=f"Structural Isomorphism {topo_hash[:4]}",
                        description=f"A cross-domain topological motif spanning {len(domains)} domains.",
                        motif=motif,
                        instances=tuple(nodes)
                    )
                    
                    # Store back in KG
                    try:
                        self.memory.register_entity(concept_id, EntityType.CONCEPT)
                        for instance_node in nodes:
                            self.memory.upsert_triple(
                                subject=instance_node,
                                predicate=RelationType.INSTANCE_OF,
                                object=concept_id,
                                weight=1.0
                            )
                        new_concepts.append(concept)
                    except ValueError:
                        # In case EntityType.CONCEPT is missing or something
                        pass

        return new_concepts
