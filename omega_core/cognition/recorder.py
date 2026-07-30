"""recorder.py - OMEGA Phase 7, Milestone 30 trace recorder.

Records deterministic, bounded, redacted structured cognition traces.
"""
import time
import json
import hashlib
from typing import Optional, List, Dict

from .models import (
    CognitionTrace, CognitionStatus, DecisionSummary, 
    EvidenceReference, CognitionCheckpoint, CognitionContinuation
)
from .redaction import redact_text, hash_evidence_content

class CognitionSession:
    """An isolated reasoning trace recording session."""
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.status = CognitionStatus.CREATED
        self.traces: Dict[str, CognitionTrace] = {}
        self.active_trace_id: Optional[str] = None
        self.unresolved_goal: Optional[str] = None
        self.waiting_for: Optional[str] = None
        self.next_sequence_number = 1
        self.previous_checkpoint_id: Optional[str] = None
        
    def add_trace(self, 
                  goal_id: str, 
                  problem_summary: str, 
                  evidence: List[EvidenceReference] = None,
                  decision: Optional[DecisionSummary] = None,
                  status: CognitionStatus = CognitionStatus.REASONING,
                  outcome_summary: Optional[str] = None) -> CognitionTrace:
                  
        # Redact potentially sensitive summary fields
        safe_problem = redact_text(problem_summary)
        safe_outcome = redact_text(outcome_summary) if outcome_summary else None
        
        # Derive deterministic Trace ID
        raw_content = f"{self.session_id}:{self.next_sequence_number}:{safe_problem}"
        trace_id = f"trace_{hashlib.sha256(raw_content.encode('utf-8')).hexdigest()[:16]}"
        
        parent_id = self.active_trace_id
        
        trace = CognitionTrace(
            schema_version=1,
            trace_id=trace_id,
            session_id=self.session_id,
            parent_trace_id=parent_id,
            sequence_number=self.next_sequence_number,
            goal_id=goal_id,
            problem_summary=safe_problem,
            evidence=tuple(evidence or []),
            decision=decision,
            status=status,
            outcome_summary=safe_outcome,
            created_at=time.time(),
            updated_at=time.time()
        )
        
        self.traces[trace_id] = trace
        self.active_trace_id = trace_id
        self.next_sequence_number += 1
        self.status = status
        self.unresolved_goal = goal_id if status in (CognitionStatus.REASONING, CognitionStatus.WAITING_FOR_EVIDENCE, CognitionStatus.WAITING_FOR_USER) else None
        return trace

    def complete(self):
        self.status = CognitionStatus.COMPLETED
        self.active_trace_id = None
        self.unresolved_goal = None
