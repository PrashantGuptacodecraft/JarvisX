import pytest
import time
from pathlib import Path

from shared_core.dev_tools import (
    ExecutionRequest, ExecutionTarget, ExecutionKind, PreRunDecision,
    DiagnosticsEvidenceStore, PreRunPredictor, PreRunContext,
    ExecutionStructurePredictor, PythonSyntaxPredictor, D7DiagnosticsPredictor,
    ExecutionGateway
)
from shared_core.event_bus import EventBus

class MockEventBus(EventBus):
    def __init__(self):
        super().__init__()
        self.emitted = []
        
    def publish(self, topic: str, data: dict):
        if topic == "perception.dev.pre_run_assessment":
            self.emitted.append(data)
        super().publish(topic, data)

@pytest.fixture
def workspace(tmp_path):
    (tmp_path / "valid.py").write_text("def foo():\n    pass")
    (tmp_path / "syntax_error.py").write_text("def foo(\n    pass")
    (tmp_path / "indent_error.py").write_text("def foo():\npass")
    
    (tmp_path / "other_dir").mkdir()
    return tmp_path

def test_python_valid_file(workspace):
    bus = MockEventBus()
    store = DiagnosticsEvidenceStore(bus)
    gw = ExecutionGateway(
        workspace, bus, store,
        [ExecutionStructurePredictor(), PythonSyntaxPredictor(), D7DiagnosticsPredictor()]
    )
    
    req = ExecutionRequest(
        request_id="req1",
        execution_kind=ExecutionKind.TERMINAL.value,
        target=ExecutionTarget(language=None, path="valid.py", working_directory=".", inline_code_sha256=None)
    )
    
    executor_called = False
    def mock_executor():
        nonlocal executor_called
        executor_called = True
        return "success"
        
    res = gw.execute(req, mock_executor)
    
    assert executor_called
    assert res == "success"
    
    assert len(bus.emitted) == 1
    assessment = bus.emitted[0]
    assert assessment["decision"] == "allow"
    assert assessment["execution_permitted"] is True

def test_python_syntax_error(workspace):
    bus = MockEventBus()
    store = DiagnosticsEvidenceStore(bus)
    gw = ExecutionGateway(
        workspace, bus, store,
        [ExecutionStructurePredictor(), PythonSyntaxPredictor(), D7DiagnosticsPredictor()]
    )
    
    req = ExecutionRequest(
        request_id="req2",
        execution_kind=ExecutionKind.CODE_SANDBOX.value,
        target=ExecutionTarget(language="python", path="syntax_error.py", working_directory=".", inline_code_sha256=None)
    )
    
    executor_called = False
    def mock_executor():
        nonlocal executor_called
        executor_called = True
        return "success"
        
    res = gw.execute(req, mock_executor)
    
    assert not executor_called
    assert isinstance(res, dict)
    assert res["status"] == "blocked"
    
    assert len(bus.emitted) == 1
    assessment = bus.emitted[0]
    assert assessment["decision"] == "block"
    assert assessment["execution_permitted"] is False
    assert len(assessment["findings"]) == 1
    assert assessment["findings"][0]["code"] == "PYTHON_SYNTAX_ERROR"
    assert assessment["findings"][0]["blocks_execution"] is True

def test_missing_target(workspace):
    bus = MockEventBus()
    store = DiagnosticsEvidenceStore(bus)
    gw = ExecutionGateway(
        workspace, bus, store,
        [ExecutionStructurePredictor()]
    )
    
    req = ExecutionRequest(
        request_id="req3",
        execution_kind=ExecutionKind.TERMINAL.value,
        target=ExecutionTarget(language=None, path="missing.py", working_directory=".", inline_code_sha256=None)
    )
    
    res = gw.execute(req, lambda: "success")
    assert res["status"] == "blocked"
    
    assert len(bus.emitted) == 1
    assessment = bus.emitted[0]
    assert assessment["decision"] == "block"
    assert assessment["findings"][0]["code"] == "EXECUTION_TARGET_NOT_FOUND"

def test_workspace_violation(workspace):
    bus = MockEventBus()
    store = DiagnosticsEvidenceStore(bus)
    gw = ExecutionGateway(
        workspace, bus, store,
        [ExecutionStructurePredictor()]
    )
    
    req = ExecutionRequest(
        request_id="req4",
        execution_kind=ExecutionKind.TERMINAL.value,
        target=ExecutionTarget(language=None, path="../outside.py", working_directory=".", inline_code_sha256=None)
    )
    
    res = gw.execute(req, lambda: "success")
    assert res["status"] == "blocked"
    assert bus.emitted[0]["findings"][0]["code"] == "TARGET_OUTSIDE_WORKSPACE"

def test_d7_diagnostics_integration(workspace):
    bus = MockEventBus()
    store = DiagnosticsEvidenceStore(bus)
    store.start()
    
    # Inject D7 snapshot
    bus.publish("perception.dev.diagnostics", {
        "schema_version": 1,
        "completed_at": "now",
        "diagnostics": [
            {
                "path": "valid.py",
                "severity": "error",
                "message": "Some type error"
            }
        ]
    })
    
    time.sleep(0.1) # let async bus process
    
    gw = ExecutionGateway(
        workspace, bus, store,
        [D7DiagnosticsPredictor()]
    )
    
    req = ExecutionRequest(
        request_id="req5",
        execution_kind=ExecutionKind.TERMINAL.value,
        target=ExecutionTarget(language=None, path="valid.py", working_directory=".", inline_code_sha256=None)
    )
    
    res = gw.execute(req, lambda: "success")
    assert res == "success" # D7 errors do NOT automatically block
    
    assessment = bus.emitted[-1] # -1 because the diagnostics was also on bus but not pre_run
    assert assessment["decision"] == "warn"
    assert assessment["findings"][0]["severity"] == "warning"
    assert assessment["findings"][0]["code"] == "D7_STATIC_DIAGNOSTIC"
    
    store.stop()

def test_inline_code_sha256(workspace):
    bus = MockEventBus()
    store = DiagnosticsEvidenceStore(bus)
    gw = ExecutionGateway(
        workspace, bus, store,
        [PythonSyntaxPredictor()]
    )
    
    req = ExecutionRequest(
        request_id="req6",
        execution_kind=ExecutionKind.CODE_SANDBOX.value,
        inline_code="print('hello')",
        target=ExecutionTarget(language="python", path=None, working_directory=".", inline_code_sha256=None)
    )
    
    gw.execute(req, lambda: "success")
    
    assessment = bus.emitted[0]
    assert assessment["decision"] == "allow"
    assert assessment["target"]["inline_code_sha256"] is not None
    assert assessment["target"]["inline_code_sha256"] != "print('hello')"

def test_unsupported_language_not_analyzed(workspace):
    bus = MockEventBus()
    store = DiagnosticsEvidenceStore(bus)
    gw = ExecutionGateway(
        workspace, bus, store,
        [ExecutionStructurePredictor()]
    )
    
    req = ExecutionRequest(
        request_id="req7",
        execution_kind=ExecutionKind.CODE_SANDBOX.value,
        target=ExecutionTarget(language="ruby", path=None, working_directory=".", inline_code_sha256=None)
    )
    
    res = gw.execute(req, lambda: "success")
    assert res == "success"
    
    assessment = bus.emitted[0]
    assert assessment["decision"] == "allow" # Because ExecutionStructurePredictor 'completed', allowing it
    assert len(assessment["findings"]) == 1
    assert assessment["findings"][0]["code"] == "LANGUAGE_NOT_ANALYZED"
    assert assessment["findings"][0]["severity"] == "information"
