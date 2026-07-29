import subprocess
import time
import re
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

from .execution_gateway import ExecutionGateway
from .pre_run_model import ExecutionRequest, ExecutionTarget, ExecutionKind
from .test_execution_model import TestExecutionRequest, TestExecutionResult, TestExecutionStatus, TestFramework
from .event_models import DevEventEnvelope
from shared_core.event_bus.topics import PERCEPTION_DEV_TESTS_COMPLETED
from shared_core.event_bus.bus import EventBus

class AutonomousTestRunner:
    def __init__(self, gateway: ExecutionGateway, event_bus: Optional[EventBus] = None):
        self.gateway = gateway
        self.event_bus = event_bus
        self.MAX_LOG_SIZE = 500 * 1024 # 500 KB limit

    def execute(self, request: TestExecutionRequest) -> TestExecutionResult:
        # 1. Build D8 gateway request
        req = ExecutionRequest(
            request_id=request.request_id,
            execution_kind=ExecutionKind.TERMINAL.value,
            target=ExecutionTarget(
                language=None, 
                path=None, 
                working_directory=request.working_directory, 
                inline_code_sha256=None
            ),
            argv=request.selected_command,
            raw_shell=False
        )

        started_at = datetime.now(timezone.utc)
        d8_assessment = None

        # 1.5 Auto-provision venv if needed
        venv_path = Path(request.repository_root) / ".venv"
        if not venv_path.exists():
            import sys
            venv_req = ExecutionRequest(
                request_id=f"{request.request_id}_venv",
                execution_kind=ExecutionKind.TERMINAL.value,
                target=ExecutionTarget(language=None, path=None, working_directory=request.repository_root, inline_code_sha256=None),
                argv=[sys.executable, "-m", "venv", str(venv_path)],
                raw_shell=False
            )
            def run_venv():
                try:
                    subprocess.run(
                        [sys.executable, "-m", "venv", str(venv_path)],
                        check=True,
                        capture_output=True
                    )
                    return {"status": "success"}
                except subprocess.CalledProcessError as e:
                    return {"status": "error"}
            
            # Route venv creation through D8 Gateway
            self.gateway.execute(venv_req, run_venv)

        # 2. Define the executor
        def run_test_process():
            cmd = request.selected_command
            
            # Optionally add quiet flags for easier parsing if not present
            if request.selected_framework == TestFramework.PYTEST.value and "-q" not in cmd and "--quiet" not in cmd:
                cmd = cmd + ["-q"]
            
            try:
                proc = subprocess.Popen(
                    cmd,
                    cwd=request.working_directory,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding='utf-8',
                    errors='replace'
                )
                
                try:
                    out, err = proc.communicate(timeout=request.timeout_seconds)
                    timeout_flag = False
                except subprocess.TimeoutExpired:
                    proc.kill()
                    out, err = proc.communicate()
                    timeout_flag = True

                # Bound outputs
                if len(out) > self.MAX_LOG_SIZE:
                    out = out[:self.MAX_LOG_SIZE] + "\n...[stdout truncated]..."
                if len(err) > self.MAX_LOG_SIZE:
                    err = err[:self.MAX_LOG_SIZE] + "\n...[stderr truncated]..."

                return {
                    "status": TestExecutionStatus.SUCCESS.value if proc.returncode == 0 else TestExecutionStatus.FAILURE.value,
                    "exit_code": proc.returncode,
                    "timeout_flag": timeout_flag,
                    "stdout": out,
                    "stderr": err
                }
            except Exception as e:
                return {
                    "status": TestExecutionStatus.ERROR.value,
                    "exit_code": -1,
                    "timeout_flag": False,
                    "stdout": "",
                    "stderr": str(e)
                }

        # 3. Go through gateway
        start_ms = time.time()
        gw_result = self.gateway.execute(req, run_test_process)
        duration_ms = int((time.time() - start_ms) * 1000)
        completed_at = datetime.now(timezone.utc)

        # 4. Handle blocked status
        if isinstance(gw_result, dict) and gw_result.get("status") == "blocked":
            return TestExecutionResult(
                request_id=request.request_id,
                execution_status=TestExecutionStatus.BLOCKED.value,
                exit_code=None,
                started_at=started_at.isoformat(),
                completed_at=completed_at.isoformat(),
                duration_ms=duration_ms,
                passed_count=0,
                failed_count=0,
                skipped_count=0,
                error_count=0,
                stdout="",
                stderr="Execution blocked by D8 Pre-Run Assessment.",
                timeout_flag=False,
                diagnostics=gw_result.get("findings", []),
                d8_assessment=None # Can't fetch directly without bus listener, but we know it's blocked
            )

        # 5. Parse test results
        status = gw_result["status"]
        if gw_result["timeout_flag"]:
            status = TestExecutionStatus.TIMEOUT.value
            
        passed = failed = skipped = errors = 0
        
        stdout_text = gw_result["stdout"]
        if request.selected_framework == TestFramework.PYTEST.value:
            # e.g. "1 failed, 2 passed, 1 skipped, 1 warning, 1 error in 0.12s"
            # e.g. "3 passed in 0.05s"
            if "passed" in stdout_text:
                m = re.search(r'(\d+)\s+passed', stdout_text)
                if m: passed = int(m.group(1))
            if "failed" in stdout_text:
                m = re.search(r'(\d+)\s+failed', stdout_text)
                if m: failed = int(m.group(1))
            if "skipped" in stdout_text:
                m = re.search(r'(\d+)\s+skipped', stdout_text)
                if m: skipped = int(m.group(1))
            if "error" in stdout_text:
                m = re.search(r'(\d+)\s+error', stdout_text)
                if m: errors = int(m.group(1))
                
        elif request.selected_framework == TestFramework.UNITTEST.value:
            # Ran X tests
            m = re.search(r'Ran (\d+) tests', gw_result["stderr"])
            if not m:
                m = re.search(r'Ran (\d+) tests', gw_result["stdout"])
            
            total = int(m.group(1)) if m else 0
            
            # FAILED (failures=1, errors=1, skipped=1)
            f_m = re.search(r'failures=(\d+)', gw_result["stderr"])
            e_m = re.search(r'errors=(\d+)', gw_result["stderr"])
            s_m = re.search(r'skipped=(\d+)', gw_result["stderr"])
            
            failed = int(f_m.group(1)) if f_m else 0
            errors = int(e_m.group(1)) if e_m else 0
            skipped = int(s_m.group(1)) if s_m else 0
            
            if status == TestExecutionStatus.SUCCESS.value and total > 0:
                passed = total - skipped
            else:
                passed = max(0, total - failed - errors - skipped)

        result = TestExecutionResult(
            request_id=request.request_id,
            execution_status=status,
            exit_code=gw_result["exit_code"],
            started_at=started_at.isoformat(),
            completed_at=completed_at.isoformat(),
            duration_ms=duration_ms,
            passed_count=passed,
            failed_count=failed,
            skipped_count=skipped,
            error_count=errors,
            stdout=gw_result["stdout"],
            stderr=gw_result["stderr"],
            timeout_flag=gw_result["timeout_flag"],
            diagnostics=[],
            d8_assessment=None # If we need to capture this, we'd have to snoop the bus or modify gateway to return it
        )
        
        if self.event_bus:
            env = DevEventEnvelope(
                schema_version=1,
                event_type=PERCEPTION_DEV_TESTS_COMPLETED,
                event_id=f"evt_{int(time.time()*1000)}",
                operation="test_execution",
                request_id=request.request_id,
                repository_id=None,
                occurred_at=datetime.now(timezone.utc).isoformat(),
                duration_ms=duration_ms,
                status=status,
                summary={
                    "passed": passed,
                    "failed": failed,
                    "skipped": skipped,
                    "errors": errors
                }
            )
            self.event_bus.publish(PERCEPTION_DEV_TESTS_COMPLETED, env.to_dict())
            
        return result
