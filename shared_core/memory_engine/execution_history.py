import hashlib
import json
import logging
from typing import Any, Dict

from shared_core.event_bus.topics import ACTION_RESULT, COGNITION_TRACE
from shared_core.event_bus.bus import SYNC, ASYNC
from shared_core.memory_engine.manager import MemoryManager
from shared_core.memory_engine.execution_predicates import ExecutionPredicate

log = logging.getLogger("memory.execution")

MAX_STRING_LENGTH = 1000
MAX_TARGETS = 10

class ExecutionRecorder:
    def __init__(self, memory_manager: MemoryManager, event_bus: Any):
        self.memory = memory_manager
        self.bus = event_bus
        self._is_started = False
        self._subs = []

    def start(self):
        if self._is_started:
            return
        # Subscribe exactly once
        self._subs.append(self.bus.subscribe(ACTION_RESULT, self._handle_action_result, mode=ASYNC, source="execution_recorder"))
        self._subs.append(self.bus.subscribe(COGNITION_TRACE, self._handle_cognition_trace, mode=ASYNC, source="execution_recorder"))
        self._is_started = True
        log.info("ExecutionRecorder started and subscribed to action.result, cognition.trace.")

    def stop(self):
        if not self._is_started:
            return
        if hasattr(self.bus, "unsubscribe"):
            for sub in self._subs:
                self.bus.unsubscribe(sub)
        self._subs.clear()
        self._is_started = False
        log.info("ExecutionRecorder stopped.")

    def status(self) -> dict:
        return {
            "is_started": self._is_started,
            "topics": [ACTION_RESULT, COGNITION_TRACE] if self._is_started else []
        }

    def _truncate(self, val: str) -> str:
        if not isinstance(val, str):
            val = str(val)
        return val[:MAX_STRING_LENGTH]

    def _generate_stable_id(self, prefix: str, event_obj: dict, topic: str, timestamp: str, source: str, core_fields: dict) -> str:
        # Priority 1: event_id
        if event_obj.get("event_id"):
            return f"event:{prefix}:{event_obj['event_id']}"
            
        # Priority 2: Topic-specific stable ID
        if prefix == "action":
            # action_id or correlation_id
            aid = event_obj.get("action_id") or event_obj.get("correlation_id")
            if aid:
                return f"event:{prefix}:{aid}"
        elif prefix == "trace":
            # trace_id plus span_id/sequence
            tid = event_obj.get("trace_id")
            span = event_obj.get("span_id") or event_obj.get("sequence")
            if tid and span:
                return f"event:{prefix}:{tid}_{span}"
                
        # Priority 3: Fallback hash
        payload_str = json.dumps(core_fields, sort_keys=True)
        base = f"{topic}|{timestamp}|{source}|{payload_str}"
        h = hashlib.sha256(base.encode("utf-8")).hexdigest()[:16]
        return f"event:{prefix}:{h}"

    def _format_literal(self, ns: str, val: str) -> str:
        if not val:
            return ""
        return f"literal:{ns}:{val.lower().replace(' ', '_')}"

    def _handle_action_result(self, event):
        try:
            payload = event.payload or {}
            timestamp = getattr(event, 'timestamp', None) or payload.get("timestamp")
            if not timestamp:
                return
                
            source = getattr(event, 'source', 'unknown')
            
            # Allowlisted bounded fields
            actor = payload.get("actor") or payload.get("agent") or payload.get("owner")
            action = payload.get("action") or payload.get("command")
            outcome = payload.get("outcome") or payload.get("status") or ("success" if payload.get("ok") else "failure")
            target = payload.get("target")

            if not action:
                return
                
            # Truncate to bounds
            actor = self._truncate(actor) if actor else ""
            action = self._truncate(action)
            outcome_lit = self._format_literal("outcome", self._truncate(outcome))
            
            targets = []
            if target:
                if isinstance(target, list):
                    targets = [self._truncate(t) for t in target[:MAX_TARGETS]]
                else:
                    targets = [self._truncate(target)]

            core_fields = {"action": action, "actor": actor, "outcome": outcome}
            # The event parameter might be a dict or an object depending on phase A. Assuming it behaves like dict if accessing payload
            # Actually event is an Event object from Phase A
            event_id = self._generate_stable_id("action", payload, ACTION_RESULT, timestamp, source, core_fields)
            
            # Atomic commit
            self.memory.record_execution_event(
                event_id=event_id,
                actor=actor,
                action=action,
                outcome=outcome_lit,
                targets=targets,
                timestamp=timestamp,
                source_relation=ExecutionPredicate.SOURCE,
                source=source
            )
        except Exception as e:
            log.error(f"Error handling action.result: {e}")

    def _handle_cognition_trace(self, event):
        try:
            payload = event.payload or {}
            timestamp = getattr(event, 'timestamp', None) or payload.get("timestamp")
            if not timestamp:
                return
                
            source = getattr(event, 'source', 'unknown')
            
            actor = payload.get("source") or payload.get("agent") or source
            action = payload.get("step") or payload.get("operation")
            outcome = payload.get("outcome") or payload.get("status")
            parent = payload.get("parent") or payload.get("trace_id")

            if not action:
                return
                
            actor = self._truncate(actor) if actor else ""
            action = self._truncate(action)
            outcome_lit = self._format_literal("outcome", self._truncate(outcome)) if outcome else ""
            parent = self._truncate(parent) if parent else ""
            
            core_fields = {"action": action, "actor": actor}
            event_id = self._generate_stable_id("trace", payload, COGNITION_TRACE, timestamp, source, core_fields)

            self.memory.record_execution_event(
                event_id=event_id,
                actor=actor,
                action=action,
                outcome=outcome_lit or self._format_literal("outcome", "completed"),
                targets=[],
                timestamp=timestamp,
                source_relation=ExecutionPredicate.TRACE_PARENT if parent else None,
                source=parent
            )
        except Exception as e:
            log.error(f"Error handling cognition.trace: {e}")
