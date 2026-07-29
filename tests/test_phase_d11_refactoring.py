import pytest
import os
from pathlib import Path

from shared_core.dev_tools.refactoring_engine import RefactoringEngine, RefactoringRequest, RefactoringOperation
from shared_core.dev_tools.execution_gateway import ExecutionGateway
from shared_core.dev_tools.autonomous_test_runner import AutonomousTestRunner
from shared_core.event_bus import EventBus
from shared_core.dev_tools.diagnostics_evidence import DiagnosticsEvidenceStore

class MockEventBus(EventBus):
    def publish(self, topic: str, data: dict): pass

@pytest.fixture
def workspace(tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    
    # Create valid target
    (repo_dir / "target.py").write_text("def old_func():\n    return 42\n")
    # Create test that expects old_func
    (repo_dir / "test_target.py").write_text("from target import old_func\ndef test_old():\n    assert old_func() == 42\n")
    
    return repo_dir

def test_refactoring_rollbacks_on_test_failure(workspace):
    bus = MockEventBus()
    store = DiagnosticsEvidenceStore(bus)
    gw = ExecutionGateway(str(workspace), bus, store, [])
    runner = AutonomousTestRunner(gw)
    engine = RefactoringEngine(gw, runner)
    
    req = RefactoringRequest(
        repository_root=str(workspace),
        target_file="target.py",
        operation=RefactoringOperation.RENAME,
        target_symbol="old_func",
        new_name="new_func",
        test_command=["python", "-m", "pytest", "test_target.py", "-q"]
    )
    
    res = engine.execute(req)
    
    # Tests will fail because test_target.py still imports old_func
    assert not res.success
    assert "Tests failed. Refactoring rolled back." in res.status
    
    # Ensure rollback happened
    content = (workspace / "target.py").read_text()
    assert "def old_func():" in content

def test_refactoring_commits_on_test_pass(workspace):
    bus = MockEventBus()
    store = DiagnosticsEvidenceStore(bus)
    gw = ExecutionGateway(str(workspace), bus, store, [])
    runner = AutonomousTestRunner(gw)
    engine = RefactoringEngine(gw, runner)
    
    # Fix the test so it doesn't fail on rename
    (workspace / "test_target.py").write_text("from target import new_func\ndef test_new():\n    assert new_func() == 42\n")
    
    req = RefactoringRequest(
        repository_root=str(workspace),
        target_file="target.py",
        operation=RefactoringOperation.RENAME,
        target_symbol="old_func",
        new_name="new_func",
        test_command=["python", "-m", "pytest", "test_target.py", "-q"]
    )
    
    res = engine.execute(req)
    
    # Tests will pass
    assert res.success
    assert "Tests passed. Refactoring applied." in res.status
    
    # Ensure change stayed
    content = (workspace / "target.py").read_text()
    assert "def new_func():" in content
