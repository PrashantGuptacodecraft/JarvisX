from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
from enum import Enum

class ToolLifecycleState(str, Enum):
    GENERATED = "generated"
    VALIDATED = "validated"
    SECURITY_REJECTED = "security_rejected"
    SECURITY_APPROVED = "security_approved"
    CONFIRMATION_PENDING = "confirmation_pending"
    USER_REJECTED = "user_rejected"
    ACTIVE = "active"
    REVOKED = "revoked"
    QUARANTINED = "quarantined"

@dataclass(frozen=True)
class ToolExecutionResult:
    """Explicit bounded result for tool execution."""
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

# A tool handler takes a dictionary of parameters and returns a ToolExecutionResult.
ToolHandler = Callable[[Dict[str, Any]], ToolExecutionResult]

@dataclass(frozen=False)
class ToolSpec:
    """Formal Tool interface definition."""
    name: str
    description: str
    params_schema: Dict[str, Any]
    handler: ToolHandler
    permissions: List[str] = field(default_factory=list)
    lifecycle_state: ToolLifecycleState = ToolLifecycleState.ACTIVE
