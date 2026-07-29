from dataclasses import dataclass
from enum import Enum
from typing import Dict, Any, List

class StyleEvidenceSource(str, Enum):
    CONFIG = "config"
    SOURCE = "source"
    DIAGNOSTIC = "diagnostic"
    MANUAL = "manual"

@dataclass
class StyleEvidence:
    source: StyleEvidenceSource
    description: str
    weight: float

@dataclass
class CodingStyleModel:
    __test__ = False
    indent_style: str = "space"
    indent_size: int = 4
    max_line_length: int = 88
    quotes: str = "double"
    naming_conventions: Dict[str, str] = None
    evidences: List[StyleEvidence] = None

    def __post_init__(self):
        if self.naming_conventions is None:
            self.naming_conventions = {
                "class": "PascalCase",
                "function": "snake_case",
                "variable": "snake_case",
                "constant": "UPPER_SNAKE_CASE"
            }
        if self.evidences is None:
            self.evidences = []
