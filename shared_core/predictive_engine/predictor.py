import logging
import datetime
from dataclasses import dataclass
from typing import List, Optional

from shared_core.state_manager.world_state import WorldState
from shared_core.memory_engine.manager import MemoryManager
from shared_core.event_bus.bus import EventBus
from shared_core.scheduler.scheduler import Scheduler

log = logging.getLogger("predictive_engine")


@dataclass
class Prediction:
    action: str
    target: Optional[str]
    confidence: float
    reason: str


class PredictiveBehaviorEngine:
    def __init__(self, memory: MemoryManager, bus: EventBus = None, scheduler: Scheduler = None, state_manager=None):
        self.memory = memory
        self.bus = bus
        self.scheduler = scheduler
        self.state_manager = state_manager

    def start(self):
        """Register the prediction loop on the Scheduler."""
        if self.scheduler and self.bus and self.state_manager:
            from shared_core.scheduler.task import Priority
            self.scheduler.register_task(
                "predictive_loop",
                "Behavior Predictor",
                self._prediction_tick,
                interval=5.0,
                priority=Priority.BACKGROUND,
                source_module="predictive_engine"
            )
            log.info("PredictiveBehaviorEngine started.")

    def stop(self):
        """Unregister the prediction loop."""
        if self.scheduler:
            try:
                self.scheduler.unregister_task("predictive_loop")
            except Exception:
                pass

    def _prediction_tick(self):
        if not self.state_manager or not self.bus:
            return
            
        current_state = self.state_manager.get_world_state()
        preds = self.predict_next_action(current_state)
        
        if preds:
            from dataclasses import asdict
            # F5: predict.suggestion events published
            self.bus.publish("predict.suggestion", {"predictions": [asdict(p) for p in preds]}, source="predictive_engine")
            
            # F6: predict.preload events published
            for p in preds:
                if p.confidence >= 0.8:
                    self.bus.publish("predict.preload", {"action": p.action, "target": p.target, "confidence": p.confidence}, source="predictive_engine")

    def predict_next_action(self, current_state: WorldState) -> List[Prediction]:
        """
        Derive predictions from Phase-C habit edges and Phase-B WorldState.
        (Milestone F1 requirement)
        """
        predictions = []

        # Find all habit actors
        # We query for entities that have pattern_action
        habit_triples = self.memory.query_triples(predicate="pattern_action", limit=100)
        
        # We also need pattern_outcome and pattern_target to build a full prediction.
        for t in habit_triples:
            habit_id = t["subject"]
            action = t["object"]
            
            # Clean up the literal marker if present
            if action.startswith("literal:action:"):
                action = action.replace("literal:action:", "", 1)
                
            targets = self.memory.query_triples(subject=habit_id, predicate="pattern_target")
            target_val = None
            if targets:
                target_val = targets[0]["object"]
                
            focused = current_state.system.focused_process or "unknown"
            
            confidence = 0.5
            reason = f"Habit {habit_id} matched in context of {focused}"
            
            # F2 Temporal Features
            now_dt = datetime.datetime.now(datetime.timezone.utc)
            
            # Example time-of-day: "morning" (06-12), "afternoon" (12-18), "evening" (18-24), "night" (00-06)
            hour = now_dt.hour
            current_tod = "night"
            if 6 <= hour < 12: current_tod = "morning"
            elif 12 <= hour < 18: current_tod = "afternoon"
            elif 18 <= hour <= 23: current_tod = "evening"
            
            current_dow = now_dt.strftime("%A").lower()
            
            tod_triples = self.memory.query_triples(subject=habit_id, predicate="pattern_time_of_day")
            if tod_triples:
                tod_val = tod_triples[0]["object"].replace("literal:time_of_day:", "")
                if tod_val == current_tod:
                    confidence += 0.2
                    reason += f" (+time_of_day match: {current_tod})"
                else:
                    confidence -= 0.1
                    
            dow_triples = self.memory.query_triples(subject=habit_id, predicate="pattern_day_of_week")
            if dow_triples:
                dow_val = dow_triples[0]["object"].replace("literal:day_of_week:", "")
                if dow_val == current_dow:
                    confidence += 0.15
                    reason += f" (+day_of_week match: {current_dow})"
                else:
                    confidence -= 0.05
                    
            # F3 Contextual Features
            app_triples = self.memory.query_triples(subject=habit_id, predicate="pattern_context_app")
            if app_triples:
                app_val = app_triples[0]["object"].replace("literal:context_app:", "")
                if app_val == focused:
                    confidence += 0.25
                    reason += f" (+app match: {focused})"
                else:
                    confidence -= 0.1
                    
            confidence = max(0.0, min(1.0, round(confidence, 2)))
            predictions.append(Prediction(
                action=action,
                target=target_val,
                confidence=confidence,
                reason=reason
            ))

        predictions.sort(key=lambda p: p.confidence, reverse=True)
        return predictions
