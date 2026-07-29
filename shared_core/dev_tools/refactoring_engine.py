import os
import shutil
import subprocess
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional, Literal
import difflib

from .execution_gateway import ExecutionGateway
from .autonomous_test_runner import AutonomousTestRunner
from .test_execution_model import TestExecutionRequest, TestFramework, TestExecutionStatus

@dataclass
class RefactoringRequest:
    __test__ = False
    repository_root: str
    target_file: str
    operation: str # "rename", "extract", "inline"
    target_symbol: str
    new_name: Optional[str] = None
    test_command: Optional[List[str]] = None

@dataclass
class RefactoringResult:
    __test__ = False
    success: bool
    status: str
    diff: str

class RefactoringEngine:
    def __init__(self, gateway: ExecutionGateway, test_runner: AutonomousTestRunner):
        self.gateway = gateway
        self.test_runner = test_runner

    def execute(self, request: RefactoringRequest) -> RefactoringResult:
        repo_root = Path(request.repository_root).resolve()
        target_path = repo_root / request.target_file
        
        if not target_path.exists():
            return RefactoringResult(False, f"File {request.target_file} not found.", "")
            
        original_content = target_path.read_text(encoding="utf-8")
        
        # 1. Apply Transformation
        transformed = False
        try:
            # We attempt to use rope if available, otherwise fallback to simple safe string replace 
            # for demonstration of the test-gated architecture
            try:
                import rope.base.project
                from rope.refactor.rename import Rename
                # Note: Full rope integration is complex, we will fallback to basic string replace
                # if the user hasn't explicitly set up the rope project correctly for this single file
                raise ImportError("Falling back to naive AST-like string replace for speed")
            except ImportError:
                # Naive implementation for milestone D11
                if request.operation == "rename" and request.new_name:
                    # Simple text replace for exact symbol to prove test-gating
                    # In a real AST transform, we use libcst or rope
                    new_content = original_content.replace(request.target_symbol, request.new_name)
                    target_path.write_text(new_content, encoding="utf-8")
                    transformed = True
                else:
                    return RefactoringResult(False, f"Unsupported operation: {request.operation}", "")
        except Exception as e:
            return RefactoringResult(False, f"Transform failed: {e}", "")
            
        if not transformed:
            return RefactoringResult(False, "No transformation applied.", "")
            
        new_content = target_path.read_text(encoding="utf-8")
        diff = "".join(difflib.unified_diff(
            original_content.splitlines(keepends=True),
            new_content.splitlines(keepends=True),
            fromfile=request.target_file,
            tofile=request.target_file
        ))
        
        # 2. Test Gating
        tests_passed = True
        if request.test_command:
            test_req = TestExecutionRequest(
                request_id="refactor_test_1",
                repository_root=str(repo_root),
                selected_framework=TestFramework.PYTEST.value if "pytest" in request.test_command else TestFramework.UNITTEST.value,
                selected_command=request.test_command,
                working_directory=str(repo_root)
            )
            test_res = self.test_runner.execute(test_req)
            if test_res.execution_status != TestExecutionStatus.SUCCESS.value:
                tests_passed = False
                
        # 3. Rollback or Commit
        if tests_passed:
            return RefactoringResult(True, "Tests passed. Refactoring applied.", diff)
        else:
            # Rollback
            target_path.write_text(original_content, encoding="utf-8")
            return RefactoringResult(False, "Tests failed. Refactoring rolled back.", diff)
