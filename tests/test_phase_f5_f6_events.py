import pytest
from unittest.mock import MagicMock
from shared_core.predictive_engine.predictor import PredictiveBehaviorEngine, Prediction
from shared_core.event_bus.bus import EventBus
from shared_core.state_manager.world_state import WorldState, SystemState

def test_f5_f6_publish_events():
    memory = MagicMock()
    bus = MagicMock(spec=EventBus)
    scheduler = MagicMock()
    state_manager = MagicMock()
    
    # Setup state
    ws = WorldState()
    ws.system = SystemState(focused_process="Code.exe")
    state_manager.get_world_state.return_value = ws
    
    engine = PredictiveBehaviorEngine(memory, bus, scheduler, state_manager)
    
    # Mock predict_next_action to return known predictions
    engine.predict_next_action = MagicMock(return_value=[
        Prediction(action="action_high", target="target1", confidence=0.9, reason="test"),
        Prediction(action="action_low", target="target2", confidence=0.4, reason="test")
    ])
    
    # Run the tick
    engine._prediction_tick()
    
    # Assert F5: predict.suggestion emitted
    bus.publish.assert_any_call(
        "predict.suggestion",
        {"predictions": [
            {"action": "action_high", "target": "target1", "confidence": 0.9, "reason": "test"},
            {"action": "action_low", "target": "target2", "confidence": 0.4, "reason": "test"}
        ]},
        source="predictive_engine"
    )
    
    # Assert F6: predict.preload emitted for confidence >= 0.8
    bus.publish.assert_any_call(
        "predict.preload",
        {"action": "action_high", "target": "target1", "confidence": 0.9},
        source="predictive_engine"
    )
    
    # Ensure action_low (0.4) was NOT preloaded
    call_args_list = bus.publish.call_args_list
    for call in call_args_list:
        if call[0][0] == "predict.preload":
            assert call[0][1]["action"] != "action_low"
