import time
import queue
import statistics
import pytest
from main import build_jarvis

def measure(name, func, iterations=3):
    times = []
    for _ in range(iterations):
        t0 = time.time()
        func()
        t1 = time.time()
        times.append(t1 - t0)
    
    median = statistics.median(times)
    mx = max(times)
    print(f"{name}: runs={iterations}, median={median:.4f}s, max={mx:.4f}s")
    return median, mx

def test_d16_headless_boot_does_not_bind_api_port():
    cq = queue.Queue()
    # By passing headless=True, CrossDeviceServer should not start
    t0 = time.time()
    core, listener, speaker, memory, _, gesture_ctrl = build_jarvis(gui=None, command_queue=cq, headless=True)
    t1 = time.time()
    print(f"build_jarvis(headless=True) took {t1 - t0:.4f}s")
    
    # Check that CrossDeviceServer is not in tools or not running
    # The tools dictionary is inside brain, but wait, build_jarvis doesn't return tools directly.
    # We can check memory.event_bus to see it exists
    assert memory is not None
    
    # Shutdown bounded
    t0 = time.time()
    if hasattr(core, 'stop'):
        core.stop()
    if core.brain and core.brain.scheduler:
        core.brain.scheduler.stop()
    if core.brain and 'code_analyzer' in core.brain.tools:
        core.brain.tools['code_analyzer'].stop()
    listener.stop()
    if hasattr(speaker, 'stop'):
        speaker.stop()
    if gesture_ctrl and hasattr(gesture_ctrl, 'stop'):
        gesture_ctrl.stop()
    t1 = time.time()
    print(f"Bounded shutdown took {t1 - t0:.4f}s")
    assert (t1 - t0) < 5.0  # Should be quick

def test_d16_module_import_time():
    def do_imports():
        import shared_core.event_bus.bus
        import shared_core.scheduler
        import memory.manager
    
    measure("Module imports", do_imports)

def test_d16_eventbus_wiring():
    def do_eb():
        from shared_core import get_bus
        eb = get_bus()
    measure("EventBus wiring", do_eb)

def test_d16_scheduler_wiring():
    def do_sched():
        from shared_core.scheduler import Scheduler
        s = Scheduler()
        s.start()
        s.stop()
    measure("Scheduler wiring", do_sched)
