from dataclasses import dataclass, field
from typing import Dict, Any, Tuple, Optional
import datetime

@dataclass(frozen=True)
class DevEventEnvelope:
    schema_version: int
    event_type: str
    event_id: str
    operation: str
    request_id: Optional[str]
    repository_id: Optional[str]
    occurred_at: str
    duration_ms: Optional[float]
    status: str
    summary: Dict[str, Any] = field(default_factory=dict)
    diagnostics: Tuple[Dict[str, Any], ...] = field(default_factory=tuple)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "event_type": self.event_type,
            "event_id": self.event_id,
            "operation": self.operation,
            "request_id": self.request_id,
            "repository_id": self.repository_id,
            "occurred_at": self.occurred_at,
            "duration_ms": self.duration_ms,
            "status": self.status,
            "summary": self.summary,
            "diagnostics": list(self.diagnostics)
        }
