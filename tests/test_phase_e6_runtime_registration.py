import pytest
from shared_core.tool_registry.gap_model import ToolGap, ToolGapKind
from shared_core.tool_registry.tool_generator import ToolGenerator
from shared_core.tool_registry.sandbox_validator import ToolValidator
from shared_core.tool_registry.registry import ToolRegistry
from shared_core.tool_registry.tool_factory import ToolFactory

class FakeRouterE6:
    def __init__(self, succeed_gen: bool, succeed_val: bool):
        self.succeed_gen = succeed_gen
        self.succeed_val = succeed_val
        
    def generate_text(self, prompt: str) -> str:
        if "pytest" in prompt:
            if self.succeed_val:
                return """
from generated_tool import get_tool_spec
def test_tool():
    spec = get_tool_spec()
    assert spec.name == "runtime_tool"
"""
            else:
                return "def test_fail(): assert False"
        else:
            if self.succeed_gen:
                return """
from typing import Dict, Any
from shared_core.tool_registry.models import ToolSpec, ToolExecutionResult

def rt_handler(params: Dict[str, Any]) -> ToolExecutionResult:
    return ToolExecutionResult(success=True, data={"res": "ok"})

def get_tool_spec() -> ToolSpec:
    return ToolSpec(
        name="runtime_tool",
        description="A runtime registered tool",
        params_schema={},
        handler=rt_handler,
        permissions=["read"]
    )
"""
            else:
                return "def get_tool_spec(): raise Exception('gen error')"

class FakeSecurityApprover:
    def approve(self, code: str, spec: ToolSpec) -> bool: return True

class FakeHumanConfirmer:
    def confirm(self, spec: ToolSpec) -> bool: return True

def test_runtime_registration_success():
    router = FakeRouterE6(succeed_gen=True, succeed_val=True)
    generator = ToolGenerator(router)
    validator = ToolValidator(router)
    registry = ToolRegistry()
    factory = ToolFactory(generator, validator, registry, security_approver=FakeSecurityApprover(), human_confirmer=FakeHumanConfirmer())
    
    gap = ToolGap(kind=ToolGapKind.UNHANDLED_INTENT, description="something")
    
    spec = factory.build_and_register(gap)
    assert spec is not None
    assert spec.name == "runtime_tool"
    
    # Verify it is invocable without restart
    res = registry.dispatch("runtime_tool", {})
    assert res.success is True
    assert res.data["res"] == "ok"

def test_runtime_registration_validation_fails():
    router = FakeRouterE6(succeed_gen=True, succeed_val=False)
    generator = ToolGenerator(router)
    validator = ToolValidator(router)
    registry = ToolRegistry()
    factory = ToolFactory(generator, validator, registry)
    
    gap = ToolGap(kind=ToolGapKind.UNHANDLED_INTENT, description="something")
    
    spec = factory.build_and_register(gap)
    assert spec is None
    
    # Tool should not be registered
    tools = registry.list_tools()
    assert len(tools) == 0
