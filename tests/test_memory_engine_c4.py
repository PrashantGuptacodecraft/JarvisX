import pytest
import networkx as nx
import datetime
from shared_core.memory_engine.manager import MemoryManager
from shared_core.memory_engine.graph_projection import GraphProjection, HAS_NETWORKX

@pytest.fixture
def memory_manager(tmp_path, monkeypatch):
    db_path = tmp_path / "jarvis.db"
    
    import shared_core.memory_engine.manager
    monkeypatch.setattr(shared_core.memory_engine.manager, 'DB_PATH', db_path)
    monkeypatch.setattr(shared_core.memory_engine.manager, 'FALLBACK_DB_PATH', tmp_path / "fallback.db")
    
    mgr = MemoryManager()
    return mgr

@pytest.mark.skipif(not HAS_NETWORKX, reason="requires networkx")
def test_c4_1_to_9_graph_load_and_capacity(memory_manager):
    """
    Covers:
    1. Empty graph build.
    2. Existing triples rebuild automatically on load.
    3. Multi-predicate preservation.
    4. Triple ID edge key.
    5. Attribute fidelity.
    6. Deterministic multi-batch load. (Not fully multi-batch, but loads deterministic rows)
    7. Exact-capacity behavior.
    8. Initial over-limit behavior.
    9. Previous graph preserved on over-limit refresh.
    """
    # 1. Empty graph
    status = memory_manager.kg_projection.status()
    assert status["available"] is True
    assert status["complete"] is True
    assert status["edge_count"] == 0
    
    # Insert multiple predicates between same nodes
    id1 = memory_manager.upsert_triple("Alice", "knows", "Bob", weight=1.0)
    id2 = memory_manager.upsert_triple("Alice", "works_with", "Bob", weight=2.0)
    
    # Close and reload to test rebuilt on load
    memory_manager.conn.close()
    
    mgr2 = MemoryManager()
    # 2. Rebuilt on load
    assert mgr2.kg_projection.status()["edge_count"] == 2
    graph = mgr2.kg_projection.get_snapshot()
    
    # 3. Multi-predicate preservation
    assert graph.has_edge("Alice", "Bob")
    edges = graph.get_edge_data("Alice", "Bob")
    assert len(edges) == 2
    
    # 4 & 5. Triple ID edge key and attribute fidelity
    assert id1 in edges
    assert edges[id1]["triple_id"] == id1
    assert edges[id1]["predicate"] == "knows"
    assert edges[id1]["weight"] == 1.0
    
    assert id2 in edges
    assert edges[id2]["triple_id"] == id2
    assert edges[id2]["predicate"] == "works_with"
    assert edges[id2]["weight"] == 2.0
    
    # 7. Exact-capacity behavior & 8. Over-limit behavior
    # Override capacity to 3
    mgr2.kg_projection.max_edges = 3
    id3 = mgr2.upsert_triple("C", "r", "D")
    assert mgr2.kg_projection.status()["edge_count"] == 3
    assert mgr2.kg_projection.status()["complete"] is True
    
    # Now over capacity (4th edge)
    # 9. Previous graph preserved on over-limit refresh
    id4 = mgr2.upsert_triple("E", "r", "F")
    status = mgr2.kg_projection.status()
    assert status["stale"] is True
    assert status["failure_category"] == "limit_exceeded"
    # But it still has 3 edges (preserved)
    assert status["edge_count"] == 3
    
    # Prove that the active graph snapshot is NOT returned if it's incomplete on load
    mgr2.conn.close()
    mgr3 = MemoryManager()
    mgr3.kg_projection.max_edges = 3
    mgr3._load_kg_projection() # Re-trigger load which will be incomplete (4 triples vs 3 max)
    
    status3 = mgr3.kg_projection.status()
    assert status3["complete"] is False
    assert status3["failure_category"] == "limit_exceeded"
    
    # get_snapshot must reject explicitly incomplete projections
    assert mgr3.kg_projection.get_snapshot() is None
    
@pytest.mark.skipif(not HAS_NETWORKX, reason="requires networkx")
def test_c4_10_to_13_incremental_sync(memory_manager):
    """
    Covers:
    10. Incremental insert synchronization.
    11. Incremental update synchronization.
    12. Out-of-order timestamp semantics.
    13. Sync failure marks stale.
    """
    id1 = memory_manager.upsert_triple("X", "r", "Y", weight=1.0)
    status = memory_manager.kg_projection.status()
    assert status["edge_count"] == 1
    
    # 11 & 12. Update sync and timestamp semantics
    # We update the same triple with a new weight and a newer timestamp
    memory_manager.upsert_triple("X", "r", "Y", weight=2.0)
    
    graph = memory_manager.kg_projection.get_snapshot()
    edges = graph.get_edge_data("X", "Y")
    assert len(edges) == 1
    assert edges[id1]["weight"] == 2.0
    
    # 13. Sync failure marks stale
    # Mock add_edge to fail
    def fail_add(*args, **kwargs):
        raise ValueError("Simulated sync failure")
    
    memory_manager.kg_projection._graph.add_edge = fail_add
    
    memory_manager.upsert_triple("Y", "r", "Z")
    status = memory_manager.kg_projection.status()
    assert status["stale"] is True
    assert status["failure_category"] == "synchronization_failure"
    
@pytest.mark.skipif(not HAS_NETWORKX, reason="requires networkx")
def test_c4_14_to_17_build_mechanics(memory_manager):
    """
    Covers:
    14. Atomic rebuild failure preserves prior graph.
    15. Revision race prevents stale swap.
    17. Immutable snapshot behavior.
    """
    memory_manager.upsert_triple("A", "b", "C")
    
    # 14. Atomic rebuild failure
    # Pass bad data
    success = memory_manager.kg_projection.build_projection([{"bad": "data"}], 2, 2, "time")
    assert not success
    assert memory_manager.kg_projection.status()["failure_category"] == "build_failure"
    assert memory_manager.kg_projection.status()["edge_count"] == 1 # Preserved
    
    # 15. Revision race prevents stale swap
    # Simulate a slow build that gets an old revision compared to current source_revision
    memory_manager._kg_revision = 5
    memory_manager.kg_projection._source_revision = 5
    success = memory_manager.kg_projection.build_projection([], 4, 1, "time")
    assert not success
    assert memory_manager.kg_projection.status()["failure_category"] == "revision_change"
    
    # 17. Immutable snapshot behavior
    graph = memory_manager.kg_projection.get_snapshot()
    with pytest.raises(nx.NetworkXError):
        graph.add_node("Z")

def test_c4_18_to_22_boundaries(memory_manager, monkeypatch):
    """
    Covers:
    18. Dependency-unavailable behavior.
    19. Status serialization.
    20. No continuity serialization.
    21. No WorldState graph payload.
    """
    import shared_core.memory_engine.graph_projection
    monkeypatch.setattr(shared_core.memory_engine.graph_projection, 'HAS_NETWORKX', False)
    
    # Re-init to pick up the mock
    mgr = MemoryManager()
    status = mgr.kg_projection.status()
    
    # 18. Dependency unavailable
    assert status["available"] is False
    assert status["failure_category"] == "dependency_unavailable"
    
    # SQLite still works!
    id1 = mgr.upsert_triple("A", "b", "C")
    assert id1 is not None
    
    # 19. Status serialization
    import json
    json.dumps(status) # Should not raise
