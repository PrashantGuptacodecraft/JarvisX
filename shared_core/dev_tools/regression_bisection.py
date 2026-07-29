import subprocess
import os
import re
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional

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
    def execute(self, request: BisectionRequest) -> BisectionResult:
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
            # git bisect run can take a shell command
            # Using a shell script is safer for git bisect run, but we can pass the command directly
            run_out = self._run_git(["bisect", "run"] + request.test_command, repo_dir)
            
            # 5. Parse result
            culprit = None
            message = None
            
            # Format usually: "<commit_hash> is the first bad commit"
            m = re.search(r'([0-9a-f]{7,40}) is the first bad commit', run_out)
            if m:
                culprit = m.group(1)
                # Get commit message
                message = self._run_git(["log", "-1", "--format=%B", culprit], repo_dir).strip()
                
            # 6. Cleanup
            self._run_git(["bisect", "reset"], repo_dir)
            
            return BisectionResult(
                culprit_commit=culprit,
                commit_message=message,
                steps_taken=run_out.count("Bisecting:"),
                log=run_out,
                status="success" if culprit else "failed_to_isolate"
            )
            
        except Exception as e:
            # Try to abort in case of error
            try:
                self._run_git(["bisect", "reset"], repo_dir)
            except:
                pass
            return BisectionResult(None, None, 0, str(e), "error")
            
    def _find_good_commit(self, repo_dir: Path, test_command: List[str], bad_commit: str, max_lookback: int) -> Optional[str]:
        # Walk commits backwards
        commits_out = self._run_git(["log", f"--max-count={max_lookback}", "--format=%H", bad_commit], repo_dir)
        commits = commits_out.strip().split("\n")
        
        if not commits:
            return None
            
        for i, commit in enumerate(commits):
            # Skip the known bad commit if it's the first one
            if i == 0 and commit.startswith(self._run_git(["rev-parse", bad_commit], repo_dir).strip()):
                continue
                
            # Checkout
            self._run_git(["checkout", commit], repo_dir)
            
            # Test
            try:
                subprocess.run(test_command, cwd=str(repo_dir), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                # Success!
                self._run_git(["checkout", "-"], repo_dir)
                return commit
            except subprocess.CalledProcessError:
                # Still failing
                pass
                
        self._run_git(["checkout", "-"], repo_dir)
        return None
        
    def _run_git(self, args: List[str], cwd: Path) -> str:
        res = subprocess.run(["git"] + args, cwd=str(cwd), capture_output=True, text=True, check=True)
        return res.stdout
