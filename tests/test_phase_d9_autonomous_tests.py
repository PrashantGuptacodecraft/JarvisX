import pytest
import time
from pathlib import Path
from unittest.mock import Mock

from shared_core.dev_tools.test_execution_model import (
    TestFramework, TestExecutionStatus, TestExecutionRequest
)
from shared_core.dev_tools.test_framework_detection import TestFrameworkDetector
from shared_core.dev_tools.autonomous_test_runner import AutonomousTestRunner
from shared_core.dev_tools.execution_gateway import ExecutionGateway
from shared_core.event_bus import EventBus
from shared_core.dev_tools.diagnostics_evidence import DiagnosticsEvidenceStore
from shared_core.dev_tools.pre_run_predictor import ExecutionStructurePredictor

class MockEventBus(EventBus):
    def publish(self, topic: str, data: dict):
        pass

@pytest.fixture
def workspace(tmp_path):
    (tmp_path / "valid.py").write_text("def foo():\n    pass")
    return tmp_path

def test_detect_pytest(workspace):
    (workspace / "pytest.ini").write_text("[pytest]\n")
    detector = TestFrameworkDetector()
    res = detector.detect(workspace)
    assert res.framework == TestFramework.PYTEST.value
    assert res.command == ["python", "-m", "pytest"]
    assert not res.is_ambiguous

def test_detect_unittest(workspace):
    tests_dir = workspace / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_foo.py").write_text("import unittest\nclass T(unittest.TestCase):\n    pass")
    
    detector = TestFrameworkDetector()
    res = detector.detect(workspace)
    assert res.framework == TestFramework.UNITTEST.value
    assert res.command == ["python", "-m", "unittest", "discover", "-s", "tests"]
    assert not res.is_ambiguous

def test_detect_ambiguous(workspace):
    detector = TestFrameworkDetector()
    res = detector.detect(workspace)
    assert res.framework == TestFramework.UNKNOWN.value
    assert res.command == []
    assert res.is_ambiguous

def test_runner_executes_through_gateway(workspace):
    bus = MockEventBus()
    store = DiagnosticsEvidenceStore(bus)
    # Give it no predictors so it always allows
    gw = ExecutionGateway(workspace, bus, store, [])
    
    runner = AutonomousTestRunner(gw)
    
    # We create a dummy test file
    (workspace / "test_dummy.py").write_text("def test_ok():\n    assert True\n")
    (workspace / "pytest.ini").write_text("[pytest]\n")
    
    req = TestExecutionRequest(
        request_id="req1",
        repository_root=str(workspace),
        selected_framework=TestFramework.PYTEST.value,
        selected_command=["python", "-m", "pytest", "test_dummy.py"],
        working_directory=str(workspace),
        timeout_seconds=5
    )
    
    res = runner.execute(req)
    assert res.execution_status == TestExecutionStatus.SUCCESS.value
    assert res.passed_count == 1
    assert res.failed_count == 0

def test_runner_blocked_by_gateway(workspace):
    bus = MockEventBus()
    store = DiagnosticsEvidenceStore(bus)
    # The ExecutionStructurePredictor blocks invalid working directories
    gw = ExecutionGateway(workspace, bus, store, [ExecutionStructurePredictor()])
    
    runner = AutonomousTestRunner(gw)
    
    req = TestExecutionRequest(
        request_id="req2",
        repository_root=str(workspace),
        selected_framework=TestFramework.PYTEST.value,
        selected_command=["python", "-m", "pytest"],
        working_directory="invalid_dir", # this will trigger a block
        timeout_seconds=5
    )
    
    res = runner.execute(req)
    assert res.execution_status == TestExecutionStatus.BLOCKED.value
    assert res.passed_count == 0
    assert "Execution blocked" in res.stderr
