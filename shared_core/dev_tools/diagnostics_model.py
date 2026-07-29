from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import List, Optional, Any, Dict, Protocol
from pathlib import Path

class DiagnosticSeverity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFORMATION = "information"
    HINT = "hint"

class DiagnosticExecutionStatus(str, Enum):
    COMPLETED = "completed"
    UNAVAILABLE = "unavailable"
    TIMED_OUT = "timed_out"
    INVALID_OUTPUT = "invalid_output"
    EXECUTION_FAILED = "execution_failed"

class DiagnosticsSnapshotStatus(str, Enum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"

class DiagnosticTriggerKind(str, Enum):
    MANUAL = "manual"
    FILE_CHANGED = "file_changed"
    STARTUP = "startup"

@dataclass
class DiagnosticPosition:
    line: int
    character: int

    def to_dict(self) -> dict:
        return asdict(self)

@dataclass
class DiagnosticRange:
    start: DiagnosticPosition
    end: DiagnosticPosition

    def to_dict(self) -> dict:
        return {
            "start": self.start.to_dict(),
            "end": self.end.to_dict()
        }

@dataclass
class DiagnosticFix:
    available: bool
    applicability: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

@dataclass
class CodeDiagnostic:
    path: str
    source: str
    severity: str
    code: Optional[str]
    message: str
    range: Optional[DiagnosticRange]
    fix: DiagnosticFix

    def to_dict(self) -> dict:
        d = asdict(self)
        if self.range:
            d["range"] = self.range.to_dict()
        d["fix"] = self.fix.to_dict()
        return d

@dataclass
class DiagnosticToolResult:
    name: str
    version: str
    status: str
    exit_code: int
    duration_ms: int
    diagnostic_count: int
    error_message: Optional[str]

    def to_dict(self) -> dict:
        return asdict(self)

@dataclass
class DiagnosticsSummary:
    error_count: int
    warning_count: int
    information_count: int
    hint_count: int
    total_count: int

    def to_dict(self) -> dict:
        return asdict(self)

@dataclass
class DiagnosticsTrigger:
    kind: str
    paths: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

@dataclass
class DiagnosticsSnapshot:
    schema_version: int
    trigger: DiagnosticsTrigger
    started_at: str
    completed_at: str
    duration_ms: int
    status: str
    diagnostics: List[CodeDiagnostic]
    tools: List[DiagnosticToolResult]
    summary: DiagnosticsSummary

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "trigger": self.trigger.to_dict(),
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_ms": self.duration_ms,
            "status": self.status,
            "diagnostics": [d.to_dict() for d in self.diagnostics],
            "tools": [t.to_dict() for t in self.tools],
            "summary": self.summary.to_dict()
        }

@dataclass
class DiagnosticsConfig:
    workspace_root: str
    enabled_providers: List[str] = field(default_factory=lambda: ["ruff", "pyright"])
    ruff_executable: List[str] = field(default_factory=lambda: ["ruff", "check", "--output-format=json"])
    pyright_executable: List[str] = field(default_factory=lambda: ["pyright", "--outputjson"])
    provider_timeout_seconds: float = 30.0
    debounce_seconds: float = 1.0
    max_output_bytes: int = 5 * 1024 * 1024  # 5MB
    target_paths: List[str] = field(default_factory=lambda: ["."])
    relevant_extensions: List[str] = field(default_factory=lambda: [".py", ".pyi"])
    relevant_config_files: List[str] = field(default_factory=lambda: ["pyproject.toml", "ruff.toml", ".ruff.toml", "pyrightconfig.json"])

@dataclass
class DiagnosticProviderResult:
    diagnostics: List[CodeDiagnostic]
    tool_result: DiagnosticToolResult

class DiagnosticProvider(Protocol):
    @property
    def name(self) -> str:
        ...

    def collect(
        self,
        workspace_root: Path,
        targets: tuple[str, ...],
    ) -> DiagnosticProviderResult:
        ...
