"""Phase B acceptance tests — StateManager, WorldState, History Ledger.

Covers: B1, B2, B3, B4, B9 and BL1, BL2, BL3, BL4, BL5, BL6, BL7, BL8, BL9.
Run:  python -m pytest tests/test_state_manager.py -v
"""
from __future__ import annotations

import os
import tempfile
import time

from shared_core.event_bus import EventBus
from shared_core.state_manager import (
    HistoryLedger,
    LedgerStore,
    StateManager,
    WorldState,
    build_state_manager,
)
from shared_core.state_manager.ledger import LEDGER_FIELDS, empty_snapshot


# ── B1 / B2: WorldState + typed sub-states ───────────────────────────────────
def test_worldstate_snapshot_has_all_sections():
    ws = WorldState()
    snap = ws.snapshot()
    for section in ("system", "screen", "vision", "browser", "voice", "dev"):
        assert section in snap
    assert "version" in snap


def test_worldstate_get_set_and_version():
    ws = WorldState()
    assert ws.get("system.cpu") is None
    old = ws.set("system.cpu", 42.0)
    assert old is None
    assert ws.get("system.cpu") == 42.0
    assert ws.version == 1


# ── B3 / B4 / B9: live bus update, history buffers, query API ─────────────────
def test_bus_event_updates_state_and_history():
    bus = EventBus("t")
    sm = build_state_manager(bus, persist=False)
    sm.start()
    try:
        bus.publish("perception.os.active_window", {"title": "VS Code"}, source="test")
        bus.publish("perception.os.active_window", {"title": "Chrome"}, source="test")
        assert bus.drain(timeout=3.0)
        assert sm.get("screen.active_window") == "Chrome"     # B3
        hist = sm.history("screen.active_window", 10)          # B4 + B9
        values = [v for _ts, v in hist]
        assert values == ["VS Code", "Chrome"]
        assert all(isinstance(ts, float) for ts, _v in hist)  # timestamped
    finally:
        sm.stop()


# ── BL2: required fields present in every transition snapshot ─────────────────
def test_ledger_required_fields():
    snap = empty_snapshot()
    for f in ("active_window", "focused_process", "cpu", "memory", "running_terminals",
              "browser_state_change", "clipboard_change", "file_modifications",
              "network_summary"):
        assert f in snap
    assert set(snap.keys()) == set(LEDGER_FIELDS)


# ── BL1 / BL9: transition recorded on change, via the bus ─────────────────────
def test_transition_recorded_on_change():
    bus = EventBus("t")
    sm = build_state_manager(bus, persist=False)
    sm.start()
    try:
        bus.publish("perception.os.active_window", {"title": "Terminal"}, source="test")
        assert bus.drain(timeout=3.0)
        recent = sm.ledger.recent(10)
        assert len(recent) >= 1
        last = recent[-1]
        assert last["change"]["path"] == "screen.active_window"
        assert last["change"]["new"] == "Terminal"
        assert last["snapshot"]["active_window"] == "Terminal"
        assert "ts" in last
    finally:
        sm.stop()


# ── BL3: bounded in-memory ring (no unbounded growth) ─────────────────────────
def test_ledger_ring_bounded():
    ledger = HistoryLedger(store=None, maxlen=100)
    for i in range(500):
        ledger.record(change={"path": "system.cpu", "old": i - 1, "new": i},
                      snapshot={"cpu": i})
    assert ledger.size() == 100           # never exceeds maxlen


# ── BL6 / BL7: temporal point + range queries ─────────────────────────────────
def test_ledger_temporal_queries():
    ledger = HistoryLedger(store=None, maxlen=1000)
    base = time.time() - 1000
    for i in range(10):
        ledger.record(change={"path": "system.cpu", "old": i - 1, "new": i},
                      snapshot={"cpu": i}, ts=base + i * 10)
    # BL6: point-in-time — state in effect at base+45 is the i=4 transition (ts base+40)
    at = ledger.at(base + 45)
    assert at is not None and at["change"]["new"] == 4
    # BL7: range — transitions between base+20 and base+50 inclusive (i=2..5)
    seq = ledger.between(base + 20, base + 50)
    assert [t["change"]["new"] for t in seq] == [2, 3, 4, 5]


# ── BL4 / BL5 / BL8: rolling persistence, pruning, reload ─────────────────────
def test_ledger_store_persist_prune_reload():
    with tempfile.TemporaryDirectory() as d:
        db = os.path.join(d, "ledger.db")
        store = LedgerStore(db_path=db, cap=50, prune_every=10)
        ledger = HistoryLedger(store=store, maxlen=10000)
        for i in range(200):
            ledger.record(change={"path": "system.cpu", "old": i - 1, "new": i},
                          snapshot={"cpu": i}, ts=1000.0 + i)
        # BL5: rolling cap keeps disk bounded (cap + at most one prune-interval slack)
        assert store.count() <= 50 + 10
        store.close()

        # BL8: reopen + rehydrate recent history on boot
        store2 = LedgerStore(db_path=db, cap=50, prune_every=10)
        ledger2 = HistoryLedger(store=store2, maxlen=10000)
        assert ledger2.size() > 0
        newest = ledger2.recent(1)[-1]
        assert newest["change"]["new"] == 199     # most-recent survived
        store2.close()
