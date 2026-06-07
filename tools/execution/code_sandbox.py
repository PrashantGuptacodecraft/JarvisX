"""
tools/execution/code_sandbox.py
Executes dynamically generated Python code securely and captures output.
"""
import subprocess
import os
import tempfile
from config.logger import get_logger

log = get_logger("execution.sandbox")

class CodeSandbox:
    def __init__(self):
        # Create a workspace for sandbox files
        self.workspace_dir = os.path.join(os.getcwd(), "sandbox_workspace")
        os.makedirs(self.workspace_dir, exist_ok=True)

    def execute_python(self, code: str, timeout: int = 15) -> str:
        """Executes the given python code and returns the stdout and stderr."""
        # Save code to a temporary file in the workspace
        fd, temp_path = tempfile.mkstemp(suffix=".py", dir=self.workspace_dir)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                f.write(code)
            
            log.info(f"Executing Python script at {temp_path}")
            result = subprocess.run(
                ["python", temp_path],
                capture_output=True,
                text=True,
                cwd=self.workspace_dir,
                timeout=timeout
            )
            
            output = ""
            if result.stdout:
                output += "--- STDOUT ---\n" + result.stdout + "\n"
            if result.stderr:
                output += "--- STDERR ---\n" + result.stderr + "\n"
                
            if result.returncode == 0:
                output = f"Execution Successful.\n{output}"
            else:
                output = f"Execution Failed (Exit Code: {result.returncode}).\n{output}"
                
            return output.strip() or "Execution finished silently (no output)."
            
        except subprocess.TimeoutExpired:
            log.warning("Sandbox execution timed out.")
            return "Error: Execution timed out after {} seconds.".format(timeout)
        except Exception as e:
            log.error(f"Sandbox error: {e}")
            return f"Error executing code: {e}"
        finally:
            # Clean up script
            try:
                os.remove(temp_path)
            except Exception:
                pass
