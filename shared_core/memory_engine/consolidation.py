import logging
import hashlib
import json
import datetime
import threading
from typing import Dict, Any, List

from shared_core.memory_engine.manager import MemoryManager
from shared_core.memory_engine.kg_query import KGQueryService
from shared_core.memory_engine.execution_predicates import ExecutionPredicate

log = logging.getLogger("memory.consolidation")

DEFAULT_CONSOLIDATION_LOOKBACK_DAYS = 30
MAX_CONSOLIDATION_EVENTS = 5000
DEFAULT_CONSOLIDATION_THRESHOLD = 3

class ConsolidationJob:
    """
    Phase C9: Episodic→semantic consolidation.
    Promotes recurring episodic patterns into semantic facts/edges.
    """
    def __init__(self, memory_manager: MemoryManager, kg_query_service: KGQueryService):
        self.memory = memory_manager
        self.query = kg_query_service
        self._last_run = "1970-01-01T00:00:00Z"
        self._lock = threading.Lock()
        self._is_running = False

    def run_once(self) -> Dict[str, Any]:
        """
        Scans for recurring episodic patterns within a bounded lookback window
        and promotes them to semantic edges (Habits/Facts).
        """
        # 11. Run guard
        if not self._lock.acquire(blocking=False):
            return {"status": "already_running"}
            
        try:
            self._is_running = True
            start_time = datetime.datetime.now(datetime.timezone.utc)
            started_at = start_time.isoformat()
            
            lookback_time = start_time - datetime.timedelta(days=DEFAULT_CONSOLIDATION_LOOKBACK_DAYS)
            lookback_str = lookback_time.isoformat()
            
            # Fetch recent triples bounded by capacity
            recent_triples = self.query.since(lookback_str, limit=MAX_CONSOLIDATION_EVENTS + 1)
            
            if len(recent_triples) > MAX_CONSOLIDATION_EVENTS:
                return {
                    "schema_version": 1,
                    "started_at": started_at,
                    "completed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "status": "candidate_capacity_exceeded",
                    "failure_category": "capacity_exceeded"
                }
                
            # Assemble event properties
            events = {}
            for t in recent_triples:
                subject = t["subject"]
                # Only C7 Event entities (starts with event:action: or event:trace:)
                if subject.startswith("event:action:") or subject.startswith("event:trace:"):
                    if subject not in events:
                        events[subject] = {}
                    events[subject][t["predicate"]] = t["object"]
                    
            patterns = {}
            valid_events = 0
            malformed = 0
            
            for event_id, props in events.items():
                actor = props.get(ExecutionPredicate.PERFORMED_BY)
                action = props.get(ExecutionPredicate.ACTION)
                outcome = props.get(ExecutionPredicate.OUTCOME)
                source = props.get(ExecutionPredicate.SOURCE, "unknown")
                
                # Incomplete execution events skipped
                if not actor or not action or not outcome:
                    malformed += 1
                    continue
                    
                valid_events += 1
                
                targets = []
                for k, v in props.items():
                    if k == ExecutionPredicate.TARGET:
                        targets.append(v)
                        
                # Deterministic signature: actor, action, outcome, sorted unique targets, source category
                unique_targets = sorted(list(set(targets)))
                
                signature_obj = {
                    "actor": actor,
                    "action": action,
                    "outcome": outcome,
                    "source": source,
                    "targets": unique_targets
                }
                sig_str = json.dumps(signature_obj, sort_keys=True)
                sig_hash = hashlib.sha256(sig_str.encode("utf-8")).hexdigest()
                
                habit_id = f"habit:execution:{sig_hash}"
                
                if habit_id not in patterns:
                    patterns[habit_id] = {
                        "habit_id": habit_id,
                        "actor": actor,
                        "action": action,
                        "outcome": outcome,
                        "targets": unique_targets,
                        "evidence": set()
                    }
                patterns[habit_id]["evidence"].add(event_id)
                
            promoted = 0
            skipped = 0
            existing = 0
            
            for habit_id, pattern in patterns.items():
                evidence_list = sorted(list(pattern["evidence"]))
                if len(evidence_list) < DEFAULT_CONSOLIDATION_THRESHOLD:
                    skipped += 1
                    continue
                    
                # Bounded evidence
                MAX_PATTERN_EVIDENCE = 3
                evidence_list = evidence_list[:MAX_PATTERN_EVIDENCE]
                pattern["evidence"] = evidence_list
                
                # Let's check using query_triples
                is_existing = len(self.memory.query_triples(subject=habit_id, limit=1)) > 0
                if is_existing:
                    existing += 1
                    continue
                    
                # Atomic promotion
                success = self.memory.promote_semantic_pattern(pattern)
                if success:
                    promoted += 1
                else:
                    skipped += 1
                    
            self._last_run = started_at
            
            return {
                "schema_version": 1,
                "started_at": started_at,
                "completed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "scanned_event_count": len(events),
                "valid_event_count": valid_events,
                "malformed_event_count": malformed,
                "distinct_pattern_count": len(patterns),
                "promoted_pattern_count": promoted,
                "existing_pattern_count": existing,
                "skipped_pattern_count": skipped,
                "status": "success",
                "failure_category": None
            }
            
        finally:
            self._is_running = False
            self._lock.release()
