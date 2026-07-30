import pytest
from shared_core.tool_registry.gap_model import ToolGap, ToolGapKind
from shared_core.tool_registry.tool_generator import ToolGenerator

class FakeDeterministicRouter:
    def generate_text(self, prompt: str) -> str:
        # We look for the suggested tool name in the prompt
        if "hello_tool" in prompt:
            return """
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
        return ""

def test_tool_generation():
    router = FakeDeterministicRouter()
    generator = ToolGenerator(router)
    
    gap = ToolGap(
        kind=ToolGapKind.UNHANDLED_INTENT,
        description="I want to say hello",
        suggested_tool_name="hello_tool"
    )
    
    code = generator.generate_tool_module(gap)
    
    # We should be able to compile it and get the tool spec
    namespace = {}
    exec(code, namespace)
    
    assert "get_tool_spec" in namespace
    get_spec = namespace["get_tool_spec"]
    
    spec = get_spec()
    assert spec.name == "hello_tool"
    assert spec.description == "A generated hello tool"
    
    # Check the handler
    res = spec.handler({})
    assert res.success is True
    assert res.data["msg"] == "hello"
