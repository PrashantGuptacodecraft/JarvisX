"""Phase B · B5 ↔ ContinuityManager restore-on-boot verification.

Simulates a process restart through the real persistence layer (fresh objects + file
round-trip = process boundary) and asserts the scheduler RESUMES rather than resets.

Run:  python -m pytest tests/test_scheduler_continuity.py -v
"""
from __future__ import annotations

import time

from shared_core.scheduler import Priority, Scheduler
from shared_core.state_manager import ContinuityManager


def test_scheduler_restore_on_boot_resumes_not_resets(tmp_path):
    path = str(tmp_path / "continuity.json")

    # ── Process A: register, accumulate state, persist via ContinuityManager ──
    sched_a = Scheduler()
    sched_a.register_task("paused_task", "paused", lambda: None,
                          interval=5.0, priority=Priority.BACKGROUND)
    work = sched_a.register_task("work", "work", lambda: None,
                                 interval=10.0, priority=Priority.USER)
    sched_a.pause_task("paused_task")
    work.run_count = 12
    work.error_count = 2
    work.total_latency = 1.5
    work.next_run = time.monotonic() + 7.0       # 7s remaining at "crash"

    cont_a = ContinuityManager(path=path)
    cont_a.register_provider("scheduler", sched_a.snapshot, sched_a.restore)
    assert cont_a.save() is True
    sched_a.stop()                                # "kill process A"

    # ── Process B: fresh objects, restore from the persisted snapshot ─────────
    sched_b = Scheduler()
    sched_b.register_task("paused_task", "paused", lambda: None,
                          interval=5.0, priority=Priority.BACKGROUND)
    sched_b.register_task("work", "work", lambda: None,
                          interval=10.0, priority=Priority.USER)
    cont_b = ContinuityManager(path=path)
    cont_b.register_provider("scheduler", sched_b.snapshot, sched_b.restore)
    restored = cont_b.restore()
    assert restored >= 1

    wb = sched_b._tasks["work"]
    pb = sched_b._tasks["paused_task"]

    # paused state restored
    assert pb.paused is True
    # task metrics restored
    assert wb.run_count == 12
    assert wb.error_count == 2
    assert abs(wb.total_latency - 1.5) < 1e-6
    # remaining interval timing restored (~7s, NOT a fresh 10s)
    remaining = wb.next_run - time.monotonic()
    assert 5.0 < remaining < 8.0
    # NOT a fresh reset: a reset would leave paused=False and run_count=0
    assert not (pb.paused is False and wb.run_count == 0)
    sched_b.stop()


def test_scheduler_restore_applies_to_late_registration(tmp_path):
    """Restore before re-registering a task: state still applied when the task registers."""
    path = str(tmp_path / "continuity.json")
    sched_a = Scheduler()
    sched_a.register_task("late", "late", lambda: None, interval=3.0)
    sched_a.pause_task("late")
    cont_a = ContinuityManager(path=path)
    cont_a.register_provider("scheduler", sched_a.snapshot, sched_a.restore)
    cont_a.save()
    sched_a.stop()

    sched_b = Scheduler()
    cont_b = ContinuityManager(path=path)
    cont_b.register_provider("scheduler", sched_b.snapshot, sched_b.restore)
    cont_b.restore()                              # restore BEFORE registering
    sched_b.register_task("late", "late", lambda: None, interval=3.0)
    assert sched_b._tasks["late"].paused is True  # applied on later registration
    sched_b.stop()
