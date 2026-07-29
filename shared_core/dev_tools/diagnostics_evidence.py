import threading
from typing import Dict, List, Optional
from pathlib import Path

from shared_core.event_bus import EventBus
from .diagnostics_model import CodeDiagnostic, DiagnosticsSnapshot

class DiagnosticsEvidenceStore:
    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus
        self._lock = threading.Lock()
        
        self._latest_snapshot: Optional[DiagnosticsSnapshot] = None
        self._stale_paths: set = set()
        self._stopped = False
        
        self._sub_diag = None
        self._sub_file = None

    def start(self):
        with self._lock:
            if self._stopped:
                self._stopped = False
                
            if self._sub_diag is not None:
                return
                
            self._sub_diag = self.event_bus.subscribe("perception.dev.diagnostics", self._on_diagnostics)
            self._sub_file = self.event_bus.subscribe("perception.dev.file_changed", self._on_file_changed)

    def stop(self):
        with self._lock:
            if self._stopped:
                return
            self._stopped = True
            
            if self._sub_diag:
                self.event_bus.unsubscribe(self._sub_diag)
                self._sub_diag = None
            if self._sub_file:
                self.event_bus.unsubscribe(self._sub_file)
                self._sub_file = None

    def _on_diagnostics(self, event):
        payload = event.payload if hasattr(event, "payload") else event
        
        # reconstruct snapshot
        snap = DiagnosticsSnapshot(
            schema_version=payload.get("schema_version", 1),
            trigger=payload.get("trigger", {}),
            started_at=payload.get("started_at", ""),
            completed_at=payload.get("completed_at", ""),
            duration_ms=payload.get("duration_ms", 0),
            status=payload.get("status", "completed"),
            diagnostics=[
                CodeDiagnostic(
                    path=d.get("path", ""),
                    source=d.get("source", ""),
                    severity=d.get("severity", ""),
                    code=d.get("code"),
                    message=d.get("message", ""),
                    range=d.get("range"), # Keep as dict for simplicity since we only need read access
                    fix=d.get("fix", {})
                ) for d in payload.get("diagnostics", [])
            ],
            tools=payload.get("tools", []),
            summary=payload.get("summary", {})
        )
        
        with self._lock:
            self._latest_snapshot = snap
            self._stale_paths.clear()

    def _on_file_changed(self, event):
        payload = event.payload if hasattr(event, "payload") else event
        rel_path = payload.get("relative_path")
        if not rel_path:
            return
            
        with self._lock:
            self._stale_paths.add(rel_path)

    def get_evidence_for_path(self, path: str) -> tuple[bool, Optional[str], List[CodeDiagnostic], bool]:
        """
        Returns:
            snapshot_available (bool)
            snapshot_completed_at (Optional[str])
            matching_diagnostics (List[CodeDiagnostic])
            is_current (bool)
        """
        with self._lock:
            if not self._latest_snapshot:
                return False, None, [], False
                
            completed_at = self._latest_snapshot.completed_at
            
            # Filter matches
            matches = [d for d in self._latest_snapshot.diagnostics if d.path == path]
            
            is_current = path not in self._stale_paths
            
            return True, completed_at, matches, is_current
