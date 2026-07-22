"""compaction.py - State Compaction Policy classification (Phase B · BC1).

Defines retention classes and deterministic classification rules.
"""
from __future__ import annotations

from enum import Enum
from typing import Any


class RetentionClass(str, Enum):
    EPHEMERAL = "EPHEMERAL"
    DEFAULT = "DEFAULT"
    SIGNIFICANT = "SIGNIFICANT"


TTL_SECONDS = {
    RetentionClass.EPHEMERAL: 6 * 3600,         # 6 hours
    RetentionClass.DEFAULT: 7 * 24 * 3600,      # 7 days
    RetentionClass.SIGNIFICANT: 30 * 24 * 3600, # 30 days
}


def classify(topic: str, payload: Any = None) -> RetentionClass:
    """Deterministic event classification using prefix-aware matching."""
    if not isinstance(topic, str) or not topic:
        return RetentionClass.DEFAULT

    topic_lower = topic.lower()

    # SIGNIFICANT: action results, scheduler failures, command execution, tool invocation
    sig_prefixes = (
        "action.",
        "scheduler.fail",
        "command.",
        "tool.",
        "error.",
        "system.fail",
    )
    if any(topic_lower.startswith(p) for p in sig_prefixes) or "error" in topic_lower or "fail" in topic_lower:
        return RetentionClass.SIGNIFICANT

    # EPHEMERAL: active-window changes, mouse/transient input, high-frequency CPU/memory
    eph_prefixes = (
        "perception.os.active_window",
        "screen.active_window",
        "perception.mouse",
        "perception.system.cpu",
        "system.cpu",
        "perception.system.memory",
        "system.memory",
        "perception.noise",
    )
    if any(topic_lower.startswith(p) for p in eph_prefixes):
        return RetentionClass.EPHEMERAL

    # DEFAULT: every unclassified event
    return RetentionClass.DEFAULT


def parse_retention_class(val: Any) -> RetentionClass:
    """Safely parse an unknown value into a RetentionClass, falling back to DEFAULT."""
    if isinstance(val, RetentionClass):
        return val
    if isinstance(val, str):
        val_upper = val.upper()
        if val_upper in RetentionClass.__members__:
            return RetentionClass(val_upper)
    return RetentionClass.DEFAULT
