import pytest
import datetime
from typing import Dict, Any

from shared_core.memory_engine.manager import MemoryManager
from shared_core.memory_engine.kg_query import KGQueryService
from shared_core.memory_engine.preference_learning import PreferenceLearningJob
from shared_core.memory_engine.consolidation import ConsolidationJob
from shared_core.memory_engine.execution_predicates import ExecutionPredicate

@pytest.fixture
def test_setup(tmp_path, monkeypatch):
    import shared_core.memory_engine.manager
    monkeypatch.setattr(shared_core.memory_engine.manager, 'DB_PATH', tmp_path / "jarvis_c10.db")
    monkeypatch.setattr(shared_core.memory_engine.manager, 'FALLBACK_DB_PATH', tmp_path / "fallback.db")
    
    memory = MemoryManager()
    query_service = KGQueryService(memory)
    consolidation_job = ConsolidationJob(memory, query_service)
    preference_job = PreferenceLearningJob(memory, query_service)
    
    return memory, query_service, consolidation_job, preference_job

def test_c10_preference_learning(test_setup):
    memory, query_service, c_job, p_job = test_setup
    
    # 1. No habits, no preferences
    res = p_job.run_once()
    assert res["status"] == "success"
    assert res["scanned_habits"] == 0
    assert res["inferred_preferences"] == 0
    
    # 2. Seed events to trigger C9
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
            
    # Need 3 for a habit
    add_event("event:action:c10:1", "User", "edit_code", "success", ["file.py"], time_offset=-10)
    add_event("event:action:c10:2", "User", "edit_code", "success", ["file.py"], time_offset=-9)
    add_event("event:action:c10:3", "User", "edit_code", "success", ["file.py"], time_offset=-8)
    
    # Another habit
    add_event("event:action:c10:4", "User", "run_test", "success", ["pytest"], time_offset=-7)
    add_event("event:action:c10:5", "User", "run_test", "success", ["pytest"], time_offset=-6)
    add_event("event:action:c10:6", "User", "run_test", "success", ["pytest"], time_offset=-5)
    
    # Trigger C9 consolidation
    c_res = c_job.run_once()
    print("C_RES:", c_res)
    assert c_res["promoted_pattern_count"] == 2
    
    # 3. Trigger C10 preference learning
    p_res = p_job.run_once()
    assert p_res["status"] == "success"
    assert p_res["scanned_habits"] == 2
    assert p_res["inferred_preferences"] == 2
    
    # 4. Verify preference entries in relational DB
    entries = memory.get_profile_entries(category="learned_preference")
    assert len(entries) == 2
    keys = [e["key"] for e in entries]
    
    # keys are expected to be prefixed with habit_<action>_<hash>
    assert any("habit_edit_code_" in k for k in keys)
    assert any("habit_run_test_" in k for k in keys)
    
    # 5. Idempotent rerun
    p_res2 = p_job.run_once()
    assert p_res2["inferred_preferences"] == 2 # it's an upsert on existing keys
    
    # Verify exact count in DB hasn't duplicated
    entries2 = memory.get_profile_entries(category="learned_preference")
    assert len(entries2) == 2

def test_c10_scheduler_lifecycle():
    from main import build_jarvis
    import queue
    cq = queue.Queue()
    core, listener, speaker, memory, cq_out, gesture_ctrl = build_jarvis(gui=None, command_queue=cq, headless=True)
    
    # Verify registered
    scheduler = core.brain.scheduler
    assert scheduler is not None
    tasks = [t for t in scheduler._tasks.values() if t.id == "preference_learning_job"]
    assert len(tasks) == 1
    task = tasks[0]
    
    # Cadence configurable and default 24h
    assert task.interval == 86400.0
    
    scheduler.stop()
    if 'code_analyzer' in core.brain.tools:
        core.brain.tools['code_analyzer'].stop()
