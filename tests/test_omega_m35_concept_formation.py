"""test_omega_m35_concept_formation.py - Acceptance tests for M35 Abstract Concept Formation."""
import pytest
import time
import os
import networkx as nx

from shared_core.memory_engine.manager import MemoryManager
from shared_core.memory_engine.entity_types import EntityType
from shared_core.memory_engine.relation_types import RelationType
from omega_core.concept_formation.miner import CrossDomainIsomorphismMiner
from omega_core.concept_formation.models import AbstractConcept

@pytest.fixture
def memory_manager(tmp_path, monkeypatch):
    db_path = tmp_path / "jarvis.db"
    
    import shared_core.memory_engine.manager
    monkeypatch.setattr(shared_core.memory_engine.manager, 'DB_PATH', db_path)
    monkeypatch.setattr(shared_core.memory_engine.manager, 'FALLBACK_DB_PATH', tmp_path / "fallback.db")
    
    mgr = MemoryManager()
    yield mgr
    mgr.conn.close()

def test_cross_domain_isomorphism_detection(memory_manager):
    # Setup synthetic graphs in two different domains.
    # Domain 1: Code dependencies (File entities)
    # A -> B -> C -> A (a cycle)
    memory_manager.register_entity("File:A.py", EntityType.FILE)
    memory_manager.register_entity("File:B.py", EntityType.FILE)
    memory_manager.register_entity("File:C.py", EntityType.FILE)
    
    memory_manager.upsert_triple("File:A.py", RelationType.DEPENDS_ON, "File:B.py", 1.0)
    memory_manager.upsert_triple("File:B.py", RelationType.DEPENDS_ON, "File:C.py", 1.0)
    memory_manager.upsert_triple("File:C.py", RelationType.DEPENDS_ON, "File:A.py", 1.0)
    
    # Domain 2: Workflow execution (Event entities)
    # X -> Y -> Z -> X (also a cycle of 3)
    memory_manager.register_entity("Event:TaskX", EntityType.EVENT)
    memory_manager.register_entity("Event:TaskY", EntityType.EVENT)
    memory_manager.register_entity("Event:TaskZ", EntityType.EVENT)
    
    memory_manager.upsert_triple("Event:TaskX", RelationType.PRECEDES, "Event:TaskY", 1.0)
    memory_manager.upsert_triple("Event:TaskY", RelationType.PRECEDES, "Event:TaskZ", 1.0)
    memory_manager.upsert_triple("Event:TaskZ", RelationType.PRECEDES, "Event:TaskX", 1.0)
    
    # Load projection so the miner can read it
    # MemoryManager updates projection incrementally outside tests, but tests might need slight wait or explicit trigger
    # But wait, upsert_triple triggers sync_edge! So it should be immediate.
    # We must ensure the initial graph load is complete.
    graph = memory_manager.kg_projection.get_snapshot()
    assert graph is not None, "Projection should be active"
    assert graph.number_of_edges() == 12
    
    # Run miner
    miner = CrossDomainIsomorphismMiner(memory_manager)
    concepts = miner.mine_concepts()
    
    # We should have found an AbstractConcept bridging the two domains
    assert len(concepts) > 0, "Miner should detect the isomorphic cycles"
    
    found_cross_domain = False
    for concept in concepts:
        # Check if concept covers both File and Event
        has_file = any(i.startswith("File:") for i in concept.instances)
        has_event = any(i.startswith("Event:") for i in concept.instances)
        if has_file and has_event:
            found_cross_domain = True
            break
            
    assert found_cross_domain, "A cross-domain concept (File + Event) must be formed"
    
    # Verify the concept was written to KG
    concept_id = concepts[0].concept_id
    assert memory_manager.kg_projection.get_snapshot().has_node(concept_id)
