"""topics.py - Canonical topic taxonomy + matching (milestone A2: wildcard subscriptions).

Topics are dotted strings. Subscriptions may use:
  * exact match:        "action.result"
  * prefix wildcard:    "perception.*"  matches "perception.os.x", "perception.screen.y"
  * nested prefix:      "perception.os.*" matches "perception.os.snapshot"
  * catch-all:          "*"             matches everything

Using the constants below (instead of raw strings) prevents stringly-typed drift.
"""
from __future__ import annotations

# ── Perception ────────────────────────────────────────────────────────────────
PERCEPTION = "perception"
PERCEPTION_OS_ACTIVE_WINDOW = "perception.os.active_window"
PERCEPTION_OS_SNAPSHOT = "perception.os.snapshot"
PERCEPTION_SCREEN_OCR = "perception.screen.ocr"
PERCEPTION_SCREEN_UI_TREE = "perception.screen.ui_tree"
PERCEPTION_SCREEN_MEMORY = "perception.screen.memory"
PERCEPTION_VISION_GESTURE = "perception.vision.gesture"
PERCEPTION_VOICE_HEARD = "perception.voice.heard"
PERCEPTION_DEV_FILE_CHANGED = "perception.dev.file_changed"
PERCEPTION_DEV_DIAGNOSTICS = "perception.dev.diagnostics"

# ── Cognition ─────────────────────────────────────────────────────────────────
COGNITION_INTENT = "cognition.intent"
COGNITION_PLAN = "cognition.plan"
COGNITION_REQUEST = "cognition.request"
COGNITION_RESULT = "cognition.result"
COGNITION_TRACE = "cognition.trace"

# ── Action ────────────────────────────────────────────────────────────────────
ACTION_REQUEST = "action.request"
ACTION_RESULT = "action.result"
ACTION_ERROR = "action.error"

# ── Memory ────────────────────────────────────────────────────────────────────
MEMORY_WRITE = "memory.write"
MEMORY_QUERY = "memory.query"
MEMORY_KG_UPDATE = "memory.kg.update"

# ── Prediction ────────────────────────────────────────────────────────────────
PREDICT_SUGGESTION = "predict.suggestion"
PREDICT_PRELOAD = "predict.preload"

# ── System / Tooling ──────────────────────────────────────────────────────────
SYSTEM_HEALTH = "system.health"
SYSTEM_LIFECYCLE = "system.lifecycle"
SYSTEM_CONFIG = "system.config"
TOOL_CREATED = "tool.created"
TOOL_INVOKED = "tool.invoked"

# Catch-all pattern
ALL = "*"


def matches(pattern: str, topic: str) -> bool:
    """Return True if `topic` matches `pattern` (see module docstring for rules)."""
    if pattern == ALL:
        return True
    if pattern == topic:
        return True
    if pattern.endswith(".*"):
        # prefix includes the trailing dot: "perception.*" -> "perception."
        prefix = pattern[:-1]
        return topic.startswith(prefix)
    return False
