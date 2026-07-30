import pytest
import datetime
from unittest.mock import MagicMock, patch
from shared_core.predictive_engine.predictor import PredictiveBehaviorEngine
from shared_core.state_manager.world_state import WorldState, SystemState
from shared_core.memory_engine.manager import MemoryManager

def test_f3_contextual_features_change_predictions():
    memory = MagicMock(spec=MemoryManager)
    
    def mock_query_triples(subject=None, predicate=None, limit=None):
        if predicate == "pattern_action":
            return [
                {"subject": "habit:execution:1", "predicate": "pattern_action", "object": "action1"},
                {"subject": "habit:execution:2", "predicate": "pattern_action", "object": "action2"}
            ]
        if predicate == "pattern_target":
            return []
        
        # habit 1 expects Code.exe
        if predicate == "pattern_context_app" and subject == "habit:execution:1":
            return [{"subject": "habit:execution:1", "predicate": "pattern_context_app", "object": "Code.exe"}]
        # habit 2 expects Chrome.exe
        if predicate == "pattern_context_app" and subject == "habit:execution:2":
            return [{"subject": "habit:execution:2", "predicate": "pattern_context_app", "object": "Chrome.exe"}]
        
        return []

    memory.query_triples.side_effect = mock_query_triples
    
    engine = PredictiveBehaviorEngine(memory)
    ws = WorldState()
    ws.system = SystemState(focused_process="Code.exe")
    
    # Run with Code.exe
    preds_code = engine.predict_next_action(ws)
    pred1_code = next(p for p in preds_code if p.action == "action1")
    pred2_code = next(p for p in preds_code if p.action == "action2")
    
    # action1 matches context app, action2 mismatches
    assert pred1_code.confidence > pred2_code.confidence
    assert "app match: Code.exe" in pred1_code.reason
    
    # Run with Chrome.exe
    ws.system.focused_process = "Chrome.exe"
    preds_chrome = engine.predict_next_action(ws)
    pred1_chrome = next(p for p in preds_chrome if p.action == "action1")
    pred2_chrome = next(p for p in preds_chrome if p.action == "action2")
    
    # action2 matches context app, action1 mismatches
    assert pred2_chrome.confidence > pred1_chrome.confidence
    assert "app match: Chrome.exe" in pred2_chrome.reason
