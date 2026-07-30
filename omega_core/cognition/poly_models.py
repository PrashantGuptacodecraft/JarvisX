"""poly_models.py - Public Data Models for Milestone 31 Poly-Cognitive Engine.

Immutable dataclasses representing concurrent role execution for OMEGA System 2.
"""
import enum
from typing import Optional, Tuple, Protocol
from dataclasses import dataclass

class CognitiveRole(str, enum.Enum):
    INTUITION = "INTUITION"
    LOGIC = "LOGIC"
    CREATIVITY = "CREATIVITY"
    SKEPTICISM = "SKEPTICISM"
    ABSTRACTION = "ABSTRACTION"

class PolyRoundStatus(str, enum.Enum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    BLOCKED = "BLOCKED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"

class CancellationToken:
    """Cooperative cancellation token."""
    def __init__(self):
        self._cancelled = False
    
    def cancel(self):
        self._cancelled = True
        
    @property
    def is_cancelled(self) -> bool:
        return self._cancelled


@dataclass(frozen=True)
class CognitiveRoleRequest:
    session_id: str
    trace_id: str
    role: CognitiveRole
    problem_summary: str
    evidence_summaries: Tuple[str, ...]


@dataclass(frozen=True)
class CognitiveModelResponse:
    role: CognitiveRole
    hypothesis_or_critique: str
    confidence: float
    computation_time_ms: float

    def __post_init__(self):
        if len(self.hypothesis_or_critique) > 2048:
            raise ValueError("hypothesis_or_critique exceeds 2048 characters")
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError("confidence must be between 0.0 and 1.0")


@dataclass(frozen=True)
class RoleExecutionResult:
    role: CognitiveRole
    response: Optional[CognitiveModelResponse]
    error: Optional[str]
    is_timeout: bool


@dataclass(frozen=True)
class PolyCognitionResult:
    trace_id: str
    status: PolyRoundStatus
    role_results: Tuple[RoleExecutionResult, ...]
    is_eligible_for_synthesis: bool
    cancellation_requested: bool
    total_time_ms: float


class CognitiveModelRouter(Protocol):
    """Injected interface for external cognitive providers."""
    def generate_role_response(
        self,
        request: CognitiveRoleRequest,
        *,
        timeout_seconds: float,
        cancellation_token: CancellationToken,
    ) -> CognitiveModelResponse:
        ...
