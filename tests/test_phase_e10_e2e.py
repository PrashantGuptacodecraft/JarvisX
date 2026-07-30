import pytest
from shared_core.tool_registry.models import ToolSpec, ToolExecutionResult, ToolLifecycleState
from shared_core.tool_registry.registry import ToolRegistry
from shared_core.tool_registry.tool_factory import ToolFactory
from shared_core.tool_registry.tool_generator import ToolGenerator
from shared_core.tool_registry.sandbox_validator import ToolValidator
from shared_core.tool_registry.gap_detector import ToolGapDetector, ToolGap, ToolGapKind

class FakeRouterE10:
    def generate_text(self, prompt: str) -> str:
        if "pytest" in prompt:
            return """
from generated_tool import get_tool_spec, run_calculator
def test_calculator():
    res = run_calculator({"a": 5, "b": 7})
    assert res.success
    assert res.data["result"] == 12
"""
        return """
from typing import Dict, Any
from shared_core.tool_registry.models import ToolSpec, ToolExecutionResult

def run_calculator(params: Dict[str, Any]) -> ToolExecutionResult:
    a = params.get("a", 0)
    b = params.get("b", 0)
    return ToolExecutionResult(success=True, data={"result": a + b})

def get_tool_spec() -> ToolSpec:
    return ToolSpec(
        name="calculator_tool",
        description="Adds two numbers",
        params_schema={"a": "int", "b": "int"},
        handler=run_calculator,
        permissions=["read"]
    )
"""

class FakeSecurityApprover:
    def approve(self, code: str, spec: ToolSpec) -> bool: return True

class FakeHumanConfirmer:
    def confirm(self, spec: ToolSpec) -> bool: return True

def test_e10_end_to_end_factory():
    # 1. Setup the factory components
    router = FakeRouterE10()
    registry = ToolRegistry()
    generator = ToolGenerator(router)
    validator = ToolValidator(router)
    detector = ToolGapDetector(registry)
    
    factory = ToolFactory(
        generator=generator, 
        validator=validator, 
        registry=registry, 
        security_approver=FakeSecurityApprover(), 
        human_confirmer=FakeHumanConfirmer()
    )
    
    # 2. Detect a gap
    user_request = "add 5 and 7"
    gap = detector.detect_intent_gap(user_request)
    
    assert gap is not None
    assert gap.kind == ToolGapKind.UNHANDLED_INTENT
    
    # 3. Generate, validate, register
    spec = factory.build_and_register(gap)
    
    assert spec is not None
    assert spec.name == "calculator_tool"
    assert spec.lifecycle_state == ToolLifecycleState.ACTIVE
    
    # 4. Verify registered in live registry
    tools = registry.list_tools()
    assert len(tools) == 1
    assert tools[0].name == "calculator_tool"
    
    # 5. Dispatch and verify invocation
    res = registry.dispatch("calculator_tool", {"a": 5, "b": 7})
    assert res.success is True
    assert res.data["result"] == 12
