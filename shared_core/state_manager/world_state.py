"""world_state.py - the live machine snapshot (Phase B · B1, B2).

WorldState is the single, versioned, thread-safe object holding the machine's PRESENT state,
organized into typed sub-states. The History Ledger (ledger.py) records the chronological
sequence of PRIOR states; this module is only "now".

All values are JSON-serializable primitives/containers so snapshots can be journaled, persisted,
and crossed over process boundaries.
"""
from __future__ import annotations

import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Optional


@dataclass
class SystemState:
    cpu: Optional[float] = None              # percent
    memory: Optional[float] = None           # percent used
    gpu: Optional[float] = None              # percent (source pending Phase B B6)
    battery: Optional[float] = None          # percent
    focused_process: Optional[str] = None    # foreground window's process name
    running_terminals: list = field(default_factory=list)
    network_summary: dict = field(default_factory=dict)
    # ── B6 continuous telemetry (additive) ──
    cpu_detail: dict = field(default_factory=dict)     # frequency, core_count, per_core
    memory_detail: dict = field(default_factory=dict)  # total/used/free/swap
    disk: dict = field(default_factory=dict)           # usage, throughput, free
    gpu_detail: dict = field(default_factory=dict)     # usage, mem_used, temperature
    last_fs_change: dict = field(default_factory=dict) # {event, path}


@dataclass
class ScreenState:
    active_window: Optional[str] = None
    windows: list = field(default_factory=list)     # window hierarchy (B8, pending)
    ui_tree: Optional[dict] = None                  # UIAutomation tree (B7, pending)
    ocr_text: Optional[str] = None


@dataclass
class VisionState:
    last_gesture: Optional[str] = None
    faces: list = field(default_factory=list)


@dataclass
class BrowserState:
    active_tab: Optional[str] = None
    tabs: list = field(default_factory=list)
    last_change: Optional[str] = None


@dataclass
class VoiceState:
    last_heard: Optional[str] = None


@dataclass
class DevState:
    open_files: list = field(default_factory=list)
    last_file_changed: Optional[str] = None
    diagnostics: list = field(default_factory=list)
    clipboard: dict = field(default_factory=dict)   # {changed, length} - content NOT stored (privacy)


_SECTIONS = {
    "system": SystemState,
    "screen": ScreenState,
    "vision": VisionState,
    "browser": BrowserState,
    "voice": VoiceState,
    "dev": DevState,
}


class WorldState:
    """Versioned, thread-safe container of typed sub-states. Supports dotted get/set."""

    def __init__(self):
        self._lock = threading.RLock()
        self.system = SystemState()
        self.screen = ScreenState()
        self.vision = VisionState()
        self.browser = BrowserState()
        self.voice = VoiceState()
        self.dev = DevState()
        self._version = 0
        self._updated = time.time()

    def _resolve(self, path: str):
        section, _, attr = path.partition(".")
        if section not in _SECTIONS or not attr:
            raise KeyError(f"invalid world-state path: {path!r}")
        return getattr(self, section), attr

    def get(self, path: str) -> Any:
        with self._lock:
            obj, attr = self._resolve(path)
            return getattr(obj, attr, None)

    def set(self, path: str, value: Any) -> Any:
        """Set a field; return the previous value (for change detection)."""
        with self._lock:
            obj, attr = self._resolve(path)
            old = getattr(obj, attr, None)
            setattr(obj, attr, value)
            self._version += 1
            self._updated = time.time()
            return old

    @property
    def version(self) -> int:
        with self._lock:
            return self._version

    def snapshot(self) -> dict:
        """JSON-serializable dict of the entire present state."""
        def _cap_collections(d: dict) -> dict:
            """Recursively bound lists and dicts to at most 1000 items to prevent unbounded serialization."""
            if isinstance(d, dict):
                return {k: _cap_collections(v) for i, (k, v) in enumerate(d.items()) if i < 1000}
            if isinstance(d, list):
                return [_cap_collections(v) for i, v in enumerate(d) if i < 1000]
            return d

        with self._lock:
            return {
                "version": self._version,
                "updated": self._updated,
                "system": _cap_collections(asdict(self.system)),
                "screen": _cap_collections(asdict(self.screen)),
                "vision": _cap_collections(asdict(self.vision)),
                "browser": _cap_collections(asdict(self.browser)),
                "voice": _cap_collections(asdict(self.voice)),
                "dev": _cap_collections(asdict(self.dev)),
            }

    def restore(self, snap: dict) -> None:
        """Rehydrate sub-states from a prior snapshot (B11 — restart = pause/resume).

        Only known fields are restored; unknown keys are ignored so format drift never crashes.
        """
        if not isinstance(snap, dict):
            return
        with self._lock:
            for section in _SECTIONS:
                data = snap.get(section)
                if not isinstance(data, dict):
                    continue
                obj = getattr(self, section)
                for key, value in data.items():
                    if hasattr(obj, key):
                        setattr(obj, key, value)
            # Preserve continuity of the version counter where available.
            if isinstance(snap.get("version"), int):
                self._version = snap["version"]
            self._updated = time.time()
