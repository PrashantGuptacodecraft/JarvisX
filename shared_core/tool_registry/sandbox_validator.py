from typing import Optional
import tempfile
from pathlib import Path
from .llm_router import LLMRouter
from .gap_model import ToolGap
import subprocess
import sys

class ToolValidator:
    def __init__(self, router: LLMRouter):
        self.router = router
        
    def generate_tests(self, tool_code: str, gap: ToolGap) -> str:
        prompt = f"""
        You are an AI that writes tests for JarvisX tools.
        Write a pytest module that tests the following generated tool.
        
        Tool Code:
        ```python
        {tool_code}
        ```
        
        The tool implements: {gap.description}
        
        Return ONLY valid Python code containing pytest test cases. Do not include markdown formatting.
        """
        source = self.router.generate_text(prompt)
        
        if source.startswith("```python"):
            source = source[len("```python"):].strip()
        if source.startswith("```"):
            source = source[len("```"):].strip()
        if source.endswith("```"):
            source = source[:-len("```")].strip()
            
        return source.strip()
        
    def validate(self, tool_code: str, gap: ToolGap) -> bool:
        """
        Validates the tool by generating tests and running them in a temporary sandbox.
        """
        test_code = self.generate_tests(tool_code, gap)
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            tool_path = temp_path / "generated_tool.py"
            test_path = temp_path / "test_generated_tool.py"
            
            tool_path.write_text(tool_code, encoding="utf-8")
            
            # Make sure test imports the tool
            # Assuming the test code does `from generated_tool import ...`
            test_path.write_text(test_code, encoding="utf-8")
            
            # Run pytest in the sandbox
            import os
            env = os.environ.copy()
            # Add the current working directory to PYTHONPATH so it can import shared_core
            env["PYTHONPATH"] = str(Path.cwd().resolve())
            
            try:
                result = subprocess.run(
                    [sys.executable, "-m", "pytest", str(test_path)],
                    cwd=str(temp_path),
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                return result.returncode == 0
            except subprocess.TimeoutExpired:
                return False
            except Exception:
                return False
