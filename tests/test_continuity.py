"""Phase B acceptance tests — Continuity (B10 serialization, B11 restore/restart=pause).

Run:  python -m pytest tests/test_continuity.py -v
"""
from __future__ import annotations

import os
import tempfile

from shared_core.event_bus import EventBus
from shared_core.state_manager import ContinuityManager, build_state_manager
from shared_core.state_manager.world_state import WorldState


# ── B10: full WorldState serialization round-trips ────────────────────────────
def test_worldstate_snapshot_restore_roundtrip():
    ws = WorldState()
    ws.set("system.cpu", 55.5)
    ws.set("system.running_terminals", ["cmd.exe", "bash.exe"])
    ws.set("screen.active_window", "VS Code")
    ws.set("voice.last_heard", "what time is it")
    snap = ws.snapshot()

    ws2 = WorldState()
    ws2.restore(snap)
    s2 = ws2.snapshot()
    for section in ("system", "screen", "vision", "browser", "voice", "dev"):
        assert s2[section] == snap[section]     # full fidelity


def test_restore_ignores_unknown_fields():
    ws = WorldState()
    ws.restore({"system": {"cpu": 10, "bogus_field": 999}, "nonsense": {"x": 1}})
    assert ws.get("system.cpu") == 10           # known restored, unknown ignored (no crash)


# ── B11: continuity = restart pause/resume across a simulated reboot ───────────
def test_continuity_restart_is_resume_not_fresh():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "continuity.json")

        # --- session 1: set state, persist ---
        bus1 = EventBus("t1")
        sm1 = build_state_manager(bus1, persist=False)
        sm1.state.set("system.cpu", 73.0)
        sm1.state.set("screen.active_window", "Deployment Console")
        cm1 = ContinuityManager(path=path)
        cm1.register_provider("world_state", sm1.snapshot, sm1.restore_snapshot)
        brain_state = {"volatile_memory": {"active_window": "Deployment Console"},
                       "pending": ["shutdown", {}]}
        cm1.register_provider("brain", lambda: brain_state, lambda v: None)
        assert cm1.save()

        # --- session 2: fresh objects, restore ---
        bus2 = EventBus("t2")
        sm2 = build_state_manager(bus2, persist=False)
        assert sm2.get("screen.active_window") is None      # genuinely fresh
        restored = {}
        cm2 = ContinuityManager(path=path)
        cm2.register_provider("world_state", sm2.snapshot, sm2.restore_snapshot)
        cm2.register_provider("brain", lambda: {}, lambda v: restored.update(v))
        n = cm2.restore()

        assert n == 2
        assert sm2.get("screen.active_window") == "Deployment Console"   # resumed
        assert sm2.get("system.cpu") == 73.0
        assert restored["volatile_memory"]["active_window"] == "Deployment Console"
        assert restored["pending"] == ["shutdown", {}]


# ── crash-safety: corrupt/missing snapshot never crashes boot ─────────────────
def test_corrupt_snapshot_is_tolerated():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "continuity.json")
        with open(path, "w", encoding="utf-8") as f:
            f.write("{ this is not valid json ::::")
        cm = ContinuityManager(path=path)
        assert cm.load() == {}                  # tolerant
        assert cm.restore() == 0                 # no providers restored, no crash


def test_missing_snapshot_returns_empty():
    with tempfile.TemporaryDirectory() as d:
        cm = ContinuityManager(path=os.path.join(d, "nope.json"))
        assert cm.load() == {}
        assert cm.restore() == 0


# ── atomic write: real file produced, non-serializable providers skipped ──────
def test_save_is_atomic_and_skips_unserializable():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "continuity.json")
        cm = ContinuityManager(path=path)
        cm.register_provider("ok", lambda: {"a": 1}, lambda v: None)
        cm.register_provider("bad", lambda: object(), lambda v: None)   # not serializable
        assert cm.save()
        assert os.path.exists(path)
        assert not os.path.exists(path + ".tmp")    # temp cleaned up
        data = cm.load()
        assert data == {"ok": {"a": 1}}             # bad provider skipped, ok persisted
