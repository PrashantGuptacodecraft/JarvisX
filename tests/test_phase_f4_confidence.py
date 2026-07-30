import pytest
from unittest.mock import MagicMock
from shared_core.predictive_engine.predictor import PredictiveBehaviorEngine
from shared_core.state_manager.world_state import WorldState, SystemState
from shared_core.memory_engine.manager import MemoryManager

def test_f4_predictions_are_ranked_and_calibrated():
    memory = MagicMock(spec=MemoryManager)
    
    def mock_query_triples(subject=None, predicate=None, limit=None):
        if predicate == "pattern_action":
            return [
                {"subject": "habit:execution:1", "predicate": "pattern_action", "object": "action1"},
                {"subject": "habit:execution:2", "predicate": "pattern_action", "object": "action2"},
                {"subject": "habit:execution:3", "predicate": "pattern_action", "object": "action3"}
            ]
        
        # habit 1 gets app match (+0.25)
        if predicate == "pattern_context_app" and subject == "habit:execution:1":
            return [{"subject": "habit:execution:1", "predicate": "pattern_context_app", "object": "Code.exe"}]
        
        # habit 2 gets no match (just 0.5)
        
        # habit 3 gets mismatch app (-0.1)
        if predicate == "pattern_context_app" and subject == "habit:execution:3":
            return [{"subject": "habit:execution:3", "predicate": "pattern_context_app", "object": "Chrome.exe"}]
            
        return []

    memory.query_triples.side_effect = mock_query_triples
    
    engine = PredictiveBehaviorEngine(memory)
    ws = WorldState()
    ws.system = SystemState(focused_process="Code.exe")
    
    preds = engine.predict_next_action(ws)
    
    # Assert Ranked (highest confidence first)
    assert len(preds) == 3
    assert preds[0].confidence >= preds[1].confidence >= preds[2].confidence
    
    assert preds[0].action == "action1"
    assert preds[1].action == "action2"
    assert preds[2].action == "action3"
    
    # Assert Calibrated (within realistic bounds)
    for p in preds:
        assert 0.0 <= p.confidence <= 1.0
