from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Any, Dict
from datetime import datetime, timezone

class TestFramework(str, Enum):
    __test__ = False
    PYTEST = "pytest"
    UNITTEST = "unittest"
    UNKNOWN = "unknown"

class TestExecutionStatus(str, Enum):
    __test__ = False
    SUCCESS = "success"
    FAILURE = "failure"
    BLOCKED = "blocked"
    TIMEOUT = "timeout"
    ERROR = "error"

@dataclass
class TestDetectionResult:
    __test__ = False
    framework: str
    command: List[str]
    working_directory: str
    is_ambiguous: bool
    reason: Optional[str]

    def to_dict(self) -> dict:
        return {
            "framework": self.framework,
            "command": self.command,
            "working_directory": self.working_directory,
            "is_ambiguous": self.is_ambiguous,
            "reason": self.reason
        }

@dataclass
class TestExecutionRequest:
    __test__ = False
    request_id: str
    repository_root: str
    selected_framework: str
    selected_command: List[str]
    working_directory: str
    target_scope: Optional[str] = None
    timeout_seconds: int = 60
    environment_policy: str = "inherit"

    def to_dict(self) -> dict:
        return {
            "request_id": self.request_id,
            "repository_root": self.repository_root,
            "selected_framework": self.selected_framework,
            "selected_command": self.selected_command,
            "working_directory": self.working_directory,
            "target_scope": self.target_scope,
            "timeout_seconds": self.timeout_seconds,
            "environment_policy": self.environment_policy
        }

@dataclass
class TestExecutionResult:
    __test__ = False
    request_id: str
    execution_status: str
    exit_code: Optional[int]
    started_at: str
    completed_at: str
    duration_ms: int
    passed_count: int
    failed_count: int
    skipped_count: int
    error_count: int
    stdout: str
    stderr: str
    timeout_flag: bool
    diagnostics: List[dict]
    d8_assessment: Optional[dict]

    def to_dict(self) -> dict:
        return {
            "request_id": self.request_id,
            "execution_status": self.execution_status,
            "exit_code": self.exit_code,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_ms": self.duration_ms,
            "passed_count": self.passed_count,
            "failed_count": self.failed_count,
            "skipped_count": self.skipped_count,
            "error_count": self.error_count,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "timeout_flag": self.timeout_flag,
            "diagnostics": self.diagnostics,
            "d8_assessment": self.d8_assessment
        }
