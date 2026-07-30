import pytest
import tempfile
from pathlib import Path
from shared_core.tool_registry.registry import ToolRegistry
from shared_core.tool_registry.adapters import register_core_adapters

def test_e2_adapters():
    registry = ToolRegistry()
    register_core_adapters(registry)
    
    tools = registry.list_tools()
    assert len(tools) == 3
    names = [t.name for t in tools]
    assert "ast_parser" in names
    assert "dependency_analyzer" in names
    assert "test_runner" in names

    # Test AST Parser adapter
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        py_file = tmp_path / "test.py"
        py_file.write_text("def hello(): pass")
        
        res = registry.dispatch("ast_parser", {"file_path": str(py_file)})
        assert res.success is True
        assert len(res.data["symbols"]) == 1
        assert res.data["symbols"][0]["name"] == "hello"

    # Dependency Analyzer and Test Runner are heavier, but we can verify their parameters
    ast_spec = registry.get_tool("ast_parser")
    dep_spec = registry.get_tool("dependency_analyzer")
    test_spec = registry.get_tool("test_runner")
    
    assert ast_spec.permissions == ["read"]
    assert dep_spec.permissions == ["read"]
    assert test_spec.permissions == ["execute"]
