import pytest
import subprocess
import os
from pathlib import Path
from shared_core.dev_tools.regression_bisection import RegressionBisector, BisectionRequest

@pytest.fixture
def git_repo(tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    
    # Init git
    subprocess.run(["git", "init"], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=str(repo_dir), check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(repo_dir), check=True)
    
    script_path = repo_dir / "math_funcs.py"
    test_path = repo_dir / "test_math.py"
    
    # Commit 1: Good
    script_path.write_text("def add(a, b):\n    return a + b\n")
    test_path.write_text("from math_funcs import add\ndef test_add():\n    assert add(2, 3) == 5\n")
    subprocess.run(["git", "add", "."], cwd=str(repo_dir), check=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=str(repo_dir), check=True)
    
    # Commit 2: Good
    script_path.write_text("def add(a, b):\n    return a + b\ndef sub(a, b):\n    return a - b\n")
    subprocess.run(["git", "add", "."], cwd=str(repo_dir), check=True)
    subprocess.run(["git", "commit", "-m", "Add sub"], cwd=str(repo_dir), check=True)
    
    # Commit 3: Bad (introduces bug in add)
    script_path.write_text("def add(a, b):\n    return a - b\ndef sub(a, b):\n    return a - b\n")
    subprocess.run(["git", "add", "."], cwd=str(repo_dir), check=True)
    subprocess.run(["git", "commit", "-m", "Introduce bug"], cwd=str(repo_dir), check=True)
    
    bad_commit_hash = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(repo_dir), capture_output=True, text=True).stdout.strip()
    
    # Commit 4: Bad (but not the root cause)
    script_path.write_text("def add(a, b):\n    return a - b\ndef sub(a, b):\n    return a - b\ndef mul(a, b):\n    return a * b\n")
    subprocess.run(["git", "add", "."], cwd=str(repo_dir), check=True)
    subprocess.run(["git", "commit", "-m", "Add mul"], cwd=str(repo_dir), check=True)
    
    return repo_dir, bad_commit_hash

from shared_core.event_bus import EventBus
from shared_core.dev_tools.diagnostics_evidence import DiagnosticsEvidenceStore
from shared_core.dev_tools.execution_gateway import ExecutionGateway

class MockEventBus(EventBus):
    def publish(self, topic: str, data: dict): pass

def test_bisector_finds_bad_commit(git_repo):
    repo_dir, bad_commit_hash = git_repo
    
    bus = MockEventBus()
    store = DiagnosticsEvidenceStore(bus)
    gw = ExecutionGateway(str(repo_dir), bus, store, [])
    
    bisector = RegressionBisector(gw)
    req = BisectionRequest(
        repository_root=str(repo_dir),
        test_command=["python", "-m", "pytest", "test_math.py"],
        max_lookback=10
    )
    
    res = bisector.execute(req)
    print(f"Bisection result log: {res.log}")
    
    assert res.status == "success"
    assert res.culprit_commit == bad_commit_hash
    assert res.commit_message == "Introduce bug"
