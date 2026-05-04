"""
tools/terminal/controller.py
Full shell command execution + Python code writer/runner.
JARVIS can now run any terminal command and write + execute code.
"""
import os
import sys
import re
import subprocess
import tempfile
import threading
from pathlib import Path
from config.settings import USER_NAME, SAFE_MODE, WORKSPACE_DIR
from config.logger import get_logger

log = get_logger("terminal")

# Commands blocked in safe mode
BLOCKED_PATTERNS = [
    r"rm\s+-rf\s+[/~]",
    r"format\s+c:",
    r"del\s+/f\s+/s\s+/q\s+c:\\",
    r":\(\)\s*\{.*\}",   # fork bomb
    r"dd\s+if=.*of=/dev/",
    r"mkfs\.",
    r"shutdown\s+-h\s+now",  # handled separately with confirmation
]

WORK_DIR = WORKSPACE_DIR


class TerminalController:
    def __init__(self):
        WORK_DIR.mkdir(exist_ok=True)
        self._history = []

    # ─────────────────────────────────────────
    def run_command(self, command: str, timeout: int = 30) -> str:
        """Run a shell command and return output."""
        command = command.strip()
        if not command:
            return "No command provided."

        # Safety check
        if SAFE_MODE:
            for pattern in BLOCKED_PATTERNS:
                if re.search(pattern, command, re.IGNORECASE):
                    return f"⚠ Command blocked (safe mode): {command}"

        log.info(f"Running command: {command}")
        self._history.append(("cmd", command))

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(WORK_DIR),
                env=os.environ.copy()
            )
            output = ""
            if result.stdout:
                output += result.stdout
            if result.stderr:
                output += result.stderr
            if result.returncode != 0 and not output:
                output = f"(exit code {result.returncode})"
            return output.strip() or "(no output)"
        except subprocess.TimeoutExpired:
            return f"Command timed out after {timeout}s."
        except Exception as e:
            log.error(f"Command error: {e}")
            return f"Error: {e}"

    # ─────────────────────────────────────────
    def run_python_code(self, code: str, timeout: int = 15) -> str:
        """Execute Python code and return output."""
        code = code.strip()
        if not code:
            return "No code provided."

        # Remove markdown code fences if present
        code = re.sub(r'^```(?:python)?\n?', '', code, flags=re.MULTILINE)
        code = re.sub(r'\n?```$', '', code, flags=re.MULTILINE)
        code = code.strip()

        log.info(f"Running Python: {code[:80]}")
        self._history.append(("python", code))

        # Write to temp file
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.py', delete=False,
            dir=str(WORK_DIR), prefix='jarvis_'
        ) as f:
            f.write(code)
            tmp_path = f.name

        try:
            result = subprocess.run(
                [sys.executable, tmp_path],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(WORK_DIR)
            )
            output = result.stdout or result.stderr or "(no output)"
            return output.strip()[:2000]
        except subprocess.TimeoutExpired:
            return f"Python script timed out after {timeout}s."
        except Exception as e:
            return f"Python execution error: {e}"
        finally:
            try:
                os.remove(tmp_path)
            except Exception:
                pass

    # ─────────────────────────────────────────
    def write_and_run(self, description: str, ai_client) -> str:
        """Ask AI to write Python code for a task, then run it."""
        prompt = f"""Write a Python script to: {description}

Requirements:
- Complete, runnable Python 3 code
- Print results to stdout
- Handle errors with try/except
- Keep it under 50 lines
- No user input required

Return ONLY the Python code, no explanation, no markdown fences."""

        code = ai_client.chat(prompt)
        # Clean up any markdown
        code = re.sub(r'^```(?:python)?\n?', '', code, flags=re.MULTILINE)
        code = re.sub(r'\n?```$', '', code, flags=re.MULTILINE)
        code = code.strip()

        log.info(f"AI-generated code:\n{code}")
        result = self.run_python_code(code)
        return f"Code written and executed, {USER_NAME}.\nOutput:\n{result}"

    # ─────────────────────────────────────────
    def save_script(self, code: str, filename: str = None) -> str:
        """Save code as a script in the workspace."""
        if not filename:
            import datetime
            filename = f"jarvis_script_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.py"
        path = WORK_DIR / filename
        path.write_text(code, encoding="utf-8")
        return str(path)

    def get_history(self, limit: int = 20) -> list:
        return self._history[-limit:]

    def get_workspace_files(self) -> list:
        return [f.name for f in WORK_DIR.iterdir() if f.is_file()]

    def open_workspace(self) -> str:
        """Open the JARVIS workspace folder."""
        try:
            if sys.platform == "win32":
                os.startfile(str(WORK_DIR))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(WORK_DIR)])
            else:
                subprocess.Popen(["xdg-open", str(WORK_DIR)])
            return f"Workspace opened: {WORK_DIR}"
        except Exception as e:
            return f"Couldn't open workspace: {e}"

    def install_package(self, package: str) -> str:
        """Install a Python package."""
        return self.run_command(f"{sys.executable} -m pip install {package}", timeout=120)
