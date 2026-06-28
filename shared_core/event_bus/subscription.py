"""subscription.py - A single subscription + its async delivery buffer.

Covers:
  A3  SYNC delivery  - handler runs inline on the publisher thread (no buffer/worker).
  A4  ASYNC delivery - handler runs on a dedicated worker thread fed by a bounded buffer.
  A5  Backpressure   - buffer is bounded; overflow drops the OLDEST and counts the drop.
  A6  Coalescing     - with a coalesce_key, a newer event REPLACES the unprocessed older one
                       for that key (latest-wins), so consumers never see a stale backlog.
"""
from __future__ import annotations

import threading
from collections import OrderedDict, deque
from typing import Callable, Optional

from config.logger import get_logger

from .event import Event

log = get_logger("event_bus")

SYNC = "sync"
ASYNC = "async"


class _BoundedBuffer:
    """Thread-safe bounded buffer with drop-oldest overflow and optional coalescing."""

    def __init__(self, maxlen: int, coalesce_key: Optional[Callable[[Event], str]]):
        self._maxlen = max(1, int(maxlen))
        self._coalesce_key = coalesce_key
        self._cond = threading.Condition()
        self._closed = False
        # Non-coalescing path: a plain FIFO deque.
        self._dq: deque[Event] = deque()
        # Coalescing path: key -> latest Event, insertion-ordered (FIFO over keys).
        self._coalesced: "OrderedDict[str, Event]" = OrderedDict()
        self.dropped = 0      # events discarded by overflow
        self.coalesced = 0    # events superseded by a newer same-key event

    def put(self, event: Event) -> None:
        with self._cond:
            if self._closed:
                return
            if self._coalesce_key is not None:
                key = self._coalesce_key(event)
                if key in self._coalesced:
                    self._coalesced[key] = event   # latest-wins, no growth
                    self.coalesced += 1
                else:
                    if len(self._coalesced) >= self._maxlen:
                        self._coalesced.popitem(last=False)  # drop oldest key
                        self.dropped += 1
                    self._coalesced[key] = event
            else:
                if len(self._dq) >= self._maxlen:
                    self._dq.popleft()               # drop oldest
                    self.dropped += 1
                self._dq.append(event)
            self._cond.notify()

    def get(self, timeout: float = 0.2) -> Optional[Event]:
        """Block up to `timeout` for the next event; return None on timeout/close."""
        with self._cond:
            if not self._has_items() and not self._closed:
                self._cond.wait(timeout)
            if self._coalesce_key is not None:
                if self._coalesced:
                    _key, ev = self._coalesced.popitem(last=False)
                    return ev
                return None
            if self._dq:
                return self._dq.popleft()
            return None

    def _has_items(self) -> bool:
        return bool(self._coalesced) if self._coalesce_key is not None else bool(self._dq)

    def pending(self) -> int:
        with self._cond:
            return len(self._coalesced) if self._coalesce_key is not None else len(self._dq)

    def close(self) -> None:
        with self._cond:
            self._closed = True
            self._cond.notify_all()


class Subscription:
    """Handle returned by EventBus.subscribe(); also drives async delivery."""

    def __init__(
        self,
        pattern: str,
        handler: Callable[[Event], None],
        mode: str = ASYNC,
        source: str = "subscriber",
        maxlen: int = 256,
        coalesce_key: Optional[Callable[[Event], str]] = None,
    ):
        self.pattern = pattern
        self.handler = handler
        self.mode = mode
        self.source = source
        self.delivered = 0
        self._busy = False
        self._buffer: Optional[_BoundedBuffer] = None
        self._worker: Optional[threading.Thread] = None
        self._running = False
        if mode == ASYNC:
            self._buffer = _BoundedBuffer(maxlen, coalesce_key)
            self._running = True
            self._worker = threading.Thread(
                target=self._worker_loop, name=f"bus-sub-{source}", daemon=True
            )
            self._worker.start()

    # ── SYNC path (called inline by publisher) ──────────────────────────────
    def deliver_sync(self, event: Event) -> None:
        self._busy = True
        try:
            self.handler(event)
            self.delivered += 1
        except Exception as exc:  # one bad handler must not break the publisher
            log.error(f"[bus] sync handler '{self.source}' error on {event.topic}: {exc}")
        finally:
            self._busy = False

    # ── ASYNC path (enqueue; worker delivers) ───────────────────────────────
    def enqueue(self, event: Event) -> None:
        if self._buffer is not None:
            self._buffer.put(event)

    def _worker_loop(self) -> None:
        assert self._buffer is not None
        while self._running:
            event = self._buffer.get(timeout=0.2)
            if event is None:
                continue
            self._busy = True
            try:
                self.handler(event)
                self.delivered += 1
            except Exception as exc:
                log.error(f"[bus] async handler '{self.source}' error on {event.topic}: {exc}")
            finally:
                self._busy = False

    # ── Introspection / lifecycle ───────────────────────────────────────────
    def is_idle(self) -> bool:
        if self.mode == SYNC:
            return not self._busy
        return (self._buffer is None or self._buffer.pending() == 0) and not self._busy

    def stats(self) -> dict:
        buf = self._buffer
        return {
            "pattern": self.pattern,
            "source": self.source,
            "mode": self.mode,
            "delivered": self.delivered,
            "pending": buf.pending() if buf else 0,
            "dropped": buf.dropped if buf else 0,
            "coalesced": buf.coalesced if buf else 0,
        }

    def close(self) -> None:
        self._running = False
        if self._buffer is not None:
            self._buffer.close()
