import pytest
from shared_core.tool_registry.registry import ToolRegistry
from shared_core.tool_registry.models import ToolSpec, ToolExecutionResult
from shared_core.tool_registry.gap_model import ToolGapKind
from shared_core.tool_registry.gap_detector import ToolGapDetector

def test_gap_detection_unhandled_intent():
    registry = ToolRegistry()
    registry.register(ToolSpec(
        name="read_file",
        description="Reads a file from disk",
        params_schema={},
        handler=lambda p: ToolExecutionResult(True, {}, None),
        permissions=["read"]
    ))
    
    detector = ToolGapDetector(registry)
    
    # "read config" should map to "read" keyword in "read_file" description/name -> no gap
    gap = detector.detect_intent_gap("read config file")
    assert gap is None
    
    # "deploy server" has no matching keyword in registry -> gap
    gap = detector.detect_intent_gap("deploy server to cloud")
    assert gap is not None
    assert gap.kind == ToolGapKind.UNHANDLED_INTENT
    assert "deploy" in gap.description
    assert gap.suggested_tool_name == "deploy_tool"

def test_gap_detection_repeated_sequence():
    registry = ToolRegistry()
    detector = ToolGapDetector(registry)
    
    history = [
        "git status",
        "git add .",
        "git commit -m 'wip'",
        "pytest",
        "git status",
        "git add .",
        "git commit -m 'wip'",
        "npm start",
        "git status",
        "git add .",
        "git commit -m 'wip'",
    ]
    
    gap = detector.detect_repeated_sequence(history, threshold=3)
    assert gap is not None
    assert gap.kind == ToolGapKind.REPEATED_SEQUENCE
    assert gap.evidence == ["git status", "git add .", "git commit -m 'wip'"]

    short_history = ["git status", "git add ."]
    assert detector.detect_repeated_sequence(short_history) is None
