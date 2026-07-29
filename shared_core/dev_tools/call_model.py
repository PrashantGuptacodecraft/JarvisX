from dataclasses import dataclass, asdict
from enum import Enum
from typing import Any, List, Optional

class CodeRelationPredicate(str, Enum):
    CALLS = "calls"

@dataclass
class CallNode:
    caller: str
    callee: str
    resolved: bool
    candidates: List[str]
    source_location: Optional[dict[str, int]] = None
    language: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
