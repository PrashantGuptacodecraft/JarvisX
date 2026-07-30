from pathlib import Path
from typing import Dict, Any

from .models import ToolSpec, ToolExecutionResult
from .registry import ToolRegistry
from shared_core.dev_tools.ast_parser import PythonASTParser
from shared_core.dev_tools.dependency_analyzer import DependencyAnalyzer
from shared_core.dev_tools.test_framework_detection import TestFrameworkDetector
from shared_core.dev_tools.autonomous_test_runner import AutonomousTestRunner
from shared_core.dev_tools.test_execution_model import TestExecutionRequest, TestFramework
from shared_core.dev_tools.execution_gateway import ExecutionGateway

def parse_ast_handler(params: Dict[str, Any]) -> ToolExecutionResult:
    file_path_str = params.get("file_path")
    if not file_path_str:
        return ToolExecutionResult(success=False, error="Missing file_path")
    
    file_path = Path(file_path_str)
    if not file_path.exists():
        return ToolExecutionResult(success=False, error="File does not exist")
        
    parser = PythonASTParser()
    try:
        symbols = parser.parse_file(file_path)
        return ToolExecutionResult(success=True, data={"symbols": [s.to_dict() for s in symbols]})
    except Exception as e:
        return ToolExecutionResult(success=False, error=str(e))

def analyze_dependencies_handler(params: Dict[str, Any]) -> ToolExecutionResult:
    root_dir_str = params.get("root_dir")
    if not root_dir_str:
        return ToolExecutionResult(success=False, error="Missing root_dir")
        
    root_dir = Path(root_dir_str)
    analyzer = DependencyAnalyzer(root_dir)
    try:
        nodes = analyzer.analyze()
        return ToolExecutionResult(success=True, data={"dependencies": [n.to_dict() for n in nodes]})
    except Exception as e:
        return ToolExecutionResult(success=False, error=str(e))

def run_tests_handler(params: Dict[str, Any]) -> ToolExecutionResult:
    repo_root_str = params.get("repository_root")
    if not repo_root_str:
        return ToolExecutionResult(success=False, error="Missing repository_root")
        
    repo_root = Path(repo_root_str)
    gateway = ExecutionGateway(workspace_root=repo_root)
    runner = AutonomousTestRunner(gateway)
    
    try:
        detector = TestFrameworkDetector()
        detection = detector.detect(repo_root)
        req = TestExecutionRequest(
            request_id="tool_invoke",
            repository_root=str(repo_root),
            working_directory=str(repo_root),
            framework=detection.framework,
            selected_command=detection.command
        )
        res = runner.execute(req)
        return ToolExecutionResult(
            success=res.status.value == "success", 
            data={"status": res.status.value, "passed": res.passed_count, "failed": res.failed_count}
        )
    except Exception as e:
        return ToolExecutionResult(success=False, error=str(e))

def register_core_adapters(registry: ToolRegistry):
    registry.register(ToolSpec(
        name="ast_parser",
        description="Parses Python AST to extract symbols",
        params_schema={"type": "object", "properties": {"file_path": {"type": "string"}}},
        handler=parse_ast_handler,
        permissions=["read"]
    ))
    
    registry.register(ToolSpec(
        name="dependency_analyzer",
        description="Analyzes dependencies in a repository",
        params_schema={"type": "object", "properties": {"root_dir": {"type": "string"}}},
        handler=analyze_dependencies_handler,
        permissions=["read"]
    ))
    
    registry.register(ToolSpec(
        name="test_runner",
        description="Runs autonomous tests in a repository",
        params_schema={"type": "object", "properties": {"repository_root": {"type": "string"}}},
        handler=run_tests_handler,
        permissions=["execute"]
    ))
