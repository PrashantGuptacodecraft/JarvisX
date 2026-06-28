"""bus.py - EventBus: the thread-safe in-process nervous system (Phase A).

Milestones:
  A1 thread-safe publish/subscribe   A2 wildcard subscriptions
  A3 SYNC delivery                   A4 ASYNC delivery
  A5 backpressure (drop-oldest)      A6 coalescing (latest-wins)
  + stats() and drain() for objective validation / deterministic tests.

Design notes
------------
* The subscription registry is guarded by an RLock. publish() snapshots the matching
  subscriptions under the lock, then dispatches OUTSIDE the lock so a slow/sync handler
  never blocks subscribe/unsubscribe or other publishers.
* Payloads should be JSON-serializable (enforced softly in debug via _check_payload).
"""
from __future__ import annotations

import threading
import time
from typing import Callable, Optional

from config.logger import get_logger

from .event import Event
from .subscription import ASYNC, SYNC, Subscription
from .topics import matches

log = get_logger("event_bus")


class EventBus:
    def __init__(self, name: str = "main"):
        self.name = name
        self._subs: list[Subscription] = []
        self._lock = threading.RLock()
        self._published: dict[str, int] = {}   # topic -> count
        self._publish_total = 0

    # ── Subscribe / Unsubscribe (A1, A2) ────────────────────────────────────
    def subscribe(
        self,
        pattern: str,
        handler: Callable[[Event], None],
        mode: str = ASYNC,
        source: str = "subscriber",
        maxlen: int = 256,
        coalesce_key: Optional[Callable[[Event], str]] = None,
    ) -> Subscription:
        """Register a handler for topics matching `pattern`.

        mode=SYNC  -> handler runs inline on the publisher's thread (ordered, low-latency).
        mode=ASYNC -> handler runs on its own worker thread (slow/IO/LLM-safe).
        """
        if mode not in (SYNC, ASYNC):
            raise ValueError(f"invalid delivery mode: {mode!r}")
        sub = Subscription(
            pattern=pattern, handler=handler, mode=mode,
            source=source, maxlen=maxlen, coalesce_key=coalesce_key,
        )
        with self._lock:
            self._subs.append(sub)
        log.debug(f"[bus] +sub {source} '{pattern}' ({mode})")
        return sub

    def unsubscribe(self, sub: Subscription) -> None:
        with self._lock:
            if sub in self._subs:
                self._subs.remove(sub)
        sub.close()
        log.debug(f"[bus] -sub {sub.source} '{sub.pattern}'")

    # ── Publish (A1, A3, A4) ─────────────────────────────────────────────────
    def publish(
        self,
        topic: str,
        payload: Optional[dict] = None,
        source: str = "unknown",
        correlation_id: Optional[str] = None,
    ) -> Event:
        """Publish an event to all matching subscriptions. Returns the Event."""
        event = Event(
            topic=topic,
            payload=payload or {},
            source=source,
            correlation_id=correlation_id,
        )
        _check_payload(event)
        with self._lock:
            self._published[topic] = self._published.get(topic, 0) + 1
            self._publish_total += 1
            targets = [s for s in self._subs if matches(s.pattern, topic)]
        # Dispatch outside the lock.
        for sub in targets:
            if sub.mode == SYNC:
                sub.deliver_sync(event)
            else:
                sub.enqueue(event)
        return event

    # ── Introspection (A5/A6 validation) ─────────────────────────────────────
    def stats(self) -> dict:
        with self._lock:
            subs = list(self._subs)
            published = dict(self._published)
            total = self._publish_total
        return {
            "published_total": total,
            "published_by_topic": published,
            "subscriptions": [s.stats() for s in subs],
            "drops_total": sum(s.stats()["dropped"] for s in subs),
        }

    def subscription_count(self) -> int:
        with self._lock:
            return len(self._subs)

    # ── drain (deterministic tests) ──────────────────────────────────────────
    def drain(self, timeout: float = 5.0) -> bool:
        """Block until every async buffer is empty and no handler is busy.

        Returns True if fully drained within `timeout`, else False.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._lock:
                subs = list(self._subs)
            if all(s.is_idle() for s in subs):
                # double-check after a beat to avoid a race with in-flight enqueues
                time.sleep(0.01)
                with self._lock:
                    subs = list(self._subs)
                if all(s.is_idle() for s in subs):
                    return True
            time.sleep(0.005)
        return False

    def shutdown(self) -> None:
        with self._lock:
            subs = list(self._subs)
            self._subs.clear()
        for s in subs:
            s.close()


def _check_payload(event: Event) -> None:
    """Soft guard: warn (debug) if a payload is not a JSON-serializable dict.

    Kept cheap and non-fatal so it never breaks runtime; it only flags drift during dev.
    """
    if not isinstance(event.payload, dict):
        log.debug(f"[bus] payload for {event.topic} is not a dict: {type(event.payload)}")
