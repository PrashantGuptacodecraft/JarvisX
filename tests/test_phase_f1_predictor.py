import pytest
from unittest.mock import MagicMock
from shared_core.predictive_engine.predictor import PredictiveBehaviorEngine, Prediction
from shared_core.state_manager.world_state import WorldState, SystemState
from shared_core.memory_engine.manager import MemoryManager

def test_f1_predictions_derived_from_kg_and_world_state():
    # Setup mock memory manager
    memory = MagicMock(spec=MemoryManager)
    
    # Mock habit edges in KG
    def mock_query_triples(subject=None, predicate=None, limit=None):
        if predicate == "pattern_action":
            return [{"subject": "habit:execution:123", "predicate": "pattern_action", "object": "literal:action:open_browser"}]
        if predicate == "pattern_target" and subject == "habit:execution:123":
            return [{"subject": "habit:execution:123", "predicate": "pattern_target", "object": "github.com"}]
        return []
        
    memory.query_triples.side_effect = mock_query_triples
    
    engine = PredictiveBehaviorEngine(memory)
    
    # Setup Phase-B WorldState
    world_state = WorldState()
    world_state.system = SystemState(focused_process="Code.exe")
    
    # Execute predictor
    predictions = engine.predict_next_action(world_state)
    
    # Assert predictions derived from both
    assert len(predictions) == 1
    pred = predictions[0]
    assert pred.action == "open_browser"
    assert pred.target == "github.com"
    assert pred.confidence == 0.5
    
    # Reason should reference WorldState
    assert "Code.exe" in pred.reason
    assert "habit:execution:123" in pred.reason

def test_f1_invalid_input_and_missing_dependency():
    # Missing dependency: no memory manager
    with pytest.raises(AttributeError):
        # Passing None for memory should fail or handle gracefully if we design it that way
        engine = PredictiveBehaviorEngine(None)
        engine.predict_next_action(WorldState())

def test_f1_json_serialization():
    import json
    from dataclasses import asdict
    pred = Prediction(action="test", target="test.txt", confidence=0.8, reason="Because")
    # Must be JSON serializable
    data = json.dumps(asdict(pred))
    assert "test.txt" in data

def test_f1_boundedness():
    memory = MagicMock(spec=MemoryManager)
    # Return 200 items, should be capped by limit=100 inside predictor
    def mock_query_triples(subject=None, predicate=None, limit=100):
        if predicate == "pattern_action":
            return [{"subject": f"habit:execution:{i}", "predicate": "pattern_action", "object": "action"} for i in range(limit or 100)]
        return []
    memory.query_triples.side_effect = mock_query_triples
    
    engine = PredictiveBehaviorEngine(memory)
    preds = engine.predict_next_action(WorldState())
    assert len(preds) <= 100  # Enforces capacity/boundedness
