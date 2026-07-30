"""models.py - OMEGA Phase 7, Milestone 30 public cognition models.

Immutable dataclasses, strictly bounded and validated to prevent raw
chain-of-thought or secret leakage.
"""
from __future__ import annotations

import enum
import math
import hashlib
from dataclasses import dataclass, field
from typing import Optional, List, Tuple

class CognitionStatus(str, enum.Enum):
    CREATED = "CREATED"
    REASONING = "REASONING"
    WAITING_FOR_EVIDENCE = "WAITING_FOR_EVIDENCE"
    WAITING_FOR_USER = "WAITING_FOR_USER"
    BLOCKED = "BLOCKED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    SUPERSEDED = "SUPERSEDED"


@dataclass(frozen=True)
class EvidenceReference:
    source_id: str
    source_type: str
    excerpt: str
    content_sha256: str
    sensitivity: str
    captured_at: float

    def __post_init__(self):
        if len(self.excerpt) > 1024:
            raise ValueError("Evidence excerpt exceeds 1024 characters")
        if not self.content_sha256:
            raise ValueError("content_sha256 required")


@dataclass(frozen=True)
class DecisionSummary:
    selected_strategy: str
    alternatives_considered: Tuple[str, ...]
    decision: str
    confidence: float
    assumptions: Tuple[str, ...]
    constraints: Tuple[str, ...]

    def __post_init__(self):
        if len(self.selected_strategy) > 256:
            raise ValueError("selected_strategy exceeds 256 characters")
        if len(self.decision) > 1024:
            raise ValueError("decision exceeds 1024 characters")
        if len(self.alternatives_considered) > 10:
            raise ValueError("alternatives_considered exceeds 10 labels")
        if len(self.assumptions) > 20:
            raise ValueError("assumptions exceeds 20 items")
        if len(self.constraints) > 20:
            raise ValueError("constraints exceeds 20 items")
            
        if not isinstance(self.confidence, (float, int)):
            raise ValueError("confidence must be a float")
        
        # In Python, booleans are subclasses of int. But the rules explicitly say "Reject booleans as confidence"
        if isinstance(self.confidence, bool):
            raise ValueError("confidence cannot be boolean")
            
        if math.isnan(self.confidence) or math.isinf(self.confidence):
            raise ValueError("confidence must be finite")
            
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError("confidence must be between 0.0 and 1.0")


@dataclass(frozen=True)
class CognitionTrace:
    schema_version: int
    trace_id: str
    session_id: str
    parent_trace_id: Optional[str]
    sequence_number: int
    goal_id: str
    problem_summary: str
    evidence: Tuple[EvidenceReference, ...]
    decision: Optional[DecisionSummary]
    status: CognitionStatus
    outcome_summary: Optional[str]
    created_at: float
    updated_at: float

    def __post_init__(self):
        if len(self.problem_summary) > 500:
            raise ValueError("problem_summary exceeds 500 characters")
        if len(self.evidence) > 20:
            raise ValueError("evidence exceeds 20 references")
        if self.outcome_summary and len(self.outcome_summary) > 1024:
            raise ValueError("outcome_summary exceeds 1024 characters")


@dataclass(frozen=True)
class CognitionCheckpoint:
    schema_version: int
    checkpoint_id: str
    session_id: str
    session_status: CognitionStatus
    traces: Tuple[CognitionTrace, ...]
    active_trace_id: Optional[str]
    unresolved_goal: Optional[str]
    waiting_for: Optional[str]
    created_at: float
    previous_checkpoint_id: Optional[str]
    content_sha256: str

    def __post_init__(self):
        if len(self.traces) > 50:
            raise ValueError("Maximum active traces in a checkpoint cannot exceed 50")
            
            
@dataclass(frozen=True)
class CognitionContinuation:
    session_id: str
    restored_checkpoint_id: str
    status: CognitionStatus
    active_trace_id: Optional[str]
    unresolved_goal: Optional[str]
    waiting_for: Optional[str]
    next_sequence_number: int
    restored_at: float
    complete: bool
    diagnostics: dict
