"""ledger.py - World-State History Ledger (Phase B · BL1-BL3, BL6-BL8).

Records the chronological sequence of prior machine states. Each transition captures a
timestamp, the field that changed, and a snapshot of the retrospective fields the user
requires (active_window, focused_process, cpu, memory, running_terminals,
browser_state_change, clipboard_change, file_modifications, network_summary).

Memory is bounded by a ring buffer (BL3); durability/rolling persistence is delegated to
LedgerStore (BL4/BL5/BL8). Retrospective queries answer: "what was happening N minutes ago?"
(at), "what sequence preceded X?" (between).
"""
from __future__ import annotations

import threading
import time
from collections import deque
from typing import Optional

from .compaction import parse_retention_class

# The retrospective snapshot fields recorded with every transition (BL2).
LEDGER_FIELDS = (
    "active_window",
    "focused_process",
    "cpu",
    "memory",
    "running_terminals",
    "browser_state_change",
    "clipboard_change",
    "file_modifications",
    "network_summary",
)


def empty_snapshot() -> dict:
    """A transition snapshot with all required fields present (BL2)."""
    return {k: None for k in LEDGER_FIELDS}


class HistoryLedger:
    def __init__(self, store=None, maxlen: int = 5000):
        self._ring: deque[dict] = deque(maxlen=maxlen)
        self._store = store
        self._lock = threading.Lock()
        if store is not None:
            # BL8/BC5: rehydrate bounded recent history on construction (restart = continuity).
            try:
                for tr in store.recent(min(maxlen, 100)):
                    self._ring.append(tr)
            except Exception:
                pass

    @property
    def store(self):
        return self._store

    def record(self, change: dict, snapshot: dict, ts: Optional[float] = None, retention_class: Optional[str] = None) -> dict:
        """Append one transition. `change` = {path, old, new}; `snapshot` = retrospective fields."""
        full = empty_snapshot()
        full.update({k: snapshot.get(k) for k in LEDGER_FIELDS if k in snapshot})
        
        rc = parse_retention_class(retention_class).value
        
        transition = {
            "ts": ts if ts is not None else time.time(),
            "change": change,
            "snapshot": full,
            "retention_class": rc,
        }
        with self._lock:
            self._ring.append(transition)          # BL1/BL3: bounded ring
        if self._store is not None:
            try:
                self._store.append(transition)     # BL4: rolling persistence
            except Exception:
                pass
        return transition

    # ── Queries ──────────────────────────────────────────────────────────────
    def recent(self, n: int = 50) -> list[dict]:
        with self._lock:
            return list(self._ring)[-n:]

    def at(self, t: float) -> Optional[dict]:
        """BL6: the transition in effect at time `t` (latest with ts <= t)."""
        with self._lock:
            chosen = None
            for tr in self._ring:
                if tr["ts"] <= t:
                    chosen = tr
                else:
                    break
            return chosen

    def between(self, t0: float, t1: float) -> list[dict]:
        """BL7: ordered transitions in [t0, t1] (e.g. the sequence preceding an error)."""
        lo, hi = (t0, t1) if t0 <= t1 else (t1, t0)
        with self._lock:
            return [tr for tr in self._ring if lo <= tr["ts"] <= hi]

    def minutes_ago(self, minutes: float) -> Optional[dict]:
        """Convenience for 'what was happening N minutes ago?'"""
        return self.at(time.time() - minutes * 60.0)

    def size(self) -> int:
        with self._lock:
            return len(self._ring)

    def diagnostics(self) -> dict:
        """BC6: Operational sizing bounds."""
        import sys
        with self._lock:
            ring_size = len(self._ring)
            mem = sys.getsizeof(self._ring)
            if ring_size > 0:
                mem += sum(sys.getsizeof(r) for r in self._ring)
                
        store_diag = self._store.diagnostics() if self._store else {}
        return {
            "ring_size": ring_size,
            "memory_usage_bytes": mem,
            "store": store_diag
        }

    def close(self) -> None:
        if self._store:
            self._store.close()
