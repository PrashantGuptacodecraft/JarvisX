from typing import Optional
from .gap_model import ToolGap
from .llm_router import LLMRouter

class ToolGenerator:
    def __init__(self, router: LLMRouter):
        self.router = router
        
    def generate_tool_module(self, gap: ToolGap) -> str:
        """
        Generates Python source code for a ToolSpec-conforming module 
        that addresses the specified ToolGap.
        The generated module must define a function `get_tool_spec() -> ToolSpec`.
        """
        prompt = f"""
        You are an AI that writes Python tools for the JarvisX system.
        We detected a capability gap:
        - Kind: {gap.kind.value}
        - Description: {gap.description}
        - Suggested Tool Name: {gap.suggested_tool_name}
        
        Write a Python module that implements this tool.
        The module MUST contain:
        1. A handler function that takes a dict `params` and returns a `ToolExecutionResult`.
        2. A `get_tool_spec() -> ToolSpec` function that returns the tool's specification.
        
        Use the following imports:
        from typing import Dict, Any
        from shared_core.tool_registry.models import ToolSpec, ToolExecutionResult
        
        Return ONLY valid Python code, no markdown formatting.
        """
        
        source = self.router.generate_text(prompt)
        
        # Clean up markdown blocks if the LLM output them despite instructions
        if source.startswith("```python"):
            source = source[len("```python"):].strip()
        if source.startswith("```"):
            source = source[len("```"):].strip()
        if source.endswith("```"):
            source = source[:-len("```")].strip()
            
        return source.strip()
