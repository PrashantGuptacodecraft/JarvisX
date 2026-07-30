import pytest
import datetime
from unittest.mock import MagicMock, patch
from shared_core.predictive_engine.predictor import PredictiveBehaviorEngine
from shared_core.state_manager.world_state import WorldState, SystemState
from shared_core.memory_engine.manager import MemoryManager

def test_f2_temporal_features_change_predictions():
    memory = MagicMock(spec=MemoryManager)
    
    # We mock two habits. 
    # habit 1 matches the current time of day.
    # habit 2 has a mismatched time of day.
    def mock_query_triples(subject=None, predicate=None, limit=None):
        if predicate == "pattern_action":
            return [
                {"subject": "habit:execution:1", "predicate": "pattern_action", "object": "action1"},
                {"subject": "habit:execution:2", "predicate": "pattern_action", "object": "action2"}
            ]
        if predicate == "pattern_target":
            return []
        
        # habit 1 expects "morning"
        if predicate == "pattern_time_of_day" and subject == "habit:execution:1":
            return [{"subject": "habit:execution:1", "predicate": "pattern_time_of_day", "object": "morning"}]
        # habit 2 expects "evening"
        if predicate == "pattern_time_of_day" and subject == "habit:execution:2":
            return [{"subject": "habit:execution:2", "predicate": "pattern_time_of_day", "object": "evening"}]
        
        # habit 1 expects "monday"
        if predicate == "pattern_day_of_week" and subject == "habit:execution:1":
            return [{"subject": "habit:execution:1", "predicate": "pattern_day_of_week", "object": "monday"}]
            
        return []

    memory.query_triples.side_effect = mock_query_triples
    
    engine = PredictiveBehaviorEngine(memory)
    ws = WorldState()
    ws.system = SystemState(focused_process="Code.exe")
    
    # Force time to Monday Morning
    fake_time = datetime.datetime(2026, 7, 27, 9, 0, 0, tzinfo=datetime.timezone.utc) # 2026-07-27 is a Monday, 9 AM is morning
    
    with patch("shared_core.predictive_engine.predictor.datetime") as mock_datetime:
        mock_datetime.datetime.now.return_value = fake_time
        mock_datetime.timezone = datetime.timezone
        
        preds = engine.predict_next_action(ws)
        
        # We expect action1 (habit 1) to be much higher than action2 (habit 2)
        assert len(preds) == 2
        
        pred1 = next(p for p in preds if p.action == "action1")
        pred2 = next(p for p in preds if p.action == "action2")
        
        # baseline is 0.5. 
        # pred1 matches morning (+0.2) and monday (+0.15) = 0.85
        # pred2 mismatches evening (-0.1) = 0.4
        assert pred1.confidence > pred2.confidence
        assert pred1.confidence == 0.85
        assert pred2.confidence == 0.40
        assert "time_of_day match: morning" in pred1.reason
        assert "day_of_week match: monday" in pred1.reason
