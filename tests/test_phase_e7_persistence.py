import pytest
import tempfile
from pathlib import Path
from shared_core.tool_registry.gap_model import ToolGap, ToolGapKind
from shared_core.tool_registry.tool_generator import ToolGenerator
from shared_core.tool_registry.sandbox_validator import ToolValidator
from shared_core.tool_registry.registry import ToolRegistry
from shared_core.tool_registry.tool_factory import ToolFactory, SecurityApprover, HumanConfirmationProvider
from shared_core.tool_registry.models import ToolSpec, ToolExecutionResult

class FakeRouterE7:
    def generate_text(self, prompt: str) -> str:
        if "pytest" in prompt:
            return """
from generated_tool import get_tool_spec
def test_tool(): pass
"""
        return """
from typing import Dict, Any
from shared_core.tool_registry.models import ToolSpec, ToolExecutionResult

def test_handler(params: Dict[str, Any]) -> ToolExecutionResult:
    return ToolExecutionResult(success=True, data={"result": "persisted_ok"})

def get_tool_spec() -> ToolSpec:
    return ToolSpec(
        name="persisted_tool",
        description="A tool that should be persisted",
        params_schema={},
        handler=test_handler,
        permissions=["read"]
    )
"""

class FakeSecurityApprover:
    def approve(self, code: str, spec: ToolSpec) -> bool: return True

class FakeHumanConfirmer:
    def confirm(self, spec: ToolSpec) -> bool: return True

def test_persistence_across_restart():
    with tempfile.TemporaryDirectory() as tmpdir:
        persistence_dir = Path(tmpdir) / "generated_tools"
        
        # Session 1: generate and persist
        router = FakeRouterE7()
        generator = ToolGenerator(router)
        validator = ToolValidator(router)
        registry1 = ToolRegistry()
        factory1 = ToolFactory(generator, validator, registry1, security_approver=FakeSecurityApprover(), human_confirmer=FakeHumanConfirmer(), persistence_dir=persistence_dir)
        
        gap = ToolGap(kind=ToolGapKind.UNHANDLED_INTENT, description="something")
        spec = factory1.build_and_register(gap)
        
        assert spec is not None
        assert spec.name == "persisted_tool"
        
        # Verify it was written to disk
        assert (persistence_dir / "persisted_tool.py").exists()
        
        # Session 2: relaunch (new registry, new factory)
        registry2 = ToolRegistry()
        # Initializing factory should load it
        factory2 = ToolFactory(generator, validator, registry2, persistence_dir=persistence_dir)
        
        # Verify it is invocable
        tools = registry2.list_tools()
        assert len(tools) == 1
        assert tools[0].name == "persisted_tool"
        
        res = registry2.dispatch("persisted_tool", {})
        assert res.success is True
        assert res.data["result"] == "persisted_ok"
