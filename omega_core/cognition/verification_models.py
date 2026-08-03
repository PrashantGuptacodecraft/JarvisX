"""verification_models.py - Public data models for M33 Truth Verification."""
from dataclasses import dataclass
from typing import Protocol, TYPE_CHECKING
from enum import Enum

if TYPE_CHECKING:
    from .synthesis_models import CognitionSynthesis

class VerificationRole(str, Enum):
    LOGICAL_CONSISTENCY = "logical_consistency"
    EVIDENCE_AUDITOR = "evidence_auditor"
    FALSIFICATION = "falsification"
    ASSUMPTION_STRESS = "assumption_stress"
    REPRODUCIBILITY = "reproducibility"

@dataclass(frozen=True)
class TruthVerificationResult:
    trace_id: str
    verified_true: bool
    falsification_report: str
    verification_confidence: float

    def __post_init__(self):
        if len(self.falsification_report) > 1024:
            raise ValueError("falsification_report exceeds 1024 characters limit")
        if not (0.0 <= self.verification_confidence <= 1.0):
            raise ValueError("verification_confidence must be between 0.0 and 1.0")

@dataclass(frozen=True)
class AdversarialResult:
    passed: bool
    argument: str
    confidence: float

class AdversarialRouter(Protocol):
    """Protocol for the injected adversarial verifier router."""
    def probe(self, synthesis: 'CognitionSynthesis', strategy: str) -> AdversarialResult:
        ...
