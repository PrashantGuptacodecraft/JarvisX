import pytest
import time
from unittest.mock import MagicMock
from shared_core.predictive_engine.executor import ProactiveExecutor, EXECUTION_THRESHOLD
from shared_core.event_bus.bus import EventBus
from shared_core.scheduler.scheduler import Scheduler

def test_f7_threshold_gating():
    bus = EventBus()
    scheduler = MagicMock(spec=Scheduler)
    action_handler = MagicMock(return_value=True)
    
    executor = ProactiveExecutor(bus, scheduler, action_handler)
    executor.start()
    
    # Send below threshold
    bus.publish("predict.suggestion", {
        "predictions": [{"action": "test1", "target": "t1", "confidence": EXECUTION_THRESHOLD - 0.1}]
    }, source="test")
    time.sleep(0.1)
    
    # Should not schedule
    scheduler.register_task.assert_not_called()
    
    # Send above threshold
    bus.publish("predict.suggestion", {
        "predictions": [{"action": "test2", "target": "t2", "confidence": EXECUTION_THRESHOLD + 0.05}]
    }, source="test")
    time.sleep(0.1)
    
    # Should schedule
    assert scheduler.register_task.call_count == 1
    
    executor.stop()
    bus.shutdown()


def test_f8_guardrails_announced_and_cancelable():
    bus = EventBus()
    scheduler = MagicMock(spec=Scheduler)
    action_handler = MagicMock(return_value=True)
    
    executor = ProactiveExecutor(bus, scheduler, action_handler)
    executor.start()
    
    # Capture announcements
    announcements = []
    def on_announce(event):
        announcements.append(event.payload)
    bus.subscribe("proactive.announced", on_announce)
    
    cancellations = []
    def on_cancel(event):
        cancellations.append(event.payload)
    bus.subscribe("proactive.cancelled", on_cancel)
    
    # Trigger high confidence prediction
    bus.publish("predict.suggestion", {
        "predictions": [{"action": "test3", "target": "t3", "confidence": 0.95}]
    }, source="test")
    time.sleep(0.1)
    
    assert len(announcements) == 1
    assert announcements[0]["action"] == "test3"
    assert "cancel_window" in announcements[0]
    
    # Ensure it's in pending actions
    assert len(executor._pending_actions) == 1
    
    # Simulate user saying "stop"
    bus.publish("user.input", {"text": "wait stop doing that"}, source="test")
    time.sleep(0.1)
    
    # Should be cancelled
    assert len(cancellations) == 1
    assert len(executor._pending_actions) == 0
    assert scheduler.unregister_task.call_count == 1
    
    executor.stop()
    bus.shutdown()
