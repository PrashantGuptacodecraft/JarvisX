"""event.py - The immutable Event record carried by the bus.

Phase A · supports milestones A1-A8. Payloads MUST be JSON-serializable so events can
later be journaled (Phase B continuity) and crossed over process boundaries. No live object
references in payloads.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class Event:
    """A single fact published onto the bus.

    Attributes
    ----------
    topic:          dotted topic string, e.g. "perception.os.active_window".
    payload:        JSON-serializable dict of event data.
    source:         publisher id, e.g. "core_loop" / "context_watcher".
    ts:             wall-clock timestamp (time.time()) at publish.
    mono:           monotonic timestamp (time.monotonic()) for reliable ordering.
    id:             unique event id (uuid4 hex).
    correlation_id: optional id tying a request->result chain (e.g. a turn token).
    """

    topic: str
    payload: dict
    source: str = "unknown"
    ts: float = field(default_factory=time.time)
    mono: float = field(default_factory=time.monotonic)
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    correlation_id: Optional[str] = None

    def as_dict(self) -> dict[str, Any]:
        """Flat dict form (used by the journal / future serialization)."""
        return {
            "topic": self.topic,
            "payload": self.payload,
            "source": self.source,
            "ts": self.ts,
            "mono": self.mono,
            "id": self.id,
            "correlation_id": self.correlation_id,
        }
