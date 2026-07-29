import pytest
import time
import json
from pathlib import Path
from unittest.mock import patch

from shared_core.dev_tools import (
    DiagnosticsConfig, RuffDiagnosticProvider, PyrightDiagnosticProvider,
    DiagnosticsAnalyzer, DiagnosticsCoordinator, DiagnosticsSnapshotStatus,
    DiagnosticExecutionStatus
)
from shared_core.event_bus import EventBus

class MockEventBus(EventBus):
    def __init__(self):
        super().__init__()
        self.emitted = []
        
    def publish(self, topic: str, data: dict):
        if topic == "perception.dev.diagnostics":
            self.emitted.append(data)
        super().publish(topic, data)

class MockProc:
    def __init__(self, stdout, returncode):
        self.stdout = stdout
        self.returncode = returncode

@pytest.fixture
def ruff_json():
    return json.dumps([
        {
            "filename": "test.py",
            "message": "Undefined name `example`",
            "code": "F821",
            "location": {"row": 11, "column": 5},
            "end_location": {"row": 11, "column": 12},
            "fix": None,
            "severity": "error"
        },
        {
            "filename": "test.py",
            "message": "Line too long",
            "code": "E501",
            "location": {"row": 1, "column": 80},
            "end_location": {"row": 1, "column": 85},
            "fix": {"message": "Wrap line"},
            # missing severity, should default to warning
        }
    ])

@pytest.fixture
def pyright_json():
    return json.dumps({
        "version": "1.1.300",
        "generalDiagnostics": [
            {
                "file": "test.py",
                "severity": "error",
                "message": "Type mismatch",
                "rule": "reportGeneralTypeIssues",
                "range": {
                    "start": {"line": 10, "character": 4},
                    "end": {"line": 10, "character": 11}
                }
            }
        ]
    })

def test_ruff_normalization(tmp_path, ruff_json):
    provider = RuffDiagnosticProvider(["ruff"], 1.0, 1024)
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MockProc(ruff_json, 1)
        res = provider.collect(tmp_path, ("test.py",))
        
        assert len(res.diagnostics) == 2
        d1 = res.diagnostics[0]
        assert d1.severity == "error"
        assert d1.code == "F821"
        assert d1.range.start.line == 10
        assert d1.range.start.character == 4
        assert not d1.fix.available
        
        d2 = res.diagnostics[1]
        assert d2.severity == "warning"
        assert d2.fix.available
        assert d2.fix.applicability == "safe"
        
        assert res.tool_result.status == "completed"

def test_pyright_normalization(tmp_path, pyright_json):
    provider = PyrightDiagnosticProvider(["pyright"], 1.0, 1024)
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MockProc(pyright_json, 1)
        res = provider.collect(tmp_path, ("test.py",))
        
        assert len(res.diagnostics) == 1
        d = res.diagnostics[0]
        assert d.severity == "error"
        assert d.range.start.line == 10
        assert d.range.start.character == 4
        assert d.code == "reportGeneralTypeIssues"
        
def test_diagnostics_analyzer_dedup_and_sort(tmp_path, ruff_json, pyright_json):
    (tmp_path / "test.py").touch()
    ruff = RuffDiagnosticProvider(["ruff"], 1.0, 1024)
    pyright = PyrightDiagnosticProvider(["pyright"], 1.0, 1024)
    
    analyzer = DiagnosticsAnalyzer(DiagnosticsConfig(workspace_root=str(tmp_path)), [ruff, pyright])
    
    with patch("subprocess.run") as mock_run:
        # First call ruff, second call pyright
        mock_run.side_effect = [MockProc(ruff_json, 1), MockProc(pyright_json, 1)]
        snap = analyzer.analyze("manual", [])
        
        # Ruff had F821 at 10:4, pyright had error at 10:4
        # They shouldn't dedup because source is different!
        assert len(snap.diagnostics) == 3
        
        # Let's check sort order
        # Line 1 (warning) comes before Line 10 (error)
        assert snap.diagnostics[0].range.start.line == 0
        assert snap.diagnostics[0].code == "E501"
        
        assert snap.summary.total_count == 3
        assert snap.summary.error_count == 2
        assert snap.summary.warning_count == 1
        
        assert snap.status == DiagnosticsSnapshotStatus.COMPLETED.value

def test_diagnostics_coordinator(tmp_path):
    bus = MockEventBus()
    analyzer = DiagnosticsAnalyzer(DiagnosticsConfig(workspace_root=str(tmp_path)), [])
    coord = DiagnosticsCoordinator(DiagnosticsConfig(workspace_root=str(tmp_path), debounce_seconds=0.1), analyzer, bus)
    
    coord.start()
    
    bus.publish("perception.dev.file_changed", {"relative_path": "test.py"})
    bus.publish("perception.dev.file_changed", {"relative_path": "test.py"}) # duplicate
    
    time.sleep(0.3)
    
    assert len(bus.emitted) == 1
    snap = bus.emitted[0]
    assert snap["trigger"]["kind"] == "file_changed"
    assert snap["trigger"]["paths"] == ["test.py"]
    
    coord.stop()

def test_missing_executable(tmp_path):
    provider = RuffDiagnosticProvider(["nonexistent"], 1.0, 1024)
    res = provider.collect(tmp_path, ())
    assert res.tool_result.status == DiagnosticExecutionStatus.UNAVAILABLE.value
    assert res.tool_result.diagnostic_count == 0

def test_invalid_json(tmp_path):
    provider = RuffDiagnosticProvider(["ruff"], 1.0, 1024)
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MockProc("not json", 1)
        res = provider.collect(tmp_path, ())
        assert res.tool_result.status == DiagnosticExecutionStatus.INVALID_OUTPUT.value

def test_analyzer_partial_status(tmp_path):
    ruff = RuffDiagnosticProvider(["ruff"], 1.0, 1024)
    pyright = PyrightDiagnosticProvider(["pyright"], 1.0, 1024)
    analyzer = DiagnosticsAnalyzer(DiagnosticsConfig(workspace_root=str(tmp_path)), [ruff, pyright])
    
    with patch("subprocess.run") as mock_run:
        # Ruff succeeds, Pyright produces invalid JSON
        mock_run.side_effect = [MockProc("[]", 0), MockProc("bad json", 1)]
        snap = analyzer.analyze("manual", [])
        
        assert snap.status == DiagnosticsSnapshotStatus.PARTIAL.value
        assert len(snap.tools) == 2
