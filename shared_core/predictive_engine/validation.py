from typing import List, Dict

class PredictionAccuracyHarness:
    def __init__(self):
        self.total_predictions = 0
        self.hits = 0
        self.misses = 0
        # Stores the most recent predictions per context/timestamp
        self.last_predictions = {}
        
    def record_predictions(self, predictions: List[dict]):
        if not predictions:
            return
        # Store the top prediction for the current session/tick
        top_pred = predictions[0]
        self.last_predictions["latest"] = top_pred
        
    def evaluate_actual_action(self, actual_action: str, actual_target: str = None):
        if "latest" not in self.last_predictions:
            return
            
        pred = self.last_predictions["latest"]
        self.total_predictions += 1
        
        # A hit is if the action (and optionally target) match
        if pred["action"] == actual_action:
            if not actual_target or pred.get("target") == actual_target:
                self.hits += 1
                return
                
        self.misses += 1
        
    def get_accuracy(self) -> float:
        if self.total_predictions == 0:
            return 0.0
        return self.hits / self.total_predictions

    def get_report(self) -> Dict[str, float]:
        return {
            "total": self.total_predictions,
            "hits": self.hits,
            "misses": self.misses,
            "accuracy": self.get_accuracy()
        }
