"""Phase B · B12 backpressure acceptance tests.

Covers: overload detection, critical-never-dropped, low-priority throttle/shed, bounded queue,
no deadlock, bounded memory, overload recovery (hysteresis), diagnostics surface, and a 10x flood.

Run:  python -m pytest tests/test_backpressure.py -v
"""
from __future__ import annotations

import threading
import time

from shared_core.scheduler import CountingCoalescer, Priority, Scheduler


class _Counter:
    def __init__(self):
        self.n = 0
        self._lock = threading.Lock()

    def inc(self):
        with self._lock:
            self.n += 1


# ── overload detection + recovery (hysteresis) ───────────────────────────────
def test_overload_detection_and_recovery():
    s = Scheduler(queue_cap=10)
    assert s._overload_state is False
    s._update_overload_state(8)          # >= 80% → enter overload
    assert s._overload_state is True
    assert s._overload_transitions == 1
    s._update_overload_state(7)          # between water marks → stays overloaded
    assert s._overload_state is True
    s._update_overload_state(4)          # <= 50% low-water → recover
    assert s._overload_state is False


# ── critical never dropped; low-priority shed under full queue ───────────────
def test_critical_never_dropped_low_shed():
    s = Scheduler(queue_cap=5)
    s._pending = {f"d{i}": object() for i in range(10)}   # queue over cap
    now = time.monotonic()
    crit = s.register_task("crit", "crit", lambda: None, interval=1.0, priority=Priority.CRITICAL)
    bg = s.register_task("bg", "bg", lambda: None, interval=1.0, priority=Priority.BACKGROUND)
    crit.next_run = bg.next_run = now - 1
    s._dispatch_batch([crit, bg], now)
    assert crit.deferred == 0            # critical dispatched despite full queue
    assert bg.deferred == 1              # low-priority shed
    assert s._dropped_events >= 1
    s.stop()


# ── bounded queue: low-priority flood never grows the queue past cap ─────────
def test_queue_stays_bounded_under_flood():
    s = Scheduler(queue_cap=8)
    s._pending = {f"d{i}": object() for i in range(8)}
    now = time.monotonic()
    tasks = []
    for i in range(50):                  # 50 due low-priority tasks at a full queue
        t = s.register_task(f"t{i}", f"t{i}", lambda: None, interval=1.0,
                            priority=Priority.BACKGROUND)
        t.next_run = now - 1
        tasks.append(t)
    s._dispatch_batch(tasks, now)
    assert len(s._pending) == 8          # not one new dispatch; bounded at cap
    assert all(t.deferred == 1 for t in tasks)
    s.stop()


# ── diagnostics surface (req 9) ──────────────────────────────────────────────
def test_diagnostics_reports_all_fields():
    s = Scheduler()
    d = s.diagnostics()
    for key in ("queue_depth", "dropped_events", "peak_queue", "overload",
                "overload_transitions", "avg_latency_ms", "recent_latency_ms"):
        assert key in d
    assert isinstance(d["overload"], bool)
    assert isinstance(d["recent_latency_ms"], list)


# ── coalescer flood: 10x burst stays bounded, collapses to one ───────────────
def test_coalescer_flood_bounded_and_collapsed():
    c = CountingCoalescer(per_key_max=100)
    for i in range(1000):                # 10x flood on one key
        c.add("mouse_move", {"i": i})
    assert c.depth() <= 100              # bounded memory (drop-oldest)
    assert c.dropped >= 900             # excess safely dropped
    out = c.flush()
    assert len(out) == 1 and out[0]["count"] <= 100   # collapsed to one aggregate


# ── ACCEPTANCE: flood scheduler with 10x volume; stability + all invariants ──
def test_flood_10x_stability():
    s = Scheduler(max_workers=4, queue_cap=8)
    crit = _Counter()
    lows = [_Counter() for _ in range(30)]

    # critical task: must always run
    s.register_task("critical", "critical",
                    lambda: (crit.inc(), time.sleep(0.005)), interval=0.02,
                    priority=Priority.CRITICAL)
    # 10x flood of slow low-priority tasks that saturate the pool
    for i, c in enumerate(lows):
        s.register_task(f"low{i}", f"low{i}",
                        lambda c=c: (c.inc(), time.sleep(0.01)), interval=0.005,
                        priority=Priority.BACKGROUND)

    s.start()
    time.sleep(1.2)
    diag = s.diagnostics()
    crit_task = s._tasks["critical"]
    s.stop()                             # returns → no deadlock (req 6)

    # req 2: overload detected during the flood
    assert diag["overload_transitions"] >= 1
    # req 3/5: critical never dropped, kept executing
    assert crit_task.deferred == 0
    assert crit.n > 0
    # req 4: low-priority throttled/shed
    assert diag["dropped_events"] > 0
    # req 5/7: queue depth bounded (≈ cap; small overage for critical bypass) → bounded memory
    assert diag["queue_depth"] <= s._queue_cap * 2
    assert diag["peak_queue"] <= s._queue_cap * 3
    # req 9: latency measured
    assert diag["avg_latency_ms"] >= 0.0
