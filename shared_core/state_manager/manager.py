"""manager.py - StateManager: the live machine-awareness hub (Phase B).

Milestones:
  B3  live state updates from bus      B4  per-field history ring buffers
  B9  state query API                  B12 high-rate backpressure (via bus ASYNC + coalescing)
  BL1 transition recording             BL9 transitions flow through the Event Bus

Flow:  bus event  ->  StateManager handler  ->  WorldState.set(...)  ->  (on change)
       per-field history append  +  HistoryLedger.record(transition).

The manager subscribes ASYNC with coalescing on the high-rate OS snapshot topic, so a flood of
perception events can never stall it (backpressure inherited from the Phase-A bus).
"""
from __future__ import annotations

import threading
import time
from collections import deque
from typing import Optional

from config.logger import get_logger

from .ledger import HistoryLedger
from .world_state import WorldState

log = get_logger("state.manager")


class StateManager:
    def __init__(self, bus, ledger: Optional[HistoryLedger] = None, history_len: int = 256):
        self.bus = bus
        self.state = WorldState()
        self.ledger = ledger if ledger is not None else HistoryLedger()
        self._history: dict[str, deque] = {}
        self._history_len = history_len
        self._lock = threading.Lock()
        self._subs = []

    # ── lifecycle ────────────────────────────────────────────────────────────
    def start(self):
        """Subscribe to perception topics on the bus (B3, BL9). Additive + crash-proof."""
        try:
            # High-rate OS snapshots: ASYNC + coalesced so floods never back up (B12).
            self._subs.append(self.bus.subscribe(
                "perception.os.snapshot", self._on_os_snapshot,
                mode="async", source="state_manager", maxlen=64,
                coalesce_key=lambda e: "os",
            ))
            self._subs.append(self.bus.subscribe(
                "perception.os.active_window", self._on_active_window,
                mode="async", source="state_manager", maxlen=128,
            ))
            self._subs.append(self.bus.subscribe(
                "perception.voice.heard", self._on_voice,
                mode="async", source="state_manager", maxlen=128,
            ))
            self._subs.append(self.bus.subscribe(
                "perception.dev.file_changed", self._on_file_changed,
                mode="async", source="state_manager", maxlen=256,
            ))
            self._subs.append(self.bus.subscribe(
                "perception.browser.*", self._on_browser,
                mode="async", source="state_manager", maxlen=128,
            ))
            log.info("StateManager subscribed to perception.* topics.")
        except Exception as exc:
            log.warning(f"StateManager subscribe failed: {exc}")

    def stop(self):
        for s in self._subs:
            try:
                self.bus.unsubscribe(s)
            except Exception:
                pass
        self._subs.clear()

    # ── core update path (B3, B4, BL1) ───────────────────────────────────────
    def _update(self, path: str, value, ledger_fields: Optional[dict] = None):
        """Set a WorldState field; on change, append history + record a ledger transition."""
        if value is None:
            return
        old = self.state.set(path, value)
        changed = (old != value)
        # B4: per-field history ring buffer (always timestamped).
        with self._lock:
            buf = self._history.get(path)
            if buf is None:
                buf = deque(maxlen=self._history_len)
                self._history[path] = buf
            buf.append((time.time(), value))
        if changed:
            # BL1: record a transition with the required retrospective fields.
            snapshot = self._ledger_snapshot()
            if ledger_fields:
                snapshot.update(ledger_fields)
            self.ledger.record(
                change={"path": path, "old": old, "new": value},
                snapshot=snapshot,
            )

    def _ledger_snapshot(self) -> dict:
        """Build the retrospective field set from current WorldState (BL2)."""
        return {
            "active_window": self.state.get("screen.active_window"),
            "focused_process": self.state.get("system.focused_process"),
            "cpu": self.state.get("system.cpu"),
            "memory": self.state.get("system.memory"),
            "running_terminals": self.state.get("system.running_terminals"),
            "browser_state_change": self.state.get("browser.last_change"),
            "clipboard_change": self.state.get("dev.clipboard"),
            "file_modifications": self.state.get("dev.last_file_changed"),
            "network_summary": self.state.get("system.network_summary"),
        }

    # ── bus handlers ─────────────────────────────────────────────────────────
    def _on_os_snapshot(self, event):
        p = event.payload or {}
        self._update("system.cpu", p.get("cpu"))
        self._update("system.memory", p.get("memory"))
        self._update("system.battery", p.get("battery"))
        self._update("system.focused_process", p.get("focused_process"))
        if "running_terminals" in p:
            self._update("system.running_terminals", p.get("running_terminals"))
        if "network_summary" in p:
            self._update("system.network_summary", p.get("network_summary"))
        if "clipboard_change" in p and p["clipboard_change"]:
            self._update("dev.clipboard", p.get("clipboard_change"))

    def _on_active_window(self, event):
        self._update("screen.active_window", (event.payload or {}).get("title"))

    def _on_voice(self, event):
        self._update("voice.last_heard", (event.payload or {}).get("text"))

    def _on_file_changed(self, event):
        path = (event.payload or {}).get("path")
        self._update("dev.last_file_changed", path)

    def _on_browser(self, event):
        p = event.payload or {}
        self._update("browser.last_change", p.get("change") or event.topic)
        if p.get("active_tab"):
            self._update("browser.active_tab", p.get("active_tab"))

    # ── continuity (B10/B11) ─────────────────────────────────────────────────
    def restore_snapshot(self, snap: dict) -> None:
        """Rehydrate the live WorldState from a persisted snapshot (restart = pause/resume)."""
        try:
            self.state.restore(snap)
            log.info("WorldState restored from continuity snapshot.")
        except Exception as exc:
            log.warning(f"WorldState restore failed: {exc}")

    # ── query API (B9) ───────────────────────────────────────────────────────
    def snapshot(self) -> dict:
        return self.state.snapshot()

    def get(self, path: str):
        return self.state.get(path)

    def history(self, path: str, n: int = 50) -> list:
        with self._lock:
            buf = self._history.get(path)
            return list(buf)[-n:] if buf else []
