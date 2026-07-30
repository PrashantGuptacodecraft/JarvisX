import logging
import threading
import time
from typing import Dict, Any, Callable
from shared_core.event_bus.bus import EventBus
from shared_core.scheduler.scheduler import Scheduler

log = logging.getLogger("predictive_executor")

# The confidence threshold for execution
EXECUTION_THRESHOLD = 0.90
# The time window to wait for user cancellation
CANCEL_WINDOW_SECONDS = 5.0

class ProactiveExecutor:
    def __init__(self, bus: EventBus, scheduler: Scheduler, action_handler: Callable[[str, str], bool]):
        """
        action_handler(action, target) is the callback that actually executes the action.
        It must return True if successful.
        """
        self.bus = bus
        self.scheduler = scheduler
        self.action_handler = action_handler
        self._pending_actions: Dict[str, dict] = {}
        self._subs = []
        self._lock = threading.Lock()
        
    def start(self):
        self._subs.append(self.bus.subscribe("predict.suggestion", self._on_suggestion))
        self._subs.append(self.bus.subscribe("user.input", self._on_user_input))
        log.info("ProactiveExecutor started.")
        
    def stop(self):
        for sub in self._subs:
            self.bus.unsubscribe(sub)
        self._subs.clear()
        
        with self._lock:
            for task_id in list(self._pending_actions.keys()):
                self.scheduler.unregister_task(task_id)
            self._pending_actions.clear()
            
    def _on_suggestion(self, event):
        payload = event.payload
        predictions = payload.get("predictions", [])
        if not predictions:
            return
            
        top_pred = predictions[0]
        if top_pred.get("confidence", 0.0) >= EXECUTION_THRESHOLD:
            self._schedule_proactive_action(top_pred)
            
    def _schedule_proactive_action(self, pred: dict):
        action = pred["action"]
        target = pred.get("target")
        
        task_id = f"proactive_{action}_{target}_{time.time()}"
        
        with self._lock:
            self._pending_actions[task_id] = {
                "action": action,
                "target": target,
                "timestamp": time.time(),
                "status": "pending"
            }
            
        # Announce
        self.bus.publish("proactive.announced", {
            "task_id": task_id,
            "action": action,
            "target": target,
            "cancel_window": CANCEL_WINDOW_SECONDS,
            "message": f"Proactively executing {action} on {target} in {CANCEL_WINDOW_SECONDS}s. Say 'stop' or 'cancel' to abort."
        }, source="proactive_executor")
        
        # Schedule the actual execution
        from shared_core.scheduler.task import Priority
        self.scheduler.register_task(
            task_id,
            f"Proactive {action}",
            lambda: self._execute_action(task_id),
            interval=CANCEL_WINDOW_SECONDS,
            priority=Priority.USER,
            source_module="proactive_executor"
        )
        
    def _on_user_input(self, event):
        """Cancel if user says stop/cancel."""
        payload = event.payload
        text = payload.get("text", "").lower()
        if "cancel" in text or "stop" in text or "undo" in text or "no" in text:
            self.cancel_all_pending()
            
    def cancel_all_pending(self):
        with self._lock:
            for task_id in list(self._pending_actions.keys()):
                self.scheduler.unregister_task(task_id)
                self.bus.publish("proactive.cancelled", {"task_id": task_id}, source="proactive_executor")
            self._pending_actions.clear()

    def _execute_action(self, task_id: str):
        with self._lock:
            if task_id not in self._pending_actions:
                return # was cancelled
            action_data = self._pending_actions.pop(task_id)
            
        action = action_data["action"]
        target = action_data["target"]
        
        self.scheduler.unregister_task(task_id)
        self.bus.publish("proactive.executing", {"task_id": task_id, "action": action, "target": target}, source="proactive_executor")
        
        success = False
        try:
            success = self.action_handler(action, target)
        except Exception as e:
            log.error(f"Proactive execution failed: {e}")
            
        if success:
            self.bus.publish("proactive.completed", {"task_id": task_id, "action": action, "target": target}, source="proactive_executor")
        else:
            self.bus.publish("proactive.failed", {"task_id": task_id, "action": action, "target": target}, source="proactive_executor")
