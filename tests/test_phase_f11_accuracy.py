import pytest
from shared_core.predictive_engine.validation import PredictionAccuracyHarness

def test_f11_prediction_accuracy_harness():
    harness = PredictionAccuracyHarness()
    
    # 1. Predict A, User does A (Hit)
    harness.record_predictions([{"action": "open_app", "target": "Chrome.exe"}])
    harness.evaluate_actual_action("open_app", "Chrome.exe")
    
    # 2. Predict B, User does C (Miss)
    harness.record_predictions([{"action": "warm_cache", "target": "env"}])
    harness.evaluate_actual_action("run_tests")
    
    # 3. Predict D, User does D (Hit)
    harness.record_predictions([{"action": "git_commit"}])
    harness.evaluate_actual_action("git_commit")
    
    report = harness.get_report()
    
    assert report["total"] == 3
    assert report["hits"] == 2
    assert report["misses"] == 1
    assert report["accuracy"] == 2/3
