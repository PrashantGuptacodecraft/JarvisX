import pytest
import datetime
from typing import Dict, Any

from shared_core.memory_engine.manager import MemoryManager
from shared_core.memory_engine.kg_query import KGQueryService
from shared_core.memory_engine.consolidation import ConsolidationJob
from shared_core.memory_engine.execution_predicates import ExecutionPredicate

@pytest.fixture
def test_setup(tmp_path, monkeypatch):
    import shared_core.memory_engine.manager
    monkeypatch.setattr(shared_core.memory_engine.manager, 'DB_PATH', tmp_path / "jarvis_c9.db")
    monkeypatch.setattr(shared_core.memory_engine.manager, 'FALLBACK_DB_PATH', tmp_path / "fallback.db")
    
    memory = MemoryManager()
    query_service = KGQueryService(memory)
    consolidation_job = ConsolidationJob(memory, query_service)
    
    return memory, query_service, consolidation_job

def test_c9_consolidation_probes(test_setup):
    memory, query_service, job = test_setup
    
    # 1. Manual run_once works (Non-overdue startup does not run inherently - we just call it)
    res = job.run_once()
    assert res["status"] == "success"
    assert res["scanned_event_count"] == 0
    
    # Let's seed events!
    def add_event(event_id, actor, action, outcome, targets, source="test", time_offset=0):
        t = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=time_offset)
        ts = t.isoformat()
        memory.upsert_triple(event_id, "type", "literal:entity_type:event", observed_at=ts)
        memory.upsert_triple(event_id, ExecutionPredicate.PERFORMED_BY, actor, observed_at=ts)
        memory.upsert_triple(event_id, ExecutionPredicate.ACTION, action, observed_at=ts)
        memory.upsert_triple(event_id, ExecutionPredicate.OUTCOME, f"literal:outcome:{outcome}", observed_at=ts)
        memory.upsert_triple(event_id, ExecutionPredicate.SOURCE, source, observed_at=ts)
        for t in targets:
            memory.upsert_triple(event_id, ExecutionPredicate.TARGET, t, observed_at=ts)
            
    # Two-event below-threshold probe
    add_event("event:action:1", "User", "jump", "success", ["box"], time_offset=-10)
    add_event("event:action:2", "User", "jump", "success", ["box"], time_offset=-9)
    
    res = job.run_once()
    assert res["status"] == "success"
    assert res["valid_event_count"] == 2
    assert res["promoted_pattern_count"] == 0
    assert res["skipped_pattern_count"] == 1
    
    # Three-event promotion probe
    add_event("event:action:3", "User", "jump", "success", ["box"], time_offset=-8)
    res = job.run_once()
    assert res["promoted_pattern_count"] == 1
    
    # Different actor, action, outcome, targets signatures
    # 4 distinct signatures
    add_event("event:action:4", "Agent", "jump", "success", ["box"], time_offset=-7)
    add_event("event:action:5", "Agent", "jump", "success", ["box"], time_offset=-6)
    add_event("event:action:6", "Agent", "jump", "success", ["box"], time_offset=-5)
    
    add_event("event:action:7", "User", "run", "success", ["box"], time_offset=-4)
    add_event("event:action:8", "User", "run", "success", ["box"], time_offset=-3)
    add_event("event:action:9", "User", "run", "success", ["box"], time_offset=-2)
    
    add_event("event:action:10", "User", "jump", "failure", ["box"], time_offset=-1)
    add_event("event:action:11", "User", "jump", "failure", ["box"], time_offset=0)
    add_event("event:action:12", "User", "jump", "failure", ["box"], time_offset=1)
    
    add_event("event:action:13", "User", "jump", "success", ["ball"], time_offset=2)
    add_event("event:action:14", "User", "jump", "success", ["ball"], time_offset=3)
    add_event("event:action:15", "User", "jump", "success", ["ball"], time_offset=4)
    
    res = job.run_once()
    assert res["promoted_pattern_count"] == 4
    
    # Verify Habit entity properties
    from shared_core.memory_engine.entity_types import EntityType
    habits = memory.get_entities_by_type(EntityType.HABIT, limit=100)
    assert len(habits) == 5
    
    for h in habits:
        triples = memory.query_triples(subject=h)
        preds = [t["predicate"] for t in triples]
        assert "pattern_actor" in preds
        assert "pattern_action" in preds
        assert "pattern_outcome" in preds
        assert "derived_from" in preds
        
    # Idempotent reruns
    res = job.run_once()
    assert res["promoted_pattern_count"] == 0
    assert res["existing_pattern_count"] == 5
    
    # Atomic rollback probe
    # Simulate DB error during promote
    add_event("event:action:16", "User", "fly", "success", ["sky"], time_offset=5)
    add_event("event:action:17", "User", "fly", "success", ["sky"], time_offset=6)
    add_event("event:action:18", "User", "fly", "success", ["sky"], time_offset=7)
    
    def failing_upsert(*args, **kwargs):
        raise RuntimeError("Injected DB failure")
    
    original_upsert = memory._upsert_triple_cursor
    memory._upsert_triple_cursor = failing_upsert
    
    res = job.run_once()
    assert res["promoted_pattern_count"] == 0
    
    memory._upsert_triple_cursor = original_upsert
    res = job.run_once()
    assert res["promoted_pattern_count"] == 1
    
    # Evidence bounds
    add_event("event:action:19", "User", "fly", "success", ["sky"], time_offset=8)
    add_event("event:action:20", "User", "fly", "success", ["sky"], time_offset=9)
    job.run_once()
    
    # Verify evidence bounded to 3
    triples = memory.query_triples(predicate="derived_from")
    fly_habit = [t["subject"] for t in memory.query_triples(predicate="pattern_action", object="literal:action:fly")][0]
    ev_count = len(memory.query_triples(subject=fly_habit, predicate="derived_from"))
    assert ev_count <= 3

    # Overlapping run probe
    job._lock.acquire()
    res = job.run_once()
    assert res["status"] == "already_running"
    job._lock.release()

    # Result/status is JSON serializable
    import json
    json.dumps(res)
    
def test_scheduler_lifecycle():
    from main import build_jarvis
    import queue
    cq = queue.Queue()
    core, listener, speaker, memory, cq_out, gesture_ctrl = build_jarvis(gui=None, command_queue=cq, headless=True)
    
    # Verify registered
    scheduler = core.brain.scheduler
    assert scheduler is not None
    tasks = [t for t in scheduler._tasks.values() if t.id == "consolidation_job"]
    assert len(tasks) == 1
    task = tasks[0]
    
    # Cadence configurable and default 24h
    assert task.interval == 86400.0
    
    assert scheduler.health()["running"] is True
    
    scheduler.stop()
    if 'code_analyzer' in core.brain.tools:
        core.brain.tools['code_analyzer'].stop()
    assert scheduler.health()["running"] is False
