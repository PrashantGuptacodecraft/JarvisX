import pytest
from shared_core.tool_registry.gap_model import ToolGap, ToolGapKind
from shared_core.tool_registry.sandbox_validator import ToolValidator

class FakeTestGeneratorRouter:
    def __init__(self, succeed: bool):
        self.succeed = succeed
        
    def generate_text(self, prompt: str) -> str:
        if self.succeed:
            return """
from generated_tool import get_tool_spec

def test_tool():
    spec = get_tool_spec()
    assert spec.name == "hello_tool"
"""
        else:
            return """
def test_fail():
    assert False
"""

def test_sandbox_validation_success():
    router = FakeTestGeneratorRouter(succeed=True)
    validator = ToolValidator(router)
    
    gap = ToolGap(kind=ToolGapKind.UNHANDLED_INTENT, description="hello")
    tool_code = """
from typing import Dict, Any
from shared_core.tool_registry.models import ToolSpec, ToolExecutionResult

def hello_handler(params: Dict[str, Any]) -> ToolExecutionResult:
    return ToolExecutionResult(success=True, data={"msg": "hello"})

def get_tool_spec() -> ToolSpec:
    return ToolSpec(
        name="hello_tool",
        description="A generated hello tool",
        params_schema={"type": "object", "properties": {}},
        handler=hello_handler,
        permissions=["read"]
    )
"""
    
    assert validator.validate(tool_code, gap) is True

def test_sandbox_validation_failure():
    router = FakeTestGeneratorRouter(succeed=False)
    validator = ToolValidator(router)
    
    gap = ToolGap(kind=ToolGapKind.UNHANDLED_INTENT, description="hello")
    tool_code = "def get_tool_spec(): pass"
    
    assert validator.validate(tool_code, gap) is False
