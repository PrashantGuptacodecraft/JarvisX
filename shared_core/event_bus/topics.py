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
PERCEPTION_SYSTEM_DISK = "perception.system.disk"
PERCEPTION_SYSTEM_GPU = "perception.system.gpu"
PERCEPTION_OS_SNAPSHOT = "perception.os.snapshot"
PERCEPTION_SCREEN_OCR = "perception.screen.ocr"
PERCEPTION_SCREEN_UI_TREE = "perception.screen.ui_tree"
PERCEPTION_SCREEN_MEMORY = "perception.screen.memory"
PERCEPTION_VISION_GESTURE = "perception.vision.gesture"
PERCEPTION_VOICE_HEARD = "perception.voice.heard"
PERCEPTION_DEV_FILE_CHANGED = "perception.dev.file_changed"
PERCEPTION_DEV_DIAGNOSTICS = "perception.dev.diagnostics"
PERCEPTION_DEV_PRE_RUN_ASSESSMENT = "perception.dev.pre_run_assessment"
PERCEPTION_DEV_ANALYSIS_COMPLETED = "perception.dev.analysis.completed"
PERCEPTION_DEV_DEPENDENCY_GRAPH_GENERATED = "perception.dev.dependency_graph.generated"
PERCEPTION_DEV_CALL_GRAPH_GENERATED = "perception.dev.call_graph.generated"
PERCEPTION_DEV_ARCHITECTURE_SNAPSHOT_GENERATED = "perception.dev.architecture.snapshot_generated"
PERCEPTION_DEV_ARCHITECTURE_DRIFT_DETECTED = "perception.dev.architecture.drift_detected"
PERCEPTION_DEV_TESTS_COMPLETED = "perception.dev.tests.completed"
PERCEPTION_DEV_BISECTION_COMPLETED = "perception.dev.bisection.completed"
PERCEPTION_DEV_REFACTORING_EVALUATED = "perception.dev.refactoring.evaluated"
PERCEPTION_DEV_SUGGESTIONS_GENERATED = "perception.dev.suggestions.generated"
PERCEPTION_DEV_STYLE_VALIDATION_COMPLETED = "perception.dev.style.validation_completed"
PERCEPTION_DEV_CODING_STYLE_GENERATED = "perception.dev.coding_style.generated"

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

# ── Maintenance ───────────────────────────────────────────────────────────────
MAINTENANCE_COMPACTION_STARTED = "maintenance.compaction.started"
MAINTENANCE_COMPACTION_COMPLETED = "maintenance.compaction.completed"
MAINTENANCE_COMPACTION_SKIPPED = "maintenance.compaction.skipped"
MAINTENANCE_COMPACTION_FAILED = "maintenance.compaction.failed"

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
