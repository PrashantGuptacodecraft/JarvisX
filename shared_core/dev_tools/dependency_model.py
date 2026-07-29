from dataclasses import dataclass, asdict
from enum import Enum
from typing import Any, Optional

class DependencyType(str, Enum):
    INTERNAL = "internal"
    EXTERNAL = "external"

@dataclass
class DependencyNode:
    source: str
    target: str
    dependency_type: DependencyType
    language: str
    source_location: Optional[dict[str, int]] = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["dependency_type"] = self.dependency_type.value
        return d
