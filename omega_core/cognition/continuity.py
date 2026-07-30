"""continuity.py - OMEGA Phase 7, Milestone 30 continuity adapter.

Safe checkpoint creation and restoration.
"""
import time
import json
import hashlib
from typing import Dict, Any, Optional
from dataclasses import dataclass

from .models import (
    CognitionCheckpoint, CognitionContinuation, CognitionStatus, CognitionTrace
)
from .recorder import CognitionSession
from .persistence import CognitionPersistence

@dataclass
class CheckpointResult:
    checkpoint_id: str
    compaction_occurred: bool
    status: str

@dataclass
class ContinuationResult:
    continuation: Optional[CognitionContinuation]
    error: Optional[str]


class OmegaCognitionContinuity:
    """Explicit, narrow adapter for OMEGA continuity.
    
    Does NOT register automatically during JARVIS boot.
    """
    def __init__(self, persistence: CognitionPersistence = None):
        self.persistence = persistence or CognitionPersistence()

    def checkpoint(self, session: CognitionSession) -> CheckpointResult:
        """Create a checkpoint from the current session state."""
        
        compaction_occurred = False
        retained_traces = list(session.traces.values())
        
        if len(retained_traces) > 50:
            compaction_occurred = True
            # Compact terminal traces, preserve active, blocked, waiting
            terminal_statuses = {
                CognitionStatus.COMPLETED, CognitionStatus.FAILED, 
                CognitionStatus.CANCELLED, CognitionStatus.SUPERSEDED
            }
            
            # Keep non-terminal traces or the most recent ones if we must
            preserved = [t for t in retained_traces if t.status not in terminal_statuses]
            
            # If still somehow over 50 (e.g. 51 active traces), we just keep the 50 most recent
            if len(preserved) < 50:
                # Add back some terminal ones to reach up to 50 if we want, or just keep what's preserved
                terminals_to_keep = 50 - len(preserved)
                terminals = [t for t in retained_traces if t.status in terminal_statuses]
                terminals.sort(key=lambda x: x.sequence_number, reverse=True)
                preserved.extend(terminals[:terminals_to_keep])
            elif len(preserved) > 50:
                # Still too many active, which shouldn't happen, but just in case, sort by sequence
                preserved.sort(key=lambda x: x.sequence_number, reverse=True)
                preserved = preserved[:50]
                
            preserved.sort(key=lambda x: x.sequence_number)
            retained_traces = preserved

        # Generate Checkpoint ID
        content_to_hash = {
            "session_id": session.session_id,
            "previous": session.previous_checkpoint_id,
            "traces_count": len(retained_traces),
            "seq": session.next_sequence_number
        }
        raw_hash = hashlib.sha256(json.dumps(content_to_hash, sort_keys=True).encode("utf-8")).hexdigest()
        checkpoint_id = f"cp_{raw_hash[:16]}"
        
        now = time.time()
        
        # We need a proper content_sha256
        # Generate the data dict to hash
        data_to_hash = {
            "schema_version": 1,
            "session_id": session.session_id,
            "session_status": session.status.value,
            "traces": [
                {
                    "schema_version": t.schema_version,
                    "trace_id": t.trace_id,
                    "session_id": t.session_id,
                    "parent_trace_id": t.parent_trace_id,
                    "sequence_number": t.sequence_number,
                    "goal_id": t.goal_id,
                    "problem_summary": t.problem_summary,
                    "evidence": [
                        {
                            "source_id": e.source_id,
                            "source_type": e.source_type,
                            "excerpt": e.excerpt,
                            "content_sha256": e.content_sha256,
                            "sensitivity": e.sensitivity,
                            "captured_at": e.captured_at
                        } for e in t.evidence
                    ],
                    "decision": {
                        "selected_strategy": t.decision.selected_strategy,
                        "alternatives_considered": t.decision.alternatives_considered,
                        "decision": t.decision.decision,
                        "confidence": t.decision.confidence,
                        "assumptions": t.decision.assumptions,
                        "constraints": t.decision.constraints
                    } if t.decision else None,
                    "status": t.status.value,
                    "outcome_summary": t.outcome_summary,
                    "created_at": t.created_at,
                    "updated_at": t.updated_at
                } for t in retained_traces
            ],
            "active_trace_id": session.active_trace_id,
            "unresolved_goal": session.unresolved_goal,
            "waiting_for": session.waiting_for,
            "created_at": now,
            "previous_checkpoint_id": session.previous_checkpoint_id
        }
        
        content_sha256 = hashlib.sha256(json.dumps(data_to_hash, sort_keys=True).encode("utf-8")).hexdigest()
        
        cp = CognitionCheckpoint(
            schema_version=1,
            checkpoint_id=checkpoint_id,
            session_id=session.session_id,
            session_status=session.status,
            traces=tuple(retained_traces),
            active_trace_id=session.active_trace_id,
            unresolved_goal=session.unresolved_goal,
            waiting_for=session.waiting_for,
            created_at=now,
            previous_checkpoint_id=session.previous_checkpoint_id,
            content_sha256=content_sha256
        )
        
        try:
            self.persistence.save_checkpoint(cp)
            session.previous_checkpoint_id = checkpoint_id
            return CheckpointResult(checkpoint_id, compaction_occurred, "SUCCESS")
        except Exception as e:
            return CheckpointResult("", compaction_occurred, f"FAILURE: {str(e)}")

    def restore(self, session_id: str) -> ContinuationResult:
        """Restore a continuation state from the latest checkpoint."""
        try:
            cp = self.persistence.load_latest_checkpoint(session_id)
            if not cp:
                return ContinuationResult(None, "NOT_FOUND")
                
            next_seq = max((t.sequence_number for t in cp.traces), default=0) + 1
            
            cont = CognitionContinuation(
                session_id=cp.session_id,
                restored_checkpoint_id=cp.checkpoint_id,
                status=cp.session_status,
                active_trace_id=cp.active_trace_id,
                unresolved_goal=cp.unresolved_goal,
                waiting_for=cp.waiting_for,
                next_sequence_number=next_seq,
                restored_at=time.time(),
                complete=cp.session_status in (CognitionStatus.COMPLETED, CognitionStatus.FAILED, CognitionStatus.CANCELLED, CognitionStatus.SUPERSEDED),
                diagnostics={"traces_loaded": len(cp.traces)}
            )
            return ContinuationResult(cont, None)
            
        except Exception as e:
            return ContinuationResult(None, f"CORRUPTION_OR_FAILURE: {str(e)}")
