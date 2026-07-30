"""persistence.py - OMEGA Phase 7, Milestone 30 isolated persistence.

Atomic, schema-versioned, size-bounded JSON serialization of checkpoints.
"""
import json
import os
import tempfile
import hashlib
from typing import Dict, Any, Optional

from .models import (
    CognitionCheckpoint, CognitionTrace, CognitionStatus, 
    DecisionSummary, EvidenceReference
)

# Standardize on a single directory for OMEGA cognition that is NOT the JARVIS default history
_DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "omega_cognition"
)
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB limit


def _atomic_write_json(filepath: str, data: dict):
    """Safely write JSON using a temporary file and atomic replace."""
    encoded = json.dumps(data, indent=2, sort_keys=True).encode("utf-8")
    if len(encoded) > MAX_FILE_SIZE:
        raise ValueError(f"Payload exceeds maximum allowed size of {MAX_FILE_SIZE} bytes")
        
    dirpath = os.path.dirname(filepath)
    os.makedirs(dirpath, exist_ok=True)
    
    # Restrictive permissions: typically 0o600 for files. Windows permissions are trickier,
    # but we can rely on standard Python defaults for temp files which are secure.
    fd, temp_path = tempfile.mkstemp(dir=dirpath, text=False)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(encoded)
        os.replace(temp_path, filepath)
    except Exception:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise


def _dict_to_checkpoint(data: dict) -> CognitionCheckpoint:
    traces = []
    for t in data.get("traces", []):
        decision = None
        if t.get("decision"):
            decision = DecisionSummary(**t["decision"])
            
        evidence = []
        for e in t.get("evidence", []):
            evidence.append(EvidenceReference(**e))
            
        traces.append(CognitionTrace(
            schema_version=t["schema_version"],
            trace_id=t["trace_id"],
            session_id=t["session_id"],
            parent_trace_id=t.get("parent_trace_id"),
            sequence_number=t["sequence_number"],
            goal_id=t["goal_id"],
            problem_summary=t["problem_summary"],
            evidence=tuple(evidence),
            decision=decision,
            status=CognitionStatus(t["status"]),
            outcome_summary=t.get("outcome_summary"),
            created_at=t["created_at"],
            updated_at=t["updated_at"]
        ))
        
    return CognitionCheckpoint(
        schema_version=data["schema_version"],
        checkpoint_id=data["checkpoint_id"],
        session_id=data["session_id"],
        session_status=CognitionStatus(data["session_status"]),
        traces=tuple(traces),
        active_trace_id=data.get("active_trace_id"),
        unresolved_goal=data.get("unresolved_goal"),
        waiting_for=data.get("waiting_for"),
        created_at=data["created_at"],
        previous_checkpoint_id=data.get("previous_checkpoint_id"),
        content_sha256=data["content_sha256"]
    )


class CognitionPersistence:
    def __init__(self, base_dir: str = _DATA_DIR):
        self.base_dir = base_dir
        
    def _session_dir(self, session_id: str) -> str:
        # Prevent path traversal
        clean_id = os.path.basename(session_id)
        return os.path.join(self.base_dir, "sessions", clean_id)
        
    def save_checkpoint(self, checkpoint: CognitionCheckpoint) -> None:
        """Atomically persist a checkpoint and update the latest pointer."""
        s_dir = self._session_dir(checkpoint.session_id)
        cp_dir = os.path.join(s_dir, "checkpoints")
        os.makedirs(cp_dir, exist_ok=True)
        
        # Convert to dict
        data = {
            "schema_version": checkpoint.schema_version,
            "checkpoint_id": checkpoint.checkpoint_id,
            "session_id": checkpoint.session_id,
            "session_status": checkpoint.session_status.value,
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
                } for t in checkpoint.traces
            ],
            "active_trace_id": checkpoint.active_trace_id,
            "unresolved_goal": checkpoint.unresolved_goal,
            "waiting_for": checkpoint.waiting_for,
            "created_at": checkpoint.created_at,
            "previous_checkpoint_id": checkpoint.previous_checkpoint_id,
            "content_sha256": checkpoint.content_sha256
        }
        
        # Verify hash match to ensure integrity
        raw_content = dict(data)
        del raw_content["content_sha256"]
        del raw_content["checkpoint_id"]
        expected_hash = hashlib.sha256(json.dumps(raw_content, sort_keys=True).encode("utf-8")).hexdigest()
        if expected_hash != checkpoint.content_sha256:
            raise ValueError("content_sha256 mismatch - corruption detected during save")
            
        # Write immutable checkpoint file
        cp_file = os.path.join(cp_dir, f"{checkpoint.checkpoint_id}.json")
        _atomic_write_json(cp_file, data)
        
        # Write latest pointer
        latest_file = os.path.join(s_dir, "latest.json")
        _atomic_write_json(latest_file, {"latest_checkpoint_id": checkpoint.checkpoint_id})

    def load_latest_checkpoint(self, session_id: str) -> Optional[CognitionCheckpoint]:
        """Load the latest valid checkpoint for a session."""
        s_dir = self._session_dir(session_id)
        latest_file = os.path.join(s_dir, "latest.json")
        if not os.path.exists(latest_file):
            return None
            
        try:
            with open(latest_file, "r") as f:
                ptr = json.load(f)
        except Exception:
            return None
            
        cp_id = ptr.get("latest_checkpoint_id")
        if not cp_id:
            return None
            
        cp_file = os.path.join(s_dir, "checkpoints", f"{cp_id}.json")
        if not os.path.exists(cp_file):
            return None
            
        try:
            with open(cp_file, "r") as f:
                data = json.load(f)
            return _dict_to_checkpoint(data)
        except Exception:
            return None
