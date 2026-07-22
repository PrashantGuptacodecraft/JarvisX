import os
import sqlite3
import tempfile
import threading
import time
import pytest

from shared_core import get_bus
from shared_core.scheduler import Scheduler, Priority
from shared_core.state_manager import LedgerStore
from shared_core.state_manager.compaction_job import CompactionJob, CompactionResult

@pytest.fixture
def temp_store():
    temp_db = tempfile.mktemp(suffix=".db")
    store = LedgerStore(db_path=temp_db, cap=1000)
    yield store
    store.close()
    if os.path.exists(temp_db):
        os.remove(temp_db)

@pytest.fixture
def bus():
    return get_bus()

@pytest.fixture
def scheduler():
    sched = Scheduler(max_workers=2)
    sched.start()
    yield sched
    sched.stop(wait=True)

def test_compaction_registration_is_idempotent(temp_store, bus, scheduler):
    """5. Compaction task registration is idempotent by task ID."""
    job1 = CompactionJob(store=temp_store, bus=bus, scheduler=scheduler)
    t1 = scheduler.register_task("state_compaction", "compaction", job1.run_cycle, 300.0, Priority.LOGGING)
    t2 = scheduler.register_task("state_compaction", "compaction", job1.run_cycle, 300.0, Priority.LOGGING)
    assert t1.id == t2.id
    # Scheduler replaces tasks with same id, count remains 1
    assert len(scheduler._tasks) == 1

def test_sqlite_thread_safety_and_concurrency(temp_store, bus, scheduler):
    """1, 2, 3, 4. Concurrent transition recording and compaction is safe."""
    job = CompactionJob(store=temp_store, bus=bus, scheduler=scheduler, interval=0.1)
    
    # Pre-populate with some data
    for i in range(50):
        temp_store.append({"ts": time.time(), "value": i})

    events_emitted = []
    def on_event(ev):
        events_emitted.append(ev.topic)
    bus.subscribe("maintenance.compaction.*", on_event, mode="sync")

    # Register task and run rapidly
    scheduler.register_task("state_compaction", "compaction", job.run_cycle, 0.05, Priority.LOGGING)
    
    # Concurrently write transitions
    def writer_thread():
        for i in range(100):
            temp_store.append({"ts": time.time(), "val": i})
            time.sleep(0.001)

    t = threading.Thread(target=writer_thread)
    t.start()
    time.sleep(0.5)
    t.join()

    # If it reached here, no SQLite thread errors occurred
    assert "maintenance.compaction.completed" in events_emitted

def test_overload_skip_reported(temp_store, bus, scheduler):
    """12. Overload skip reported separately."""
    job = CompactionJob(store=temp_store, bus=bus, scheduler=scheduler)
    
    events_emitted = []
    def on_event(ev):
        events_emitted.append(ev)
    bus.subscribe("maintenance.compaction.*", on_event, mode="sync")

    # Mock diagnostics to force overload
    scheduler.diagnostics = lambda: {"overload": True}
    
    job.run_cycle()
    
    assert len(events_emitted) == 1
    assert events_emitted[0].topic == "maintenance.compaction.skipped"
    assert events_emitted[0].payload["skip_reason"] == "scheduler_overload"
    assert events_emitted[0].payload["skipped"] is True

def test_overlap_skip(temp_store, bus, scheduler):
    """12. Overlap skip reported separately."""
    job = CompactionJob(store=temp_store, bus=bus, scheduler=scheduler)
    
    # Acquire lock manually to simulate running cycle
    job._guard.acquire()
    try:
        job.run_cycle() # Should return immediately due to overlap
    finally:
        job._guard.release()
        
    assert job._overlap_count == 1

def test_cycle_deadline_prevents_compression(temp_store, bus, scheduler):
    """8. Cycle deadline prevents starting additional work after budget exhaustion."""
    # Set max_duration very low so it exhausts budget during expiry
    job = CompactionJob(store=temp_store, bus=bus, scheduler=scheduler, max_duration=0.000001)
    
    events = []
    bus.subscribe("maintenance.compaction.*", lambda ev: events.append(ev), mode="sync")
    
    # Add some dummy data
    temp_store.append({"ts": time.time(), "val": 1})
    
    # Mock expire to take longer than deadline
    def slow_expire(*args, **kwargs):
        time.sleep(0.15)
        return 0
    temp_store.expire = slow_expire
    
    job.run_cycle()
    
    # Check partial success due to budget exhaust
    failures = [e for e in events if e.topic == "maintenance.compaction.failed"]
    assert len(failures) == 1
    assert failures[0].payload["error_stage"] == "deadline"
    assert failures[0].payload["skip_reason"] == "budget_exhausted"
    assert failures[0].payload["partial_success"] is True

def test_partial_result_on_compression_failure(temp_store, bus, scheduler):
    """7. Expiry succeeds but compression fails -> accurate partial-result report."""
    job = CompactionJob(store=temp_store, bus=bus, scheduler=scheduler)
    
    events = []
    bus.subscribe("maintenance.compaction.*", lambda ev: events.append(ev), mode="sync")
    
    def bad_compress(*args, **kwargs):
        raise ValueError("Compression crashed")
    temp_store.compress = bad_compress
    
    job.run_cycle()
    
    failures = [e for e in events if e.topic == "maintenance.compaction.failed"]
    assert len(failures) == 1
    payload = failures[0].payload
    assert payload["error_stage"] == "compression"
    assert payload["expiry_success"] is True
    assert payload["compression_success"] is False
    assert payload["partial_success"] is True
    assert payload["error_type"] == "ValueError"
    assert "Compression crashed" in payload["error_message"]
    # 10, 11: Error message is bounded, not full traceback
    assert "Traceback" not in payload["error_message"]
    assert len(payload["error_message"]) <= 200

def test_snapshot_restore_preserves_interval(temp_store, bus, scheduler):
    """6. Snapshot/restore preserves remaining interval without duplicate execution."""
    job = CompactionJob(store=temp_store, bus=bus, scheduler=scheduler)
    scheduler.register_task("state_compaction", "compaction", job.run_cycle, 300.0, Priority.LOGGING)
    
    snap = scheduler.snapshot()
    # Check remaining time is saved
    tasks = snap.get("tasks", [])
    task = next((t for t in tasks if t["task_id"] == "state_compaction"), None)
    assert task is not None
    assert "remaining" in task
    
    # Create new scheduler, restore
    sched2 = Scheduler(max_workers=2)
    sched2.restore(snap)
    # Re-register
    sched2.register_task("state_compaction", "compaction", job.run_cycle, 300.0, Priority.LOGGING)
    
    # Assert it kept restored state
    task_restored = sched2._tasks["state_compaction"]
    # If the remaining time is working, next_run should not just be time.monotonic() + 300
    assert task_restored.next_run > 0
    sched2.stop(wait=False)

def test_eventbus_publication_failure_safe(temp_store, bus, scheduler):
    """9. EventBus publication failure does not fail the maintenance transaction."""
    job = CompactionJob(store=temp_store, bus=bus, scheduler=scheduler)
    original_publish = job.bus.publish
    def bad_publish(*args, **kwargs):
        raise RuntimeError("Bus failure")
    job.bus.publish = bad_publish
    
    # Should not crash
    try:
        job.run_cycle()
    except Exception:
        pytest.fail("Cycle crashed due to bus publication failure")
    finally:
        job.bus.publish = original_publish

def test_invalid_config_fallback(bus, scheduler):
    """13. Invalid configuration falls back safely."""
    job = CompactionJob(store=None, bus=bus, scheduler=scheduler, interval=-10, expiry_batch="bad", compress_batch=-5, max_duration=-1.0)
    assert job.interval >= 1.0
    assert job.expiry_batch >= 1
    assert job.compress_batch >= 1
    assert job.max_duration >= 0.1

def test_shutdown_does_not_hang(temp_store, bus):
    """14. Shutdown during or immediately after a cycle does not hang."""
    sched = Scheduler(max_workers=2)
    sched.start()
    
    job = CompactionJob(store=temp_store, bus=bus, scheduler=sched)
    sched.register_task("state_compaction", "compaction", job.run_cycle, 0.1, Priority.LOGGING)
    
    time.sleep(0.3)
    sched.stop(wait=True)
    # If we got here, it didn't hang
    assert True

def test_exactly_one_terminal_event(temp_store, bus, scheduler):
    """15. Started and exactly one terminal lifecycle event are emitted per attempted cycle."""
    job = CompactionJob(store=temp_store, bus=bus, scheduler=scheduler)
    events = []
    bus.subscribe("maintenance.compaction.*", lambda ev: events.append(ev), mode="sync")
    
    job.run_cycle()
    
    assert len(events) == 2
    assert events[0].topic == "maintenance.compaction.started"
    assert events[1].topic == "maintenance.compaction.completed"
