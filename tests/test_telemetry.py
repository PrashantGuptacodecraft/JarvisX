"""Phase B · B6 — continuous telemetry acceptance tests.

Covers: CPU/RAM/Disk samplers, GPU graceful detection, bus publication, StateManager continuous
update, filesystem change detection, scheduler integration (pause/resume/continuity).

Run:  python -m pytest tests/test_telemetry.py -v
"""
from __future__ import annotations

import os
import tempfile
import threading
import time

from shared_core.event_bus import EventBus
from shared_core.scheduler import Priority, Scheduler
from shared_core.state_manager import build_state_manager
from shared_core.telemetry import (
    TelemetryEngine,
    gpu_available,
    sample_cpu,
    sample_disk,
    sample_gpu,
    sample_memory,
)
from shared_core.telemetry.collectors import FilesystemWatcher


# ── samplers return the required fields ──────────────────────────────────────
def test_cpu_sampler_fields():
    d = sample_cpu()
    assert "cpu_percent" in d
    assert "core_count" in d
    assert "cpu_frequency" in d
    assert "per_core_usage" in d


def test_memory_sampler_fields():
    d = sample_memory()
    assert "total_memory" in d and "used_memory" in d
    assert "free_memory" in d and "swap_usage" in d


def test_disk_sampler_fields():
    d = sample_disk()
    assert "disk_usage" in d and "free_space" in d


# ── GPU graceful detection (must not crash whether or not a GPU exists) ──────
def test_gpu_graceful():
    avail = gpu_available()
    assert isinstance(avail, bool)
    d = sample_gpu()
    assert isinstance(d, dict)          # {} when no NVIDIA GPU — never raises
    if not avail:
        assert d == {}


# ── bus publication + StateManager continuous update ─────────────────────────
def test_telemetry_publishes_and_updates_state():
    bus = EventBus("b6")
    sm = build_state_manager(bus, persist=False)
    sm.start()
    sch = Scheduler(max_workers=4)
    eng = TelemetryEngine(bus, sch, watch_paths=[],
                          cpu_interval=0.05, mem_interval=0.05, disk_interval=0.05, gpu_interval=0.05)
    sch.start()
    eng.start()
    try:
        time.sleep(0.6)
        bus.drain(timeout=3.0)
        # StateManager continuously reflects latest machine state
        assert sm.get("system.cpu") is not None
        assert sm.get("system.memory") is not None
        assert isinstance(sm.get("system.cpu_detail"), dict)
        assert sm.get("system.cpu_detail")           # non-empty
        assert isinstance(sm.get("system.disk"), dict)
        # bus published the telemetry topics
        topics = bus.stats()["published_by_topic"]
        assert topics.get("perception.system.cpu", 0) > 0
        assert topics.get("perception.system.memory", 0) > 0
    finally:
        eng.stop()
        sch.stop()
        sm.stop()


# ── filesystem change detection (live) ───────────────────────────────────────
def test_filesystem_change_detected():
    bus = EventBus("b6")
    seen = []
    lock = threading.Lock()
    bus.subscribe("perception.filesystem.change",
                  lambda e: (lock.acquire(), seen.append(e.payload), lock.release()),
                  mode="async", source="c")
    with tempfile.TemporaryDirectory() as d:
        w = FilesystemWatcher(bus, [d])
        w.start()
        if not w.available:
            w.stop()
            import pytest
            pytest.skip("watchdog not installed")
        try:
            time.sleep(0.3)
            fp = os.path.join(d, "probe.txt")
            with open(fp, "w") as f:
                f.write("hello")
            time.sleep(0.5)
            with open(fp, "a") as f:
                f.write(" world")
            time.sleep(0.5)
            os.remove(fp)
            time.sleep(0.5)
            bus.drain(timeout=3.0)
            events = {p.get("event") for p in seen}
            assert "created" in events
            assert seen                      # at least one fs event fired
        finally:
            w.stop()


# ── scheduler integration: pause / resume / continuity ───────────────────────
def test_telemetry_scheduler_pause_resume():
    bus = EventBus("b6")
    sch = Scheduler(max_workers=4)
    eng = TelemetryEngine(bus, sch, watch_paths=[],
                          cpu_interval=0.05, mem_interval=0.05, disk_interval=0.05, gpu_interval=0.05)
    sch.start()
    eng.start()
    try:
        assert "telemetry_cpu" in sch._tasks           # registered as scheduler tasks
        assert sch.pause_task("telemetry_cpu") is True
        assert sch._tasks["telemetry_cpu"].paused is True
        assert sch.resume_task("telemetry_cpu") is True
        assert sch._tasks["telemetry_cpu"].paused is False
    finally:
        eng.stop()
        sch.stop()


def test_telemetry_tasks_in_scheduler_snapshot():
    bus = EventBus("b6")
    sch = Scheduler(max_workers=2)
    eng = TelemetryEngine(bus, sch, watch_paths=[])
    eng.start()
    try:
        snap = sch.snapshot()                          # continuity-visible
        ids = {t["task_id"] for t in snap["tasks"]}
        assert {"telemetry_cpu", "telemetry_memory", "telemetry_disk", "telemetry_gpu"} <= ids
    finally:
        eng.stop()


def test_telemetry_stop_unregisters():
    bus = EventBus("b6")
    sch = Scheduler(max_workers=2)
    eng = TelemetryEngine(bus, sch, watch_paths=[])
    eng.start()
    assert "telemetry_cpu" in sch._tasks
    eng.stop()
    assert "telemetry_cpu" not in sch._tasks           # clean removal
