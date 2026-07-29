import subprocess
import os
import re
import uuid
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional

from .execution_gateway import ExecutionGateway
from .pre_run_model import ExecutionRequest, ExecutionTarget, ExecutionKind
from .event_models import DevEventEnvelope
from shared_core.event_bus.topics import PERCEPTION_DEV_BISECTION_COMPLETED
from shared_core.event_bus.bus import EventBus
import time
import datetime

@dataclass
class BisectionRequest:
    __test__ = False
    repository_root: str
    test_command: List[str]
    bad_commit: str = "HEAD"
    good_commit: Optional[str] = None  # If None, we will auto-discover by looking back
    max_lookback: int = 50

@dataclass
class BisectionResult:
    __test__ = False
    culprit_commit: Optional[str]
    commit_message: Optional[str]
    steps_taken: int
    log: str
    status: str

class RegressionBisector:
    def __init__(self, gateway: ExecutionGateway, event_bus: Optional[EventBus] = None):
        self.gateway = gateway
        self.event_bus = event_bus

    def execute(self, request: BisectionRequest) -> BisectionResult:
        start_time = time.time()
        repo_dir = Path(request.repository_root).resolve()
        
        # 1. Ensure clean working directory
        status_out = self._run_git(["status", "--porcelain"], repo_dir)
        if status_out.strip():
            return BisectionResult(None, None, 0, "Working directory is not clean. Commit or stash changes before bisecting.", "error")
            
        try:
            # 2. Find good commit if not provided
            good_commit = request.good_commit
            if not good_commit:
                good_commit = self._find_good_commit(repo_dir, request.test_command, request.bad_commit, request.max_lookback)
                
            if not good_commit:
                return BisectionResult(None, None, 0, f"Could not find a passing commit within {request.max_lookback} commits.", "error")
                
            # 3. Start bisect
            self._run_git(["bisect", "start", request.bad_commit, good_commit], repo_dir)
            
            # 4. Run bisect
            cmd_str = " ".join(request.test_command)
            run_out = self._run_git(["bisect", "run"] + request.test_command, repo_dir)
            
            # 5. Parse result
            culprit = None
            message = None
            
            m = re.search(r'([0-9a-f]{7,40}) is the first bad commit', run_out)
            if m:
                culprit = m.group(1)
                message = self._run_git(["log", "-1", "--format=%B", culprit], repo_dir).strip()
                
            # 6. Cleanup
            self._run_git(["bisect", "reset"], repo_dir)
            
            result = BisectionResult(
                culprit_commit=culprit,
                commit_message=message,
                steps_taken=run_out.count("Bisecting:"),
                log=run_out,
                status="success" if culprit else "failed_to_isolate"
            )
            
            if self.event_bus:
                duration_ms = (time.time() - start_time) * 1000
                env = DevEventEnvelope(
                    schema_version=1,
                    event_type=PERCEPTION_DEV_BISECTION_COMPLETED,
                    event_id=f"evt_{int(time.time()*1000)}",
                    operation="regression_bisection",
                    request_id=None,
                    repository_id=None,
                    occurred_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    duration_ms=duration_ms,
                    status=result.status,
                    summary={
                        "steps_taken": result.steps_taken,
                        "culprit_found": culprit is not None
                    }
                )
                self.event_bus.publish(PERCEPTION_DEV_BISECTION_COMPLETED, env.to_dict())
                
            return result
            
        except Exception as e:
            try:
                self._run_git(["bisect", "reset"], repo_dir)
            except:
                pass
            return BisectionResult(None, None, 0, str(e), "error")
            
    def _find_good_commit(self, repo_dir: Path, test_command: List[str], bad_commit: str, max_lookback: int) -> Optional[str]:
        commits_out = self._run_git(["log", f"--max-count={max_lookback}", "--format=%H", bad_commit], repo_dir)
        commits = commits_out.strip().split("\n")
        
        if not commits:
            return None
            
        for i, commit in enumerate(commits):
            if i == 0 and commit.startswith(self._run_git(["rev-parse", bad_commit], repo_dir).strip()):
                continue
                
            self._run_git(["checkout", commit], repo_dir)
            
            # Run test through gateway
            req = ExecutionRequest(
                request_id=f"bisect_test_{uuid.uuid4().hex[:8]}",
                execution_kind=ExecutionKind.TERMINAL.value,
                target=ExecutionTarget(language=None, path=None, working_directory=str(repo_dir), inline_code_sha256=None),
                argv=test_command,
                raw_shell=False
            )
            
            def run_test():
                try:
                    subprocess.run(test_command, cwd=str(repo_dir), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                    return {"status": "success"}
                except subprocess.CalledProcessError:
                    return {"status": "failed"}
                    
            res = self.gateway.execute(req, run_test)
            if isinstance(res, dict) and res.get("status") == "success":
                self._run_git(["checkout", "-"], repo_dir)
                return commit
                
        self._run_git(["checkout", "-"], repo_dir)
        return None
        
    def _run_git(self, args: List[str], cwd: Path) -> str:
        req = ExecutionRequest(
            request_id=f"bisect_git_{uuid.uuid4().hex[:8]}",
            execution_kind=ExecutionKind.TERMINAL.value,
            target=ExecutionTarget(language=None, path=None, working_directory=str(cwd), inline_code_sha256=None),
            argv=["git"] + args,
            raw_shell=False
        )
        
        result_box = []
        def run_cmd():
            res = subprocess.run(["git"] + args, cwd=str(cwd), capture_output=True, text=True, check=True)
            result_box.append(res.stdout)
            return {"status": "success"}
            
        gw_res = self.gateway.execute(req, run_cmd)
        if isinstance(gw_res, dict) and gw_res.get("status") == "blocked":
            raise RuntimeError(f"Git execution blocked by D8 Pre-Run Assessment: {gw_res}")
            
        if not result_box:
            raise RuntimeError(f"Git execution failed or did not return output.")
            
        return result_box[0]
