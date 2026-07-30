import json
import pytest
from shared_core.tool_registry import ToolRegistry, ToolSpec, ToolExecutionResult

def dummy_handler(params: dict) -> ToolExecutionResult:
    if "fail" in params:
        raise ValueError("Intentional failure")
    return ToolExecutionResult(success=True, data={"echo": params.get("val")})

def test_e1_tool_interface_and_registry():
    registry = ToolRegistry()
    
    spec2 = ToolSpec(
        name="tool_b",
        description="Another tool",
        params_schema={"type": "object"},
        handler=dummy_handler,
        permissions=["write"]
    )
    spec1 = ToolSpec(
        name="tool_a",
        description="A test tool",
        params_schema={"type": "object", "properties": {"val": {"type": "string"}}},
        handler=dummy_handler,
        permissions=["read"]
    )
    
    # Test: Registration
    assert registry.register(spec2) is True
    assert registry.register(spec1) is True
    
    # Test: Duplicate registration
    assert registry.register(spec1) is False
    
    # Test: Deterministic listing (should sort tool_a before tool_b regardless of insert order)
    tools = registry.list_tools()
    assert len(tools) == 2
    assert tools[0].name == "tool_a"
    assert tools[1].name == "tool_b"
    
    # Test: Get tool
    assert registry.get_tool("tool_a") == spec1
    assert registry.get_tool("nonexistent") is None
    
    # Test: Dispatch success + Boundedness (returns explicit result, no leaks)
    res = registry.dispatch("tool_a", {"val": "hello"})
    assert res.success is True
    assert res.data == {"echo": "hello"}
    
    # Test: JSON serialization capability of results
    assert json.dumps(res.data) == '{"echo": "hello"}'
    
    # Test: Failure handling (unhandled exception in handler caught and bounded)
    res_fail = registry.dispatch("tool_a", {"fail": True})
    assert res_fail.success is False
    assert "Intentional failure" in res_fail.error
    assert res_fail.data is None
    
    # Test: Invalid input (nonexistent tool)
    res_missing = registry.dispatch("nonexistent", {})
    assert res_missing.success is False
    assert "Tool not found" in res_missing.error
