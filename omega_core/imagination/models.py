"""models.py - M37 Imagination Physics Engine Models."""
import enum
from dataclasses import dataclass
from typing import Tuple, Optional

class SimulationStatus(str, enum.Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    BLOCKED_BY_CONTAINMENT = "BLOCKED_BY_CONTAINMENT"

@dataclass(frozen=True)
class HypotheticalTransition:
    action_type: str
    target: str
    payload: str

    def __post_init__(self):
        if len(self.action_type) > 64: raise ValueError("action_type too long")
        if len(self.target) > 256: raise ValueError("target too long")
        if len(self.payload) > 1024: raise ValueError("payload too long")

@dataclass(frozen=True)
class SimulationResult:
    status: SimulationStatus
    error_message: Optional[str]
    state_delta: str

    def __post_init__(self):
        if len(self.state_delta) > 4096: raise ValueError("state_delta too large")
