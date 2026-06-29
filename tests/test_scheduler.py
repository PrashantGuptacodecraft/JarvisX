"""Phase B · B5 acceptance + stress tests for the central scheduler.

Run:  python -m pytest tests/test_scheduler.py -v
"""
from __future__ import annotations

import json
import threading
import time

from shared_core.scheduler import (
    Coalescer,
    CountingCoalescer,
    Priority,
    ScheduledTask,
    Scheduler,
)
from shared_core.scheduler.scheduler import SCHEDULER_SNAPSHOT_SCHEMA_VERSION


class _Counter:
    def __init__(self):
        self.n = 0
        self._lock = threading.Lock()

    def inc(self):
        with self._lock:
            self.n += 1


# ── task registration ────────────────────────────────────────────────────────
def test_task_registration():
    s = Scheduler()
    t = s.register_task("t1", "demo", lambda: None, interval=1.0, priority=Priority.USER,
                        source_module="test", tags=("a", "b"))
    assert isinstance(t, ScheduledTask)
    assert s._tasks["t1"] is t
    assert t.source_module == "test"
    assert t.tags == ("a", "b")
    assert t.priority == Priority.USER


# ── multi-rate execution timing ──────────────────────────────────────────────
def test_multi_rate_execution():
    s = Scheduler()
    fast, slow = _Counter(), _Counter()
    s.register_task("fast", "fast", fast.inc, interval=0.03, priority=Priority.BACKGROUND)
    s.register_task("slow", "slow", slow.inc, interval=0.15, priority=Priority.BACKGROUND)
    s.start()
    time.sleep(0.6)
    s.stop()
    assert fast.n > slow.n          # different rates honored
    assert fast.n >= 5


# ── priority ordering (critical > user > background > logging) ────────────────
def test_priority_ordering():
    s = Scheduler()
    now = time.monotonic()
    for tid, prio in [("log", Priority.LOGGING), ("crit", Priority.CRITICAL),
                      ("bg", Priority.BACKGROUND), ("usr", Priority.USER)]:
        t = s.register_task(tid, tid, lambda: None, interval=1.0, priority=prio)
        t.next_run = now - 1.0      # force due
    due = s._collect_due_tasks(time.monotonic())
    assert [t.id for t in due] == ["crit", "usr", "bg", "log"]


# ── async-safe concurrent execution (non-blocking) ───────────────────────────
def test_concurrent_execution_non_blocking():
    s = Scheduler(max_workers=4)
    state = {"now": 0, "max": 0}
    lock = threading.Lock()

    def busy():
        with lock:
            state["now"] += 1
            state["max"] = max(state["max"], state["now"])
        time.sleep(0.08)
        with lock:
            state["now"] -= 1

    for i in range(4):
        s.register_task(f"c{i}", "busy", busy, interval=0.05, priority=Priority.BACKGROUND)
    s.start()
    time.sleep(0.4)
    s.stop()
    assert state["max"] >= 2        # tasks ran concurrently, never serialized/blocked


# ── missed tick detection + recovery ─────────────────────────────────────────
def test_missed_tick_detection_and_recovery():
    s = Scheduler()
    t = s.register_task("m", "m", lambda: None, interval=1.0, priority=Priority.BACKGROUND)
    now = time.monotonic()
    t.next_run = now - 5.0          # 5 intervals overdue
    due = s._collect_due_tasks(now)
    assert t in due
    s._dispatch_batch(due, now)
    assert t.missed_ticks == 5      # detected
    assert t.next_run > now         # realigned forward (no stale backlog)


# ── task cancellation (unregister) + pause/resume ────────────────────────────
def test_task_cancellation_and_pause_resume():
    s = Scheduler()
    s.register_task("x", "x", lambda: None, interval=1.0)
    assert s.pause_task("x") is True
    assert s._tasks["x"].paused is True
    assert s.resume_task("x") is True
    assert s._tasks["x"].paused is False
    assert s.unregister_task("x") is True
    assert "x" not in s._tasks
    assert s.unregister_task("nope") is False


def test_paused_task_not_dispatched():
    s = Scheduler()
    t = s.register_task("p", "p", lambda: None, interval=1.0)
    t.next_run = time.monotonic() - 1
    s.pause_task("p")
    assert s._collect_due_tasks(time.monotonic()) == []


# ── exception isolation (one failure must not stop the scheduler) ────────────
def test_exception_isolation():
    s = Scheduler()
    good = _Counter()

    def boom():
        raise RuntimeError("intentional")

    s.register_task("bad", "bad", boom, interval=0.04, priority=Priority.BACKGROUND)
    s.register_task("good", "good", good.inc, interval=0.04, priority=Priority.BACKGROUND)
    s.start()
    time.sleep(0.4)
    running = s.health()["running"]
    s.stop()
    assert s._tasks["bad"].error_count > 0
    assert good.n > 0               # good task kept running despite the failing one
    assert running is True


# ── bounded queue behavior (never unbounded) ─────────────────────────────────
def test_bounded_queue_defers_when_full():
    s = Scheduler(queue_cap=5)
    s._pending = {f"d{i}": object() for i in range(5)}   # simulate full queue
    now = time.monotonic()
    tasks = []
    for tid in ("a", "b", "c"):
        t = s.register_task(tid, tid, lambda: None, interval=1.0, priority=Priority.BACKGROUND)
        t.next_run = now - 1
        tasks.append(t)
    s._dispatch_batch(tasks, now)
    assert all(t.deferred == 1 for t in tasks)           # all deferred, none submitted
    assert len(s._pending) == 5                          # queue stayed bounded at cap


# ── overload deferral (low priority shed first, critical proceeds) ───────────
def test_overload_defers_low_priority_only():
    s = Scheduler(queue_cap=10)
    s._pending = {f"d{i}": object() for i in range(8)}   # 80% → overload
    now = time.monotonic()
    crit = s.register_task("crit", "crit", lambda: None, interval=1.0, priority=Priority.CRITICAL)
    logg = s.register_task("logg", "logg", lambda: None, interval=1.0, priority=Priority.LOGGING)
    crit.next_run = logg.next_run = now - 1
    s._dispatch_batch([crit, logg], now)
    assert logg.deferred == 1        # low priority shed under overload
    assert crit.deferred == 0        # critical still dispatched
    s.stop()


# ── coalescer hook behavior (500 events → 1 aggregate) ───────────────────────
def test_coalescer_collapses_burst():
    c = CountingCoalescer()
    for i in range(500):
        c.add("mouse_move", {"i": i})
    out = c.flush()
    assert len(out) == 1
    assert out[0]["key"] == "mouse_move"
    assert out[0]["count"] == 500
    assert c.flush() == []           # cleared after flush


def test_coalescer_attached_to_scheduler():
    s = Scheduler()
    c = CountingCoalescer()
    received = []
    s.attach_coalescer(c, handler=received.append)
    c.add("evt", 1)
    c.add("evt", 2)
    s._run_attachments()             # simulate one tick
    assert received and received[0][0]["count"] == 2


# ── queue monitor callbacks ──────────────────────────────────────────────────
def test_queue_monitor_callback():
    s = Scheduler()
    seen = []
    s.register_queue_monitor(seen.append)
    s._run_attachments()
    assert seen and isinstance(seen[0], int)


# ── snapshot() serialization ─────────────────────────────────────────────────
def test_snapshot_serialization():
    s = Scheduler()
    s.register_task("k", "k", lambda: None, interval=2.0, priority=Priority.USER,
                    source_module="m", tags=("z",))
    s.pause_task("k")
    snap = s.snapshot()
    assert snap["schema_version"] == SCHEDULER_SNAPSHOT_SCHEMA_VERSION
    assert json.dumps(snap)          # fully JSON-serializable
    task = snap["tasks"][0]
    assert task["task_id"] == "k" and task["paused"] is True
    assert task["interval"] == 2.0 and task["priority"] == int(Priority.USER)


# ── restore() recovery (metadata + paused + metrics) ─────────────────────────
def test_restore_recovers_state():
    s1 = Scheduler()
    t = s1.register_task("r", "r", lambda: None, interval=1.0)
    s1.pause_task("r")
    t.run_count = 7
    snap = s1.snapshot()

    s2 = Scheduler()
    s2.register_task("r", "r", lambda: None, interval=1.0)
    applied = s2.restore(snap)
    assert applied == 1
    assert s2._tasks["r"].paused is True
    assert s2._tasks["r"].run_count == 7


def test_restore_applies_to_late_registered_task():
    s1 = Scheduler()
    s1.register_task("late", "late", lambda: None, interval=1.0)
    s1.pause_task("late")
    snap = s1.snapshot()

    s2 = Scheduler()
    s2.restore(snap)                              # restore BEFORE registering
    s2.register_task("late", "late", lambda: None, interval=1.0)
    assert s2._tasks["late"].paused is True       # state applied on later registration


# ── deterministic timing recovery after simulated restart ────────────────────
def test_timing_recovery_resumes_remaining_interval():
    # interval 10, "crash" with 2s remaining, 2s downtime → should be due (~0 remaining)
    s1 = Scheduler()
    t = s1.register_task("tt", "tt", lambda: None, interval=10.0)
    t.next_run = time.monotonic() + 2.0
    snap = s1.snapshot()
    snap["saved_wall"] -= 2.0                     # simulate 2s of downtime

    s2 = Scheduler()
    s2.register_task("tt", "tt", lambda: None, interval=10.0)
    s2.restore(snap)
    remaining_after = s2._tasks["tt"].next_run - time.monotonic()
    assert remaining_after <= 0.5                 # resumed, not restarted at full 10s


def test_timing_recovery_partial_downtime():
    s1 = Scheduler()
    t = s1.register_task("tp", "tp", lambda: None, interval=10.0)
    t.next_run = time.monotonic() + 2.0           # 2s remaining
    snap = s1.snapshot()
    snap["saved_wall"] -= 0.5                      # 0.5s downtime

    s2 = Scheduler()
    s2.register_task("tp", "tp", lambda: None, interval=10.0)
    s2.restore(snap)
    remaining_after = s2._tasks["tp"].next_run - time.monotonic()
    assert 1.0 < remaining_after < 2.0            # ~1.5s left, not a fresh 10s


# ── schema_version validation + migration path ───────────────────────────────
def test_schema_version_present():
    assert Scheduler().snapshot()["schema_version"] == SCHEDULER_SNAPSHOT_SCHEMA_VERSION


def test_restore_rejects_newer_schema():
    s = Scheduler()
    s.register_task("z", "z", lambda: None, interval=1.0)
    future = {"schema_version": 999, "tasks": [{"task_id": "z", "paused": True}]}
    assert s.restore(future) == 0                 # newer schema skipped, not corrupted
    assert s._tasks["z"].paused is False          # untouched


def test_legacy_v0_snapshot_best_effort():
    s = Scheduler()
    s.register_task("z", "z", lambda: None, interval=1.0)
    legacy = {"tasks": [{"task_id": "z", "paused": True}]}   # no schema_version (v0)
    applied = s.restore(legacy)
    assert applied == 1
    assert s._tasks["z"].paused is True           # migrated best-effort


def test_migrate_snapshot_stamps_current_version():
    s = Scheduler()
    migrated = s._migrate_snapshot({"tasks": []}, 0)
    assert migrated["schema_version"] == SCHEDULER_SNAPSHOT_SCHEMA_VERSION


# ── stress: overload scenario stays stable ───────────────────────────────────
def test_stress_concurrent_overload_stability():
    s = Scheduler(max_workers=4, queue_cap=50)
    counters = [_Counter() for _ in range(25)]
    for i, c in enumerate(counters):
        prio = (Priority.CRITICAL, Priority.USER, Priority.BACKGROUND, Priority.LOGGING)[i % 4]
        s.register_task(f"s{i}", f"s{i}", c.inc, interval=0.02, priority=prio)

    def flaky():
        raise ValueError("boom")

    def slow():
        time.sleep(0.1)

    s.register_task("flaky", "flaky", flaky, interval=0.02, priority=Priority.BACKGROUND)
    s.register_task("slow", "slow", slow, interval=0.02, priority=Priority.BACKGROUND)
    s.start()
    time.sleep(1.0)
    health = s.health()
    s.stop()
    assert health["running"] is True
    assert sum(c.n for c in counters) > 50            # lots of work completed
    assert s._tasks["flaky"].error_count > 0          # failures isolated
    assert s._tasks["slow"].overlap_skips > 0         # overlap guard fired (no pile-up)
    assert health["queue_size"] <= health["queue_cap"]  # never unbounded
