"""Phase B · B13 — final integration validation of the whole Phase-B infrastructure.

Validation matrix:
  1. EventBus ↔ Scheduler          (publish → scheduled consume, no loss under normal load)
  2. StateManager ↔ HistoryLedger  (every update persisted; replay reconstructs exact state)
  3. ContinuityManager ↔ Scheduler (kill/restart → restored paused/timing/metrics, no reset)
  4. Event storm stress            (1000+ events: no deadlock, bounded, critical never dropped)
  5. Long-runtime stability        (thread/queue/ledger growth bounded; no leak)
  6. Cross-system full chain        (Bus → Scheduler → StateManager → Ledger → Continuity → Restore)

Run:  python -m pytest tests/test_phase_b_integration.py -v
"""
from __future__ import annotations

import threading
import time

from shared_core.event_bus import EventBus
from shared_core.scheduler import Priority, Scheduler
from shared_core.state_manager import ContinuityManager, build_state_manager


class _Counter:
    def __init__(self):
        self.n = 0
        self._lock = threading.Lock()

    def inc(self):
        with self._lock:
            self.n += 1


# ── 1. EventBus ↔ Scheduler: scheduled publishes, no event loss ──────────────
def test_eventbus_scheduler_no_loss():
    bus = EventBus("b13")
    sch = Scheduler(max_workers=4)
    seen = _Counter()
    bus.subscribe("test.tick", lambda e: seen.inc(), mode="sync", source="collector")
    task = sch.register_task("pub", "pub",
                             lambda: bus.publish("test.tick", {}, source="pub"),
                             interval=0.01, priority=Priority.USER)
    sch.start()
    time.sleep(0.5)
    sch.stop()
    bus.drain()
    assert task.run_count > 10
    assert seen.n == task.run_count          # every scheduled publish delivered — no loss


# ── 2. StateManager ↔ HistoryLedger: persistence + replay reconstruction ─────
def test_statemanager_ledger_replay_reconstructs_state():
    bus = EventBus("b13")
    sm = build_state_manager(bus, persist=False)
    sm.start()
    try:
        windows = ["Editor", "Browser", "Terminal", "Deploy Console"]
        for w in windows:
            bus.publish("perception.os.active_window", {"title": w}, source="probe")
        assert bus.drain(timeout=3.0)

        # every update persisted to the ledger (one transition per distinct change)
        recent = sm.ledger.recent(50)
        aw_changes = [t for t in recent if t["change"]["path"] == "screen.active_window"]
        assert [t["change"]["new"] for t in aw_changes] == windows

        # replay: reconstruct state purely from ledger transitions
        reconstructed = {}
        for t in sm.ledger.recent(50):
            reconstructed[t["change"]["path"]] = t["change"]["new"]
        assert reconstructed["screen.active_window"] == windows[-1]
        assert sm.get("screen.active_window") == windows[-1]   # live state matches replay
    finally:
        sm.stop()


# ── 3. ContinuityManager ↔ Scheduler recovery (kill/restart) ─────────────────
def test_continuity_scheduler_recovery(tmp_path):
    path = str(tmp_path / "continuity.json")

    sch_a = Scheduler()
    sch_a.register_task("paused", "paused", lambda: None, interval=5.0,
                        priority=Priority.BACKGROUND)
    w = sch_a.register_task("work", "work", lambda: None, interval=10.0, priority=Priority.USER)
    sch_a.pause_task("paused")
    w.run_count = 9
    w.next_run = time.monotonic() + 6.0
    cont_a = ContinuityManager(path=path)
    cont_a.register_provider("scheduler", sch_a.snapshot, sch_a.restore)
    assert cont_a.save()
    sch_a.stop()                               # "kill process"

    sch_b = Scheduler()                        # "restart process"
    sch_b.register_task("paused", "paused", lambda: None, interval=5.0,
                        priority=Priority.BACKGROUND)
    sch_b.register_task("work", "work", lambda: None, interval=10.0, priority=Priority.USER)
    cont_b = ContinuityManager(path=path)
    cont_b.register_provider("scheduler", sch_b.snapshot, sch_b.restore)
    assert cont_b.restore() >= 1
    assert sch_b._tasks["paused"].paused is True           # paused restored
    assert sch_b._tasks["work"].run_count == 9             # metrics restored
    rem = sch_b._tasks["work"].next_run - time.monotonic()
    assert 4.0 < rem < 7.0                                 # timing restored (not fresh 10s)
    sch_b.stop()


# ── 4. Event storm stress: 1000+ events ──────────────────────────────────────
def test_event_storm_1000plus():
    # bus storm: 1000 events on a bounded, coalesced subscription
    bus = EventBus("b13")
    got = _Counter()
    bus.subscribe("perception.os.snapshot", lambda e: got.inc(), mode="async",
                  source="c", maxlen=50, coalesce_key=lambda e: "os")
    for i in range(1200):
        bus.publish("perception.os.snapshot", {"i": i}, source="storm")
    assert bus.drain(timeout=5.0)              # no deadlock
    st = bus.stats()
    assert st["published_by_topic"]["perception.os.snapshot"] == 1200
    assert got.n < 1200                        # coalesced/shed — bounded, not 1:1

    # scheduler storm: critical preserved, low-priority shed, bounded queue
    sch = Scheduler(max_workers=4, queue_cap=8)
    crit = _Counter()
    sch.register_task("critical", "critical",
                      lambda: (crit.inc(), time.sleep(0.004)), interval=0.02,
                      priority=Priority.CRITICAL)
    for i in range(40):
        sch.register_task(f"low{i}", f"low{i}", lambda: time.sleep(0.01),
                          interval=0.005, priority=Priority.BACKGROUND)
    sch.start()
    time.sleep(1.0)
    diag = sch.diagnostics()
    crit_deferred = sch._tasks["critical"].deferred
    sch.stop()                                 # returns → no deadlock
    assert crit_deferred == 0                  # critical never dropped
    assert crit.n > 0
    assert diag["dropped_events"] > 0          # noncritical shed
    assert diag["queue_depth"] <= sch._queue_cap * 2   # bounded


# ── 5. Long-runtime stability (bounded growth / no leak) ─────────────────────
def test_long_runtime_stability():
    bus = EventBus("b13")
    sm = build_state_manager(bus, persist=False, ring_len=500)
    sm.start()
    sch = Scheduler(max_workers=4)
    counter = {"n": 0}

    def churn():
        counter["n"] += 1
        # continuously change state to exercise the ledger
        bus.publish("perception.os.active_window", {"title": f"win{counter['n'] % 7}"},
                    source="churn")

    sch.register_task("churn", "churn", churn, interval=0.01, priority=Priority.BACKGROUND)
    sch.register_task("crit", "crit", lambda: None, interval=0.02, priority=Priority.CRITICAL)
    sch.start()
    try:
        time.sleep(0.6)                        # warm up pool threads
        base_threads = threading.active_count()
        time.sleep(2.5)                        # sustained runtime
        end_threads = threading.active_count()
        bus.drain()

        assert end_threads <= base_threads + 1         # thread count stable (no runaway)
        assert sch.queue_size() <= sch._queue_cap      # queue bounded
        assert sm.ledger.size() <= 500                 # ledger ring bounded (no leak)
    finally:
        sch.stop()
        sm.stop()


# ── 6. Cross-system full chain: Bus → Scheduler → State → Ledger → Continuity → Restore ─
def test_cross_system_full_chain(tmp_path):
    path = str(tmp_path / "continuity.json")

    # -- session 1: full live chain --
    bus1 = EventBus("b13")
    sm1 = build_state_manager(bus1, persist=False)
    sm1.start()
    sch1 = Scheduler(max_workers=4)
    tick = {"cpu": 0}

    def sample():
        tick["cpu"] += 1
        bus1.publish("perception.os.snapshot", {"cpu": float(tick["cpu"])}, source="sampler")

    sch1.register_task("sampler", "sampler", sample, interval=0.02,
                       priority=Priority.BACKGROUND, source_module="b13")
    sch1.start()
    time.sleep(0.4)
    sch1.stop()
    assert bus1.drain(timeout=3.0)

    assert sm1.get("system.cpu") is not None       # Bus → Scheduler → State
    assert sm1.ledger.size() > 0                    # State → Ledger
    saved_cpu = sm1.get("system.cpu")

    cont1 = ContinuityManager(path=path)
    cont1.register_provider("world_state", sm1.snapshot, sm1.restore_snapshot)
    cont1.register_provider("scheduler", sch1.snapshot, sch1.restore)
    assert cont1.save()                             # → Continuity
    sm1.stop()

    # -- session 2: restore the whole chain --
    bus2 = EventBus("b13")
    sm2 = build_state_manager(bus2, persist=False)
    sm2.start()
    sch2 = Scheduler(max_workers=4)
    sch2.register_task("sampler", "sampler", lambda: None, interval=0.02,
                       priority=Priority.BACKGROUND)
    cont2 = ContinuityManager(path=path)
    cont2.register_provider("world_state", sm2.snapshot, sm2.restore_snapshot)
    cont2.register_provider("scheduler", sch2.snapshot, sch2.restore)
    restored = cont2.restore()                      # → Restore

    assert restored == 2
    assert sm2.get("system.cpu") == saved_cpu       # world state restored through the chain
    assert "sampler" in sch2._tasks
    sch2.stop()
    sm2.stop()
