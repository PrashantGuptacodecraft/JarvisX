import hashlib
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import List, Optional, Any, Dict, Protocol
from datetime import datetime, timezone

from .diagnostics_model import DiagnosticRange

class ExecutionKind(str, Enum):
    TERMINAL = "terminal"
    CODE_SANDBOX = "code_sandbox"

class PreRunDecision(str, Enum):
    ALLOW = "allow"
    WARN = "warn"
    BLOCK = "block"
    NOT_ANALYZED = "not_analyzed"

class PreRunSeverity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFORMATION = "information"

class PredictionConfidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

class PredictorStatus(str, Enum):
    COMPLETED = "completed"
    NOT_APPLICABLE = "not_applicable"
    DEGRADED = "degraded"
    FAILED = "failed"

@dataclass
class ExecutionTarget:
    language: Optional[str]
    path: Optional[str]
    working_directory: Optional[str]
    inline_code_sha256: Optional[str]

    def to_dict(self) -> dict:
        return asdict(self)

@dataclass
class ExecutionRequest:
    request_id: str
    execution_kind: str
    target: ExecutionTarget
    argv: Optional[List[str]] = None
    raw_shell: bool = False
    inline_code: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("argv", None)
        d.pop("raw_shell", None)
        d.pop("inline_code", None)
        d.pop("timestamp", None)
        d["target"] = self.target.to_dict()
        return d
        
@dataclass
class FindingEvidence:
    source: str
    diagnostics_snapshot_completed_at: Optional[str] = None
    diagnostics_current: Optional[bool] = None

    def to_dict(self) -> dict:
        return asdict(self)

@dataclass
class PreRunFinding:
    predictor: str
    category: str
    severity: str
    confidence: str
    code: str
    message: str
    path: Optional[str]
    range: Optional[DiagnosticRange]
    blocks_execution: bool
    evidence: FindingEvidence

    def to_dict(self) -> dict:
        d = asdict(self)
        if self.range:
            d["range"] = self.range.to_dict()
        d["evidence"] = self.evidence.to_dict()
        return d

@dataclass
class AssessmentDiagnosticsInfo:
    snapshot_available: bool
    snapshot_completed_at: Optional[str]
    matching_count: int
    current_matching_count: int
    stale_matching_count: int

    def to_dict(self) -> dict:
        return asdict(self)

@dataclass
class PreRunSummary:
    blocking_count: int
    warning_count: int
    information_count: int
    total_count: int

    def to_dict(self) -> dict:
        return asdict(self)

@dataclass
class PredictorResult:
    name: str
    status: str
    duration_ms: int
    error_message: Optional[str]

    def to_dict(self) -> dict:
        return asdict(self)

@dataclass
class PreRunAssessment:
    schema_version: int
    request_id: str
    execution_kind: str
    target: ExecutionTarget
    started_at: str
    completed_at: str
    duration_ms: int
    decision: str
    execution_permitted: bool
    findings: List[PreRunFinding]
    diagnostics: AssessmentDiagnosticsInfo
    summary: PreRunSummary
    predictors: List[PredictorResult]

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "request_id": self.request_id,
            "execution_kind": self.execution_kind,
            "target": self.target.to_dict(),
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_ms": self.duration_ms,
            "decision": self.decision,
            "execution_permitted": self.execution_permitted,
            "findings": [f.to_dict() for f in self.findings],
            "diagnostics": self.diagnostics.to_dict(),
            "summary": self.summary.to_dict(),
            "predictors": [p.to_dict() for p in self.predictors]
        }
