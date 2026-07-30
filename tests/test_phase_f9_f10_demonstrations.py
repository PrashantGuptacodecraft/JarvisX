import pytest
import time
from unittest.mock import MagicMock
from shared_core.predictive_engine.predictor import PredictiveBehaviorEngine
from shared_core.predictive_engine.executor import ProactiveExecutor, EXECUTION_THRESHOLD
from shared_core.event_bus.bus import EventBus
from shared_core.scheduler.scheduler import Scheduler
from shared_core.state_manager.world_state import WorldState, SystemState

def test_f9_f10_demonstrations():
    bus = EventBus()
    scheduler = MagicMock(spec=Scheduler)
    
    # We will track executed actions
    executed = []
    def mock_action_handler(action, target):
        executed.append((action, target))
        return True
    
    executor = ProactiveExecutor(bus, scheduler, mock_action_handler)
    executor.start()
    
    # F9 Demonstration: Preload dev environment (e.g., warm_cache)
    # F10 Demonstration: Open-app-before-asked (e.g., open_app)
    
    # Simulate prediction tick emitting a highly confident prediction for F9
    bus.publish("predict.suggestion", {
        "predictions": [{"action": "warm_cache", "target": "dev_env", "confidence": 0.95}]
    }, source="test")
    time.sleep(0.1)
    
    # Assert F9 scheduled
    assert scheduler.register_task.call_count == 1
    
    # Call the scheduled task to execute it
    task_fn = scheduler.register_task.call_args[0][2]
    task_fn()
    time.sleep(0.1)
    
    assert executed == [("warm_cache", "dev_env")]
    
    # Simulate prediction tick for F10 (open app)
    bus.publish("predict.suggestion", {
        "predictions": [{"action": "open_app", "target": "Chrome.exe", "confidence": 0.92}]
    }, source="test")
    time.sleep(0.1)
    
    assert scheduler.register_task.call_count == 2
    task_fn2 = scheduler.register_task.call_args[0][2]
    task_fn2()
    time.sleep(0.1)
    
    assert ("open_app", "Chrome.exe") in executed
    
    executor.stop()
    bus.shutdown()
