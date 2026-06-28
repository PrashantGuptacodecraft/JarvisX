"""coalescer.py - event coalescing interface (Phase B · B5 hook for B12 burst handling).

INTERFACE ONLY. Full burst-handling tuning is deferred to B12. The seam lets a future
backpressure layer attach a coalescer to the scheduler so that, e.g., 500 `mouse_move` events
collapse into 1 aggregated event — without redesigning the scheduler.
"""
from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from collections import defaultdict, deque


class Coalescer(ABC):
    """Collapse many same-key items into a single aggregate. Implementations MUST be bounded."""

    @abstractmethod
    def add(self, key: str, item) -> None:
        ...

    @abstractmethod
    def flush(self) -> list:
        """Return aggregated items (one per key) and clear the buffer."""
        ...


class CountingCoalescer(Coalescer):
    """Default bounded coalescer: groups items by key, aggregates to {key, count, last}.

    Per-key buffer is a bounded deque so a burst can never grow memory without limit
    (overload protection groundwork for B12).
    """

    def __init__(self, per_key_max: int = 1000):
        self._buf: dict[str, deque] = defaultdict(lambda: deque(maxlen=per_key_max))
        self._lock = threading.Lock()
        self.dropped = 0

    def add(self, key: str, item) -> None:
        with self._lock:
            dq = self._buf[key]
            if len(dq) >= dq.maxlen:
                self.dropped += 1   # bounded: oldest evicted by deque
            dq.append(item)

    def flush(self) -> list:
        with self._lock:
            out = [{"key": k, "count": len(dq), "last": dq[-1]} for k, dq in self._buf.items() if dq]
            self._buf.clear()
            return out

    def depth(self) -> int:
        with self._lock:
            return sum(len(dq) for dq in self._buf.values())
