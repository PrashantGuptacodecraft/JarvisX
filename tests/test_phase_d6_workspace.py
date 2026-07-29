import pytest
import time
import threading
from pathlib import Path

from shared_core.dev_tools import WorkspaceMonitor, WorkspaceMonitorConfig
from shared_core.event_bus import EventBus

class MockEventBus(EventBus):
    def __init__(self):
        super().__init__()
        self.emitted = []
        
    def publish(self, topic: str, data: dict):
        self.emitted.append((topic, data))

def test_workspace_monitor_emit_events(tmp_path):
    d = tmp_path / "repo"
    d.mkdir()
    
    bus = MockEventBus()
    config = WorkspaceMonitorConfig(workspace_root=str(d), debounce_seconds=0.1)
    monitor = WorkspaceMonitor(config, bus)
    
    monitor.start()
    try:
        # Create
        f1 = d / "test.py"
        f1.touch()
        
        # Modify
        time.sleep(0.05)
        f1.write_text("print('hello')")
        
        # Allow debounce
        time.sleep(0.3)
        
        # Verify
        assert len(bus.emitted) > 0
        topics = [t for t, d in bus.emitted]
        assert "perception.dev.file_changed" in topics
        
        # Check payloads
        changes = [data for t, data in bus.emitted]
        
        creates = [c for c in changes if c["change_type"] == "created" and c["relative_path"] == "test.py"]
        assert len(creates) > 0
        
        modifies = [c for c in changes if c["change_type"] == "modified" and c["relative_path"] == "test.py"]
        assert len(modifies) > 0
        
        # Move
        bus.emitted.clear()
        f2 = d / "test2.py"
        f1.rename(f2)
        time.sleep(0.3)
        
        moves = [c for t, c in bus.emitted if c["change_type"] == "moved"]
        # Depending on watchdog, it might be moved or (deleted + created).
        # We just verify something was emitted
        assert len(bus.emitted) > 0
        
        # Delete
        bus.emitted.clear()
        f2.unlink()
        time.sleep(0.3)
        deletes = [c for t, c in bus.emitted if c["change_type"] == "deleted"]
        assert len(deletes) > 0
        
    finally:
        monitor.stop()

def test_workspace_monitor_ignores(tmp_path):
    d = tmp_path / "repo"
    d.mkdir()
    
    bus = MockEventBus()
    config = WorkspaceMonitorConfig(workspace_root=str(d), debounce_seconds=0.1)
    monitor = WorkspaceMonitor(config, bus)
    
    monitor.start()
    try:
        # Ignore dir
        git_dir = d / ".git"
        git_dir.mkdir()
        
        f1 = git_dir / "config"
        f1.touch()
        
        # Ignore suffix
        f2 = d / "temp.swp"
        f2.touch()
        
        time.sleep(0.3)
        
        assert len(bus.emitted) == 0
    finally:
        monitor.stop()

def test_workspace_monitor_idempotent_lifecycle(tmp_path):
    d = tmp_path / "repo"
    d.mkdir()
    bus = MockEventBus()
    config = WorkspaceMonitorConfig(workspace_root=str(d), debounce_seconds=0.1)
    monitor = WorkspaceMonitor(config, bus)
    
    monitor.start()
    monitor.start()  # Should not raise or create multiple threads
    
    assert monitor._observer.is_alive()
    
    monitor.stop()
    monitor.stop()  # Should not raise
    
    assert monitor._observer is None
