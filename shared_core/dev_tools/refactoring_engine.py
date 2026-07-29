import os
import shutil
import subprocess
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional
from enum import Enum
import difflib

from .execution_gateway import ExecutionGateway
from .autonomous_test_runner import AutonomousTestRunner
from .test_execution_model import TestExecutionRequest, TestFramework, TestExecutionStatus

class RefactoringOperation(str, Enum):
    RENAME = "rename"
    EXTRACT = "extract"
    INLINE = "inline"

@dataclass
class RefactoringRequest:
    __test__ = False
    repository_root: str
    target_file: str
    operation: RefactoringOperation
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
            try:
                import libcst as cst
            except ImportError:
                return RefactoringResult(False, "dependency_unavailable: libcst is not installed", "")

            if request.operation == RefactoringOperation.RENAME and request.new_name:
                class RenameTransformer(cst.CSTTransformer):
                    def __init__(self, old_name: str, new_name: str):
                        self.old_name = old_name
                        self.new_name = new_name
                        
                    def leave_Name(self, original_node: cst.Name, updated_node: cst.Name) -> cst.Name:
                        if original_node.value == self.old_name:
                            return updated_node.with_changes(value=self.new_name)
                        return updated_node

                module = cst.parse_module(original_content)
                transformer = RenameTransformer(request.target_symbol, request.new_name)
                modified_module = module.visit(transformer)
                
                new_content = modified_module.code
                if new_content != original_content:
                    target_path.write_text(new_content, encoding="utf-8")
                    transformed = True
            elif request.operation in (RefactoringOperation.EXTRACT, RefactoringOperation.INLINE):
                return RefactoringResult(False, f"not_supported: {request.operation} is not implemented yet", "")
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
