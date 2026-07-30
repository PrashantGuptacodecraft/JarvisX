from enum import Enum
from dataclasses import dataclass, asdict
from typing import Optional, List, Any

class ToolGapKind(str, Enum):
    UNHANDLED_INTENT = "unhandled_intent"
    REPEATED_SEQUENCE = "repeated_sequence"

@dataclass
class ToolGap:
    kind: ToolGapKind
    description: str
    suggested_tool_name: Optional[str] = None
    evidence: Optional[List[str]] = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["kind"] = self.kind.value
        return d
