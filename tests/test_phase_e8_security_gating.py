import pytest
from shared_core.tool_registry.gap_model import ToolGap, ToolGapKind
from shared_core.tool_registry.tool_generator import ToolGenerator
from shared_core.tool_registry.sandbox_validator import ToolValidator
from shared_core.tool_registry.registry import ToolRegistry
from shared_core.tool_registry.tool_factory import ToolFactory
from shared_core.tool_registry.models import ToolSpec, ToolLifecycleState

class FakeRouterE8:
    def generate_text(self, prompt: str) -> str:
        if "pytest" in prompt:
            return """
from generated_tool import get_tool_spec
def test_tool(): pass
"""
        else:
            return """
from typing import Dict, Any
from shared_core.tool_registry.models import ToolSpec, ToolExecutionResult

def sec_handler(params: Dict[str, Any]) -> ToolExecutionResult:
    return ToolExecutionResult(success=True, data={"res": "ok"})

def get_tool_spec() -> ToolSpec:
    return ToolSpec(
        name="secure_tool",
        description="A tool requiring security gating",
        params_schema={},
        handler=sec_handler,
        permissions=["read"]
    )
"""

class FakeSecurityApprover:
    def __init__(self, approve: bool):
        self._approve = approve
        
    def approve(self, tool_code: str, spec: ToolSpec) -> bool:
        return self._approve

class FakeHumanConfirmer:
    def __init__(self, confirm: bool):
        self._confirm = confirm
        
    def confirm(self, spec: ToolSpec) -> bool:
        return self._confirm

def setup_factory(approve: bool, confirm: bool):
    router = FakeRouterE8()
    generator = ToolGenerator(router)
    validator = ToolValidator(router)
    registry = ToolRegistry()
    approver = FakeSecurityApprover(approve)
    confirmer = FakeHumanConfirmer(confirm)
    factory = ToolFactory(generator, validator, registry, security_approver=approver, human_confirmer=confirmer)
    return factory, registry

def test_security_rejected():
    factory, registry = setup_factory(approve=False, confirm=True)
    gap = ToolGap(kind=ToolGapKind.UNHANDLED_INTENT, description="test")
    
    spec = factory.build_and_register(gap)
    assert spec is not None
    assert spec.lifecycle_state == ToolLifecycleState.SECURITY_REJECTED
    
    # Not registered
    assert registry.get_tool("secure_tool") is None
    
def test_human_rejected():
    factory, registry = setup_factory(approve=True, confirm=False)
    gap = ToolGap(kind=ToolGapKind.UNHANDLED_INTENT, description="test")
    
    spec = factory.build_and_register(gap)
    assert spec is not None
    assert spec.lifecycle_state == ToolLifecycleState.USER_REJECTED
    
    # Not registered
    assert registry.get_tool("secure_tool") is None

def test_fully_approved():
    factory, registry = setup_factory(approve=True, confirm=True)
    gap = ToolGap(kind=ToolGapKind.UNHANDLED_INTENT, description="test")
    
    spec = factory.build_and_register(gap)
    assert spec is not None
    assert spec.lifecycle_state == ToolLifecycleState.ACTIVE
    
    # Registered and can run
    registered_spec = registry.get_tool("secure_tool")
    assert registered_spec is not None
    assert registered_spec.lifecycle_state == ToolLifecycleState.ACTIVE
    
    res = registry.dispatch("secure_tool", {})
    assert res.success is True
    assert res.data["res"] == "ok"
    
def test_dispatch_blocks_unconfirmed_tools():
    registry = ToolRegistry()
    def dummy_handler(p): return ToolExecutionResult(success=True)
    spec = ToolSpec(
        name="unconfirmed_tool",
        description="unconfirmed",
        params_schema={},
        handler=dummy_handler,
        lifecycle_state=ToolLifecycleState.CONFIRMATION_PENDING
    )
    registry.register(spec)
    
    res = registry.dispatch("unconfirmed_tool", {})
    assert res.success is False
    assert "cannot run" in res.error
