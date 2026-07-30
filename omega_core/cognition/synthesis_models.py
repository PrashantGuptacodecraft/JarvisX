"""synthesis_models.py - Public Data Models for Milestone 32 Synthesis Matrix.

Immutable dataclasses representing the debate and convergence phase.
"""
import enum
from dataclasses import dataclass
from typing import Tuple, Optional, Protocol
from .poly_models import CognitiveRole

class SynthesisStatus(str, enum.Enum):
    SUCCESS = "SUCCESS"
    INELIGIBLE = "INELIGIBLE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"

@dataclass(frozen=True)
class CognitionSynthesis:
    trace_id: str
    status: SynthesisStatus
    agreements: Tuple[str, ...]
    contradictions: Tuple[str, ...]
    complementary_proposals: Tuple[str, ...]
    evidence_gaps: Tuple[str, ...]
    safety_objections: Tuple[str, ...]
    unresolved_questions: Tuple[str, ...]
    selected_strategy: Optional[str]
    final_decision: Optional[str]
    supporting_roles: Tuple[CognitiveRole, ...]
    deterministic_confidence: float

    def __post_init__(self):
        if self.selected_strategy and len(self.selected_strategy) > 256:
            raise ValueError("selected_strategy exceeds 256 chars")
        if self.final_decision and len(self.final_decision) > 1024:
            raise ValueError("final_decision exceeds 1024 chars")

@dataclass(frozen=True)
class DebateMatrix:
    trace_id: str
    role_summaries: Tuple[Tuple[CognitiveRole, str], ...]

@dataclass(frozen=True)
class SynthesisRouterResponse:
    agreements: Tuple[str, ...]
    contradictions: Tuple[str, ...]
    complementary_proposals: Tuple[str, ...]
    evidence_gaps: Tuple[str, ...]
    safety_objections: Tuple[str, ...]
    unresolved_questions: Tuple[str, ...]
    selected_strategy: str
    final_decision: str
    supporting_roles: Tuple[CognitiveRole, ...]

class CognitiveSynthesisRouter(Protocol):
    """Injected interface for external cognitive providers to perform convergence."""
    def synthesize(self, matrix: DebateMatrix) -> SynthesisRouterResponse:
        ...
