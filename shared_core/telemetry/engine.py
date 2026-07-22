"""engine.py - continuous telemetry engine (Phase B · B6).

Registers CPU/RAM/Disk/GPU samplers as recurring Scheduler tasks (pause/resume/continuity via
the Scheduler) and starts a filesystem-change watcher. Each sampler publishes to the EventBus;
the StateManager consumes and continuously reflects the latest machine state in WorldState.

Additive + crash-proof: any failure degrades to no-op and never blocks boot.
"""
from __future__ import annotations

from config.logger import get_logger

from .collectors import (
    FilesystemWatcher,
    gpu_available,
    sample_cpu,
    sample_disk,
    sample_gpu,
    sample_memory,
)

log = get_logger("telemetry")

# Task ids are stable so Scheduler continuity (snapshot/restore) can preserve their state.
CPU_TASK = "telemetry_cpu"
MEM_TASK = "telemetry_memory"
DISK_TASK = "telemetry_disk"
GPU_TASK = "telemetry_gpu"


class TelemetryEngine:
    def __init__(self, bus, scheduler, watch_paths=None,
                 cpu_interval=2.0, mem_interval=2.0, disk_interval=5.0, gpu_interval=5.0):
        self.bus = bus
        self.scheduler = scheduler
        self.watch_paths = watch_paths or []
        self._intervals = {
            CPU_TASK: cpu_interval, MEM_TASK: mem_interval,
            DISK_TASK: disk_interval, GPU_TASK: gpu_interval,
        }
        self.fs_watcher = None

    # ── collector tasks (each publishes one telemetry topic) ──────────────────
    def _tick_cpu(self):
        d = sample_cpu()
        if d:
            self.bus.publish("perception.system.cpu", d, source="telemetry")

    def _tick_memory(self):
        d = sample_memory()
        if d:
            self.bus.publish("perception.system.memory", d, source="telemetry")

    def _tick_disk(self):
        d = sample_disk()
        if d:
            self.bus.publish("perception.system.disk", d, source="telemetry")

    def _tick_gpu(self):
        d = sample_gpu()
        if d:
            self.bus.publish("perception.system.gpu", d, source="telemetry")

    def start(self):
        """Register collectors on the Scheduler + start the filesystem watcher."""
        try:
            from shared_core.scheduler import Priority
            reg = self.scheduler.register_task
            reg(CPU_TASK, "CPU telemetry", self._tick_cpu, interval=self._intervals[CPU_TASK],
                priority=Priority.BACKGROUND, source_module="telemetry")
            reg(MEM_TASK, "Memory telemetry", self._tick_memory, interval=self._intervals[MEM_TASK],
                priority=Priority.BACKGROUND, source_module="telemetry")
            reg(DISK_TASK, "Disk telemetry", self._tick_disk, interval=self._intervals[DISK_TASK],
                priority=Priority.BACKGROUND, source_module="telemetry")
            reg(GPU_TASK, "GPU telemetry", self._tick_gpu, interval=self._intervals[GPU_TASK],
                priority=Priority.BACKGROUND, source_module="telemetry")
            log.info(f"Telemetry collectors registered (gpu_available={gpu_available()}).")
        except Exception as exc:
            log.warning(f"Telemetry scheduler registration failed: {exc}")

        try:
            self.fs_watcher = FilesystemWatcher(self.bus, self.watch_paths)
            self.fs_watcher.start()
        except Exception as exc:
            log.warning(f"Filesystem watcher failed: {exc}")

    def stop(self):
        for tid in (CPU_TASK, MEM_TASK, DISK_TASK, GPU_TASK):
            try:
                self.scheduler.unregister_task(tid)
            except Exception:
                pass
        if self.fs_watcher is not None:
            self.fs_watcher.stop()
