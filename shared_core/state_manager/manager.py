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

from .compaction import classify
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
            # B6 telemetry: continuous system + filesystem awareness (coalesced high-rate).
            self._subs.append(self.bus.subscribe(
                "perception.system.cpu", self._on_cpu,
                mode="async", source="state_manager", maxlen=32, coalesce_key=lambda e: "cpu",
            ))
            self._subs.append(self.bus.subscribe(
                "perception.system.memory", self._on_memory,
                mode="async", source="state_manager", maxlen=32, coalesce_key=lambda e: "mem",
            ))
            self._subs.append(self.bus.subscribe(
                "perception.system.disk", self._on_disk,
                mode="async", source="state_manager", maxlen=32, coalesce_key=lambda e: "disk",
            ))
            self._subs.append(self.bus.subscribe(
                "perception.system.gpu", self._on_gpu,
                mode="async", source="state_manager", maxlen=32, coalesce_key=lambda e: "gpu",
            ))
            self._subs.append(self.bus.subscribe(
                "perception.filesystem.change", self._on_fs_change,
                mode="async", source="state_manager", maxlen=256,
            ))
            from shared_core.event_bus.topics import (
                MAINTENANCE_COMPACTION_COMPLETED,
                MAINTENANCE_COMPACTION_FAILED,
                MAINTENANCE_COMPACTION_SKIPPED
            )
            self._subs.append(self.bus.subscribe(
                MAINTENANCE_COMPACTION_COMPLETED, self._on_compaction_event,
                mode="async", source="state_manager", maxlen=8
            ))
            self._subs.append(self.bus.subscribe(
                MAINTENANCE_COMPACTION_FAILED, self._on_compaction_event,
                mode="async", source="state_manager", maxlen=8
            ))
            self._subs.append(self.bus.subscribe(
                MAINTENANCE_COMPACTION_SKIPPED, self._on_compaction_event,
                mode="async", source="state_manager", maxlen=8
            ))
            log.info("StateManager subscribed to perception topics.")
        except Exception as exc:
            log.error(f"StateManager failed to start: {exc}")

    def stop(self):
        try:
            for sub_id in self._subs:
                self.bus.unsubscribe(sub_id)
            self._subs.clear()
            self.ledger.close()
            log.info("StateManager stopped.")
        except Exception as exc:
            log.error(f"StateManager stop failed: {exc}")

    def set_scheduler(self, scheduler) -> None:
        self._scheduler = scheduler
        
    def set_continuity(self, continuity) -> None:
        self._continuity = continuity
        
    def _on_compaction_event(self, evt: Event) -> None:
        """Cache the latest compaction terminal outcome for diagnostics."""
        with self._lock:
            self._last_compaction = evt.payload

    # ── core update path (B3, B4, BL1) ───────────────────────────────────────
    def _update(self, path: str, value, ledger_fields: Optional[dict] = None, retention_class: Optional[str] = None):
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
                retention_class=retention_class,
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
        rc = classify(event.topic, p).value
        self._update("system.cpu", p.get("cpu"), retention_class=rc)
        self._update("system.memory", p.get("memory"), retention_class=rc)
        self._update("system.battery", p.get("battery"), retention_class=rc)
        self._update("system.focused_process", p.get("focused_process"), retention_class=rc)
        if "running_terminals" in p:
            self._update("system.running_terminals", p.get("running_terminals"), retention_class=rc)
        if "network_summary" in p:
            self._update("system.network_summary", p.get("network_summary"), retention_class=rc)
        if "clipboard_change" in p and p["clipboard_change"]:
            self._update("dev.clipboard", p.get("clipboard_change"), retention_class=rc)

    def _on_active_window(self, event):
        rc = classify(event.topic, event.payload).value
        self._update("screen.active_window", (event.payload or {}).get("title"), retention_class=rc)

    def _on_voice(self, event):
        rc = classify(event.topic, event.payload).value
        self._update("voice.last_heard", (event.payload or {}).get("text"), retention_class=rc)

    def _on_file_changed(self, event):
        rc = classify(event.topic, event.payload).value
        path = (event.payload or {}).get("path")
        self._update("dev.last_file_changed", path, retention_class=rc)

    def _on_browser(self, event):
        rc = classify(event.topic, event.payload).value
        p = event.payload or {}
        self._update("browser.last_change", p.get("change") or event.topic, retention_class=rc)
        if p.get("active_tab"):
            self._update("browser.active_tab", p.get("active_tab"), retention_class=rc)

    # ── B6 telemetry handlers ────────────────────────────────────────────────
    def _on_cpu(self, event):
        p = event.payload or {}
        rc = classify(event.topic, p).value
        if "cpu_percent" in p:
            self._update("system.cpu", p.get("cpu_percent"), retention_class=rc)
        self._update("system.cpu_detail", {k: p[k] for k in
                     ("cpu_frequency", "core_count", "per_core_usage") if k in p}, retention_class=rc)

    def _on_memory(self, event):
        p = event.payload or {}
        rc = classify(event.topic, p).value
        if "percent" in p:
            self._update("system.memory", p.get("percent"), retention_class=rc)
        self._update("system.memory_detail", {k: p[k] for k in
                     ("total_memory", "used_memory", "free_memory", "swap_usage") if k in p}, retention_class=rc)

    def _on_disk(self, event):
        rc = classify(event.topic, event.payload).value
        self._update("system.disk", dict(event.payload or {}), retention_class=rc)

    def _on_gpu(self, event):
        p = event.payload or {}
        rc = classify(event.topic, p).value
        if "gpu_usage" in p and p["gpu_usage"] is not None:
            self._update("system.gpu", p.get("gpu_usage"), retention_class=rc)
        self._update("system.gpu_detail", dict(p), retention_class=rc)

    def _on_fs_change(self, event):
        p = event.payload or {}
        rc = classify(event.topic, p).value
        self._update("system.last_fs_change", {"event": p.get("event"), "path": p.get("path")}, retention_class=rc)

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

    def diagnostics(self) -> "StateDiagnostics":
        """BC6: Expose bounded, structured diagnostic view of state components."""
        import sys
        from shared_core.state_manager.history_models import StateDiagnostics
        
        mem_usage = sys.getsizeof(self.state)
        # Add approximate sizes for known structures without heavy iteration
        mem_usage += getattr(self.ledger, "diagnostics", lambda: {})().get("memory_usage_bytes", 0)

        ledger_diag = self.ledger.diagnostics() if hasattr(self.ledger, "diagnostics") else {}
        compaction_diag = getattr(self, "_last_compaction", {})
        scheduler_diag = self._scheduler.diagnostics() if hasattr(self, "_scheduler") and self._scheduler else {}
        continuity_diag = self._continuity.diagnostics() if hasattr(self, "_continuity") and self._continuity else {}
        
        return StateDiagnostics(
            schema_version=1,
            captured_at=time.time(),
            health="ok",
            state={
                "version": self.state.version,
                "memory_usage_bytes": mem_usage,
            },
            ledger=ledger_diag,
            compaction=compaction_diag,
            continuity=continuity_diag,
            scheduler=scheduler_diag,
            warnings=[]
        )

    def publish_diagnostics(self) -> "StateDiagnostics":
        """BC6: Collect one diagnostic snapshot and publish it once."""
        from shared_core.event_bus.topics import PERCEPTION_DEV_DIAGNOSTICS
        diag = self.diagnostics()
        self.bus.publish(PERCEPTION_DEV_DIAGNOSTICS, diag.to_dict(), source="state_manager")
        return diag
