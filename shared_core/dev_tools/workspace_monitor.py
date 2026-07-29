import time
import threading
from pathlib import Path
from typing import List, Set, Optional, Callable
from dataclasses import dataclass, asdict, field

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler, FileSystemEvent, FileMovedEvent
except ImportError:
    raise ImportError("The 'watchdog' package is required for WorkspaceMonitor. Please install it.")

from shared_core.event_bus import EventBus

@dataclass
class WorkspaceMonitorConfig:
    workspace_root: str
    ignored_directories: Set[str] = field(default_factory=lambda: {
        ".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
        ".venv", "venv", "env", "node_modules", "build", "dist"
    })
    ignored_suffixes: Set[str] = field(default_factory=lambda: {".tmp", ".swp", "~"})
    debounce_seconds: float = 0.2
    emit_created: bool = True
    emit_modified: bool = True
    emit_deleted: bool = True
    emit_moved: bool = True

@dataclass
class WorkspaceFileChange:
    relative_path: str
    change_type: str  # "created", "modified", "deleted", "moved"
    is_directory: bool
    timestamp: float
    source_path: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

class WorkspaceEventHandler(FileSystemEventHandler):
    def __init__(self, monitor: 'WorkspaceMonitor'):
        self.monitor = monitor
        
    def on_created(self, event: FileSystemEvent):
        if self.monitor.config.emit_created:
            self.monitor._handle_event(event.src_path, "created", event.is_directory)
            
    def on_modified(self, event: FileSystemEvent):
        if self.monitor.config.emit_modified:
            self.monitor._handle_event(event.src_path, "modified", event.is_directory)
            
    def on_deleted(self, event: FileSystemEvent):
        if self.monitor.config.emit_deleted:
            self.monitor._handle_event(event.src_path, "deleted", event.is_directory)
            
    def on_moved(self, event: FileMovedEvent):
        if self.monitor.config.emit_moved:
            self.monitor._handle_event(event.dest_path, "moved", event.is_directory, source_path=event.src_path)

class WorkspaceMonitor:
    def __init__(self, config: WorkspaceMonitorConfig, event_bus: EventBus):
        self.config = config
        self.event_bus = event_bus
        self.root_path = Path(config.workspace_root).resolve()
        
        self._observer: Optional[Observer] = None
        
        self._lock = threading.Lock()
        self._pending_events = {}
        self._debounce_timer: Optional[threading.Timer] = None
        
    def _is_ignored(self, absolute_path: str) -> bool:
        path = Path(absolute_path).resolve()
        
        # Check if outside workspace
        try:
            rel = path.relative_to(self.root_path)
        except ValueError:
            return True
            
        # Check ignored suffixes
        if any(path.name.endswith(suffix) for suffix in self.config.ignored_suffixes):
            return True
            
        # Check ignored directories in parts
        for part in rel.parts:
            if part in self.config.ignored_directories:
                return True
                
        return False
        
    def _handle_event(self, src_path: str, change_type: str, is_directory: bool, source_path: Optional[str] = None):
        if self._is_ignored(src_path):
            return
            
        # For moved events, we might have source ignored, but we still emit a create if destination is valid
        # Actually watchdog gives us moved event. 
        # If source is ignored but dest is not, we can treat it as 'created' (optional). For D6, we just normalize.
        if source_path and self._is_ignored(source_path):
            source_path = None
            change_type = "created"
            
        rel_path = Path(src_path).resolve().relative_to(self.root_path).as_posix()
        rel_src = Path(source_path).resolve().relative_to(self.root_path).as_posix() if source_path else None
        
        # Debounce key: specific file and specific action.
        key = (rel_path, change_type)
        
        with self._lock:
            self._pending_events[key] = WorkspaceFileChange(
                relative_path=rel_path,
                change_type=change_type,
                is_directory=is_directory,
                timestamp=time.time(),
                source_path=rel_src
            )
            
            if self._debounce_timer:
                self._debounce_timer.cancel()
            
            self._debounce_timer = threading.Timer(self.config.debounce_seconds, self._flush_events)
            self._debounce_timer.daemon = True
            self._debounce_timer.start()
            
    def _flush_events(self):
        with self._lock:
            events = list(self._pending_events.values())
            self._pending_events.clear()
            self._debounce_timer = None
            
        for event in events:
            self.event_bus.publish("perception.dev.file_changed", event.to_dict())
            
    def start(self):
        with self._lock:
            if self._observer is not None:
                return
            
            self._observer = Observer()
            handler = WorkspaceEventHandler(self)
            self._observer.schedule(handler, str(self.root_path), recursive=True)
            self._observer.start()
            
    def stop(self):
        with self._lock:
            if self._observer is None:
                return
                
            self._observer.stop()
            self._observer.join(timeout=5.0)
            self._observer = None
            
            if self._debounce_timer:
                self._debounce_timer.cancel()
                self._debounce_timer = None
