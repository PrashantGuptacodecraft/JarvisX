"""journal.py - Optional event journaling hook (interface seed for Phase B continuity).

OFF by default in Phase A. It is just a normal bus subscriber that records events on a
topic whitelist into an in-memory ring buffer (and, later, the persistence layer). Phase B
will enable it for state replay / "restart = pause". Kept here so the interface exists now
without expanding scope.
"""
from __future__ import annotations

from collections import deque
from typing import Iterable, Optional

from .event import Event
from .subscription import ASYNC


class EventJournal:
    def __init__(self, bus, patterns: Optional[Iterable[str]] = None, maxlen: int = 1000):
        self._bus = bus
        self._ring: deque[dict] = deque(maxlen=maxlen)
        self._subs = []
        patterns = list(patterns) if patterns else []
        for p in patterns:
            self._subs.append(
                bus.subscribe(p, self._record, mode=ASYNC, source="journal", maxlen=maxlen)
            )

    def _record(self, event: Event) -> None:
        self._ring.append(event.as_dict())

    def recent(self, n: int = 50) -> list[dict]:
        return list(self._ring)[-n:]

    def stop(self) -> None:
        for s in self._subs:
            self._bus.unsubscribe(s)
        self._subs.clear()
