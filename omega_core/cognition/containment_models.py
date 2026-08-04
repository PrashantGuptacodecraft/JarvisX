"""containment_models.py - Data models for M34 Containment Kernel."""
from dataclasses import dataclass
from typing import Optional, Tuple
from enum import Enum
from .verification_models import TruthVerificationResult

class OmegaReleaseState(str, Enum):
    SEALED = "sealed"

class ContainmentStatus(str, Enum):
    SECURE = "secure"
    BREACH_ATTEMPTED = "breach_attempted"

class ContainmentViolationType(str, Enum):
    EVENT_BUS_PUBLISH = "event_bus_publish"
    TOOL_EXECUTION = "tool_execution"
    NETWORK_REQUEST = "network_request"
    UNAUTHORIZED_FILESYSTEM = "unauthorized_filesystem"
    UNSAFE_OUTPUT = "unsafe_output"

class OmegaCapability(str, Enum):
    READ_TRACE = "read_trace"
    SYNTHESIZE = "synthesize"
    VERIFY = "verify"

@dataclass(frozen=True)
class OmegaCapabilityPolicy:
    allowed_capabilities: Tuple[OmegaCapability, ...]

    def __post_init__(self):
        if "*" in self.allowed_capabilities:
            raise ValueError("Wildcard capabilities are not allowed")
        if len(set(self.allowed_capabilities)) != len(self.allowed_capabilities):
            raise ValueError("Duplicate capabilities are not allowed")

@dataclass(frozen=True)
class ContainmentViolationRecord:
    violation_type: ContainmentViolationType
    attempted_action: str
    blocked: bool

@dataclass(frozen=True)
class ContainedOmegaRequest:
    trace_id: str
    objective: str
    policy: OmegaCapabilityPolicy

@dataclass(frozen=True)
class OmegaReleaseEnvelope:
    state: OmegaReleaseState
    verification_result: TruthVerificationResult
    breach_records: Tuple[ContainmentViolationRecord, ...]

@dataclass(frozen=True)
class ContainedOmegaResult:
    trace_id: str
    status: ContainmentStatus
    envelope: Optional[OmegaReleaseEnvelope]
