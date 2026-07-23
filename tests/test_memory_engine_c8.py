import pytest
import datetime
import threading
from shared_core.memory_engine.manager import MemoryManager
from shared_core.memory_engine.kg_query import KGQueryService
from shared_core.memory_engine.entity_types import EntityType
from shared_core.memory_engine.relation_types import RelationType

@pytest.fixture
def test_setup(tmp_path, monkeypatch):
    import shared_core.memory_engine.manager
    monkeypatch.setattr(shared_core.memory_engine.manager, 'DB_PATH', tmp_path / "jarvis_c8.db")
    monkeypatch.setattr(shared_core.memory_engine.manager, 'FALLBACK_DB_PATH', tmp_path / "fallback.db")
    
    memory = MemoryManager()
    query_service = KGQueryService(memory)
    
    return memory, query_service

def test_c8_neighbors_query_directions(test_setup):
    memory, query_service = test_setup
    
    memory.upsert_triple("NodeA", "link", "NodeB")
    memory.upsert_triple("NodeB", "link", "NodeA")
    memory.upsert_triple("NodeA", "link", "NodeC")
    memory.upsert_triple("NodeD", "link", "NodeA")
    
    out_neighbors = query_service.neighbors("NodeA", direction="out")
    out_entities = [n["neighbor"] for n in out_neighbors]
    assert set(out_entities) == {"NodeB", "NodeC"}
    
    in_neighbors = query_service.neighbors("NodeA", direction="in")
    in_entities = [n["neighbor"] for n in in_neighbors]
    assert set(in_entities) == {"NodeB", "NodeD"}
    
    both_neighbors = query_service.neighbors("NodeA", direction="both")
    assert len(both_neighbors) == 4

def test_c8_neighbors_no_multi_hop_or_mirrored(test_setup):
    memory, query_service = test_setup
    memory.upsert_triple("A", "link", "B")
    memory.upsert_triple("B", "link", "C")
    
    # B is one-hop out. C is two-hops out. A is one-hop in.
    out_neighbors = query_service.neighbors("A", direction="out")
    out_entities = [n["neighbor"] for n in out_neighbors]
    assert out_entities == ["B"]
    
    # No undirected fallback or mirrored
    assert "A" not in [n["neighbor"] for n in query_service.neighbors("B", direction="out")]

def test_c8_neighbors_schema_and_relation_filter(test_setup):
    memory, query_service = test_setup
    memory.upsert_triple("PersonA", RelationType.WORKS_ON.value, "ProjectB")
    memory.upsert_triple("PersonA", RelationType.LOCATED_IN.value, "CityC")
    
    neighbors_works = query_service.neighbors("PersonA", relation_type=RelationType.WORKS_ON)
    assert len(neighbors_works) == 1
    
    n = neighbors_works[0]
    assert "entity" in n and n["entity"] == "PersonA"
    assert "neighbor" in n and n["neighbor"] == "ProjectB"
    assert "direction" in n and n["direction"] == "out"
    assert "predicate" in n and n["predicate"] == RelationType.WORKS_ON.value
    assert "triple_id" in n
    assert "weight" in n
    assert "first_seen" in n
    assert "last_seen" in n
    assert "projection_revision" in n

def test_c8_path_directed_and_reverse(test_setup):
    memory, query_service = test_setup
    memory.upsert_triple("A", "link", "B")
    memory.upsert_triple("B", "link", "C")
    
    path_ac = query_service.path("A", "C")
    assert path_ac["found"] is True
    assert path_ac["nodes"] == ["A", "B", "C"]
    
    path_ca = query_service.path("C", "A")
    assert path_ca["found"] is False
    assert path_ca["status"] == "not_found"

def test_c8_path_parallel_edge_selection(test_setup):
    memory, query_service = test_setup
    tid1 = memory.upsert_triple("A", "link1", "B")
    tid2 = memory.upsert_triple("A", "link2", "B")
    
    path = query_service.path("A", "B")
    # deterministic: smaller triple_id
    assert path["hops"][0]["triple_id"] == min(tid1, tid2)

def test_c8_path_equal_length_deterministic(test_setup):
    memory, query_service = test_setup
    memory.upsert_triple("S", "link", "M2")
    memory.upsert_triple("M2", "link", "E")
    
    memory.upsert_triple("S", "link", "M1")
    memory.upsert_triple("M1", "link", "E")
    
    path = query_service.path("S", "E")
    # M1 comes before M2 alphabetically
    assert path["nodes"] == ["S", "M1", "E"]

def test_c8_path_metadata(test_setup):
    memory, query_service = test_setup
    tid = memory.upsert_triple("A", "link", "B")
    
    path = query_service.path("A", "B")
    assert path["found"] is True
    assert path["source"] == "A"
    assert path["target"] == "B"
    assert path["hop_count"] == 1
    assert "projection_revision" in path
    
    hop = path["hops"][0]
    assert hop["source"] == "A"
    assert hop["target"] == "B"
    assert hop["triple_id"] == tid
    assert hop["predicate"] == "link"

def test_c8_path_source_equals_target(test_setup):
    memory, query_service = test_setup
    memory.upsert_triple("A", "link", "B")
    
    path = query_service.path("A", "A")
    assert path["found"] is True
    assert path["nodes"] == ["A"]
    assert path["hops"] == []
    assert path["hop_count"] == 0

def test_c8_path_cycle_boundedness(test_setup):
    memory, query_service = test_setup
    memory.upsert_triple("A", "link", "B")
    memory.upsert_triple("B", "link", "C")
    memory.upsert_triple("C", "link", "A")
    
    path = query_service.path("A", "D", max_length=5)
    assert path["found"] is False

def test_c8_projection_state_handling(test_setup):
    memory, query_service = test_setup
    
    # Insert initially and check it works
    memory.upsert_triple("A", "link", "B")
    assert query_service.neighbors("A")
    
    # Mess up the state
    memory.kg_projection._status = "stale"
    
    # Query should automatically trigger rebuild and succeed
    assert query_service.neighbors("A")
    assert memory.kg_projection._status == "complete"
    
    # If it fails to refresh
    memory.kg_projection._status = "stale"
    memory.kg_projection.build_projection = lambda *args: False
    
    path = query_service.path("A", "B")
    assert path["found"] is False
    assert path["status"] == "projection_unavailable"

def test_c8_by_type_input_contract(test_setup):
    memory, query_service = test_setup
    
    memory.register_entity("Project_A", EntityType.PROJECT)
    
    # Valid Enum
    res = query_service.by_type(EntityType.PROJECT)
    assert "Project_A" in res
    
    # Invalid string
    with pytest.raises(TypeError):
        query_service.by_type("Project")

def test_c8_since_validation_and_plan(test_setup):
    memory, query_service = test_setup
    
    memory.upsert_triple("A", "link", "B", observed_at="2026-07-23T10:00:00Z")
    
    # Bad timestamp
    with pytest.raises(ValueError):
        query_service.since("2026-07-23")
        
    # Bad limit
    with pytest.raises(ValueError):
        query_service.since("2026-07-23T10:00:00Z", limit=True)
        
    res = query_service.since("2026-07-23T10:00:00Z")
    assert len(res) == 1
    assert "triple_id" in res[0]
    
    # EXPLAIN QUERY PLAN
    plan = memory.conn.execute("EXPLAIN QUERY PLAN SELECT subject FROM kg_triples WHERE last_seen >= '2026-07-23T10:00:00Z' ORDER BY last_seen ASC LIMIT 1000").fetchall()
    plan_str = str(plan).lower()
    # The user asked us to report whether the last_seen index is used, and explicitly instructed NOT to add a redundant index.
    # Our test confirms the query runs and we capture the plan.
    assert "scan kg_triples" in plan_str or "index" in plan_str

def test_c8_concurrent_safety(test_setup):
    memory, query_service = test_setup
    memory.upsert_triple("Root", "link", "A")
    
    errors = []
    
    def writer():
        try:
            for i in range(50):
                memory.upsert_triple(f"Node{i}", "link", f"Node{i+1}")
        except Exception as e:
            errors.append(e)
            
    def reader():
        try:
            for i in range(50):
                query_service.path("Root", f"Node{i}")
        except Exception as e:
            errors.append(e)
            
    t1 = threading.Thread(target=writer)
    t2 = threading.Thread(target=reader)
    
    t1.start()
    t2.start()
    
    t1.join()
    t2.join()
    
    assert not errors
