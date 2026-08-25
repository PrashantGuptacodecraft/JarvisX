"""models.py - M36 Formal Proof Bridge Models."""
import enum
from dataclasses import dataclass, field
from typing import Tuple, Optional

class ProofOutcome(str, enum.Enum):
    PROVED = "PROVED"
    DISPROVED = "DISPROVED"
    UNKNOWN = "UNKNOWN"
    UNSUPPORTED = "UNSUPPORTED"

@dataclass(frozen=True)
class SymbolicTheorem:
    theorem_id: str
    assumptions: Tuple[str, ...]
    conclusion: str

    def __post_init__(self):
        if len(self.theorem_id) > 64:
            raise ValueError("theorem_id too long")
        if len(self.assumptions) > 20:
            raise ValueError("too many assumptions")
        for a in self.assumptions:
            if len(a) > 256:
                raise ValueError("assumption too long")
        if len(self.conclusion) > 256:
            raise ValueError("conclusion too long")

@dataclass(frozen=True)
class ProofResult:
    theorem_id: str
    outcome: ProofOutcome
    model_dump: Optional[str]
    execution_time_ms: float

    def __post_init__(self):
        if self.model_dump and len(self.model_dump) > 1024:
            # Enforce bounds on solver traces
            object.__setattr__(self, 'model_dump', self.model_dump[:1021] + "...")
