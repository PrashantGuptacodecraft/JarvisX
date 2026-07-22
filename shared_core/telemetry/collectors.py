"""collectors.py - minimal continuous telemetry collectors (Phase B · B6).

Lightweight sampling of CPU / RAM / Disk / GPU + a filesystem-change watcher, published onto
the EventBus. Every collector is crash-proof and degrades gracefully when a dependency (psutil,
nvidia-smi, watchdog) is absent — never blocks boot, never raises to the scheduler.

Topics:
  perception.system.cpu      perception.system.memory
  perception.system.disk     perception.system.gpu
  perception.filesystem.change
"""
from __future__ import annotations

import shutil
import subprocess
import threading
import time

from config.logger import get_logger

log = get_logger("telemetry")


# ── CPU ──────────────────────────────────────────────────────────────────────
def sample_cpu() -> dict:
    out: dict = {}
    try:
        import psutil
        out["cpu_percent"] = psutil.cpu_percent(interval=None)
        out["core_count"] = psutil.cpu_count(logical=True)
        try:
            freq = psutil.cpu_freq()
            out["cpu_frequency"] = round(freq.current, 1) if freq else None
        except Exception:
            out["cpu_frequency"] = None
        try:
            out["per_core_usage"] = psutil.cpu_percent(interval=None, percpu=True)
        except Exception:
            out["per_core_usage"] = []
    except Exception as exc:
        log.debug(f"cpu sample unavailable: {exc}")
    return out


# ── RAM ──────────────────────────────────────────────────────────────────────
def sample_memory() -> dict:
    out: dict = {}
    try:
        import psutil
        vm = psutil.virtual_memory()
        out["total_memory"] = vm.total
        out["used_memory"] = vm.used
        out["free_memory"] = vm.available
        out["percent"] = vm.percent
        try:
            sw = psutil.swap_memory()
            out["swap_usage"] = sw.percent
        except Exception:
            out["swap_usage"] = None
    except Exception as exc:
        log.debug(f"memory sample unavailable: {exc}")
    return out


# ── Disk ─────────────────────────────────────────────────────────────────────
_last_disk_io = {"ts": None, "read": 0, "write": 0}


def sample_disk(path: str = "/") -> dict:
    out: dict = {}
    try:
        import os
        import psutil
        target = path if os.path.exists(path) else (os.environ.get("SystemDrive", "C:") + "\\")
        du = psutil.disk_usage(target)
        out["disk_usage"] = du.percent
        out["free_space"] = du.free
        out["total_space"] = du.total
        try:
            io = psutil.disk_io_counters()
            now = time.monotonic()
            if io is not None and _last_disk_io["ts"] is not None:
                dt = max(1e-6, now - _last_disk_io["ts"])
                out["read_throughput"] = round((io.read_bytes - _last_disk_io["read"]) / dt, 1)
                out["write_throughput"] = round((io.write_bytes - _last_disk_io["write"]) / dt, 1)
            if io is not None:
                _last_disk_io.update({"ts": now, "read": io.read_bytes, "write": io.write_bytes})
        except Exception:
            pass
    except Exception as exc:
        log.debug(f"disk sample unavailable: {exc}")
    return out


# ── GPU (NVIDIA via nvidia-smi; graceful if absent) ──────────────────────────
_gpu_available: bool | None = None


def gpu_available() -> bool:
    global _gpu_available
    if _gpu_available is None:
        _gpu_available = shutil.which("nvidia-smi") is not None
    return _gpu_available


def sample_gpu() -> dict:
    """Return GPU telemetry via nvidia-smi, or {} if no NVIDIA GPU / tool present."""
    if not gpu_available():
        return {}
    try:
        proc = subprocess.run(
            ["nvidia-smi",
             "--query-gpu=utilization.gpu,memory.used,temperature.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=3,
        )
        line = (proc.stdout or "").strip().splitlines()
        if not line:
            return {}
        parts = [p.strip() for p in line[0].split(",")]
        return {
            "gpu_usage": float(parts[0]) if parts[0].replace(".", "").isdigit() else None,
            "gpu_memory_used": float(parts[1]) if len(parts) > 1 and parts[1].replace(".", "").isdigit() else None,
            "gpu_temperature": float(parts[2]) if len(parts) > 2 and parts[2].replace(".", "").isdigit() else None,
        }
    except Exception as exc:
        log.debug(f"gpu sample unavailable: {exc}")
        return {}


# ── Filesystem change watcher (watchdog; graceful if absent) ─────────────────
class FilesystemWatcher:
    """Watches directories and publishes `perception.filesystem.change` events.

    Degrades to a no-op if `watchdog` is not installed.
    """

    def __init__(self, bus, paths=None):
        self.bus = bus
        self.paths = [p for p in (paths or []) if p]
        self._observer = None
        self.available = False

    def start(self):
        if not self.paths:
            return
        try:
            from watchdog.events import FileSystemEventHandler
            from watchdog.observers import Observer

            bus = self.bus

            class _Handler(FileSystemEventHandler):
                def _emit(self, kind, event):
                    try:
                        bus.publish("perception.filesystem.change",
                                    {"event": kind,
                                     "path": getattr(event, "src_path", None),
                                     "dest": getattr(event, "dest_path", None),
                                     "is_directory": event.is_directory},
                                    source="fs_watcher")
                    except Exception:
                        pass

                def on_created(self, event):  self._emit("created", event)
                def on_deleted(self, event):  self._emit("deleted", event)
                def on_modified(self, event): self._emit("modified", event)
                def on_moved(self, event):    self._emit("moved", event)

            self._observer = Observer()
            handler = _Handler()
            import os
            for p in self.paths:
                if os.path.isdir(p):
                    self._observer.schedule(handler, p, recursive=False)
            self._observer.daemon = True
            self._observer.start()
            self.available = True
            log.info(f"FilesystemWatcher watching {len(self.paths)} dir(s).")
        except Exception as exc:
            log.warning(f"FilesystemWatcher unavailable (watchdog missing?): {exc}")
            self.available = False

    def stop(self):
        try:
            if self._observer is not None:
                self._observer.stop()
                self._observer.join(timeout=1.0)
        except Exception:
            pass
