import threading
import time
from pathlib import Path
from typing import List, Set

from shared_core.event_bus import EventBus
from .diagnostics_model import DiagnosticsConfig, DiagnosticTriggerKind
from .diagnostics_analyzer import DiagnosticsAnalyzer

class DiagnosticsCoordinator:
    def __init__(self, config: DiagnosticsConfig, analyzer: DiagnosticsAnalyzer, event_bus: EventBus):
        self.config = config
        self.analyzer = analyzer
        self.event_bus = event_bus
        
        self._lock = threading.Lock()
        self._pending_paths: Set[str] = set()
        self._debounce_timer: threading.Timer = None
        self._active_run_thread: threading.Thread = None
        self._run_pending = False
        self._stopped = False
        self._subscription_id = None
        
    def start(self):
        with self._lock:
            if self._stopped:
                self._stopped = False
                
            if self._subscription_id is not None:
                return
                
            self._subscription_id = self.event_bus.subscribe("perception.dev.file_changed", self._on_file_changed)
            
    def stop(self):
        with self._lock:
            if self._stopped:
                return
            self._stopped = True
            
            if self._subscription_id:
                self.event_bus.unsubscribe(self._subscription_id)
                self._subscription_id = None
                
            if self._debounce_timer:
                self._debounce_timer.cancel()
                self._debounce_timer = None
                
        # Wait for active run
        if self._active_run_thread and self._active_run_thread.is_alive():
            self._active_run_thread.join(timeout=5.0)
            
    def run_now(self, paths: List[str] = None):
        self._trigger_run(paths or [], DiagnosticTriggerKind.MANUAL.value)
            
    def _is_relevant(self, path: str) -> bool:
        p = Path(path)
        
        if p.name in self.config.relevant_config_files:
            return True
            
        return any(p.name.endswith(ext) for ext in self.config.relevant_extensions)

    def _on_file_changed(self, event):
        payload = event.payload if hasattr(event, "payload") else event
        rel_path = payload.get("relative_path")
        if not rel_path or not self._is_relevant(rel_path):
            return
            
        with self._lock:
            if self._stopped:
                return
                
            self._pending_paths.add(rel_path)
            
            if self._debounce_timer:
                self._debounce_timer.cancel()
                
            self._debounce_timer = threading.Timer(self.config.debounce_seconds, self._flush_debounce)
            self._debounce_timer.daemon = True
            self._debounce_timer.start()
            
    def _flush_debounce(self):
        with self._lock:
            if self._stopped:
                return
            self._debounce_timer = None
            paths = list(self._pending_paths)
            self._pending_paths.clear()
            
        if paths:
            self._trigger_run(paths, DiagnosticTriggerKind.FILE_CHANGED.value)
            
    def _trigger_run(self, paths: List[str], kind: str):
        with self._lock:
            if self._stopped:
                return
                
            if self._active_run_thread and self._active_run_thread.is_alive():
                self._pending_paths.update(paths)
                self._run_pending = True
                return
                
            self._active_run_thread = threading.Thread(target=self._run_diagnostics, args=(paths, kind), daemon=True)
            self._active_run_thread.start()
            
    def _run_diagnostics(self, paths: List[str], kind: str):
        # Configuration change -> full scan
        if any(Path(p).name in self.config.relevant_config_files for p in paths):
            paths = []
            
        snap = self.analyzer.analyze(kind, paths)
        
        with self._lock:
            if not self._stopped:
                self.event_bus.publish("perception.dev.diagnostics", snap.to_dict())
                
            if self._run_pending and not self._stopped:
                self._run_pending = False
                pending = list(self._pending_paths)
                self._pending_paths.clear()
                
                # Schedule next run
                if pending:
                    threading.Timer(0.1, self._trigger_run, args=(pending, DiagnosticTriggerKind.FILE_CHANGED.value)).start()
