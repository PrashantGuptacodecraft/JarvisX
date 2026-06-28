"""continuity.py - crash-safe machine continuity (Phase B · B10, B11).

"Restart = pause/resume, not fresh boot." A provider registry lets any subsystem contribute a
slice of state to persist and to restore. On boot, restore() rehydrates every registered slice.

Design guarantees
-----------------
* **Atomic writes** (temp file + os.replace) → a crash mid-write never corrupts the snapshot.
* **Tolerant load** → missing/corrupt snapshot returns {} and boot proceeds normally.
* **Autosave** on a fixed interval + an explicit save() on shutdown/atexit → bounded data loss
  on hard crash (at most one interval of state).
* **Safe scope** → durable WorldState + registered runtime/reasoning slices are persisted.
  Live event-bus queues are intentionally NOT persisted (transient, thread-owned, unsafe);
  the durable record of what happened lives in the History Ledger instead.
"""
from __future__ import annotations

import json
import os
import threading
from typing import Callable

from config.logger import get_logger

log = get_logger("state.continuity")

_DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data"
)
DEFAULT_PATH = os.path.join(_DATA_DIR, "continuity.json")


class ContinuityManager:
    def __init__(self, path: str = DEFAULT_PATH, autosave_interval: float = 15.0):
        self.path = path
        self.autosave_interval = float(autosave_interval)
        self._providers: dict[str, tuple[Callable[[], object], Callable[[object], None]]] = {}
        self._lock = threading.Lock()
        self._autosave_thread = None
        self._running = False
        os.makedirs(os.path.dirname(path), exist_ok=True)

    # ── provider registry ────────────────────────────────────────────────────
    def register_provider(self, name: str, get_fn: Callable[[], object],
                          set_fn: Callable[[object], None]) -> None:
        """Register a state slice. get_fn() -> JSON-serializable; set_fn(value) restores it."""
        with self._lock:
            self._providers[name] = (get_fn, set_fn)

    # ── save (B10) ───────────────────────────────────────────────────────────
    def collect(self) -> dict:
        data = {}
        with self._lock:
            providers = dict(self._providers)
        for name, (get_fn, _set) in providers.items():
            try:
                value = get_fn()
                json.dumps(value)   # strict validation; non-JSON-native slices are skipped
                data[name] = value
            except Exception as exc:
                log.debug(f"continuity provider '{name}' skipped (not serializable): {exc}")
        return data

    def save(self) -> bool:
        """Atomically persist all provider state. Returns True on success."""
        data = self.collect()
        tmp = self.path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f)   # data already strict-validated in collect()
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.path)   # atomic
            return True
        except Exception as exc:
            log.warning(f"continuity save failed: {exc}")
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except Exception:
                pass
            return False

    # ── load / restore (B11) ─────────────────────────────────────────────────
    def load(self) -> dict:
        """Read the snapshot; return {} on missing/corrupt (crash-safe)."""
        try:
            if not os.path.exists(self.path):
                return {}
            with open(self.path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            log.warning(f"continuity load failed (starting fresh): {exc}")
            return {}

    def restore(self) -> int:
        """Rehydrate every registered provider from the saved snapshot. Returns count restored."""
        data = self.load()
        if not data:
            return 0
        restored = 0
        with self._lock:
            providers = dict(self._providers)
        for name, (_get, set_fn) in providers.items():
            if name in data:
                try:
                    set_fn(data[name])
                    restored += 1
                except Exception as exc:
                    log.warning(f"continuity restore '{name}' failed: {exc}")
        log.info(f"Continuity restored {restored} state slice(s) — resuming, not fresh boot.")
        return restored

    # ── autosave lifecycle ───────────────────────────────────────────────────
    def start_autosave(self) -> None:
        if self._running:
            return
        self._running = True
        self._autosave_thread = threading.Thread(
            target=self._autosave_loop, name="continuity-autosave", daemon=True
        )
        self._autosave_thread.start()

    def _autosave_loop(self) -> None:
        import time
        while self._running:
            time.sleep(self.autosave_interval)
            self.save()

    def stop(self, final_save: bool = True) -> None:
        self._running = False
        if final_save:
            self.save()
