"""shared_core - infrastructure shared by both intelligence systems (JARVIS + OMEGA).

Phase A establishes this package and the process-wide EventBus singleton. Nothing else
is moved here yet (non-destructive migration; see omega_context/HYBRID_REPOSITORY_STRUCTURE.md).
"""
from __future__ import annotations

import threading

from .event_bus import EventBus

_bus: EventBus | None = None
_bus_lock = threading.Lock()


def get_bus() -> EventBus:
    """Return the process-wide EventBus singleton (created on first call)."""
    global _bus
    if _bus is None:
        with _bus_lock:
            if _bus is None:
                _bus = EventBus(name="main")
    return _bus


def publish_safe(topic: str, payload: dict | None = None, source: str = "unknown",
                 correlation_id: str | None = None) -> None:
    """Publish to the bus, swallowing ALL errors.

    Used at legacy integration seams so wiring the bus into existing code can never
    break behavior (Implementation Constitution Rule 7 - backward compatibility).
    """
    try:
        get_bus().publish(topic, payload or {}, source=source, correlation_id=correlation_id)
    except Exception:
        pass


__all__ = ["get_bus", "publish_safe", "EventBus"]
