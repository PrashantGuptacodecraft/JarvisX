from dataclasses import dataclass, asdict
from enum import Enum
from typing import Optional, Any

class SymbolType(str, Enum):
    CLASS = "class"
    FUNCTION = "function"
    VARIABLE = "variable"

@dataclass
class SymbolLocation:
    line: int
    column: int
    end_line: Optional[int] = None
    end_column: Optional[int] = None

@dataclass
class SymbolNode:
    name: str
    qualified_name: str
    symbol_type: SymbolType
    location: SymbolLocation
    file_path: str
    language: str
    parent_scope: Optional[str] = None
    is_async: bool = False

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["symbol_type"] = self.symbol_type.value
        return d
