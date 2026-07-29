from pathlib import Path
from .test_execution_model import TestDetectionResult, TestFramework

class TestFrameworkDetector:
    def detect(self, repository_root: Path) -> TestDetectionResult:
        root = repository_root.resolve()
        
        has_pytest = (root / "pytest.ini").exists() or (root / "tox.ini").exists()
        has_pyproject = (root / "pyproject.toml").exists()
        
        if has_pyproject and not has_pytest:
            # Check pyproject.toml contents for pytest
            try:
                content = (root / "pyproject.toml").read_text(encoding="utf-8")
                if "[tool.pytest" in content:
                    has_pytest = True
            except:
                pass

        # If we have pytest, it takes precedence
        if has_pytest:
            return TestDetectionResult(
                framework=TestFramework.PYTEST.value,
                command=["python", "-m", "pytest"],
                working_directory=str(root),
                is_ambiguous=False,
                reason=None
            )
            
        # Check for unittest
        tests_dir = root / "tests"
        has_tests_dir = tests_dir.exists() and tests_dir.is_dir()
        if has_tests_dir:
            test_files = list(tests_dir.glob("test_*.py"))
            if test_files:
                return TestDetectionResult(
                    framework=TestFramework.UNITTEST.value,
                    command=["python", "-m", "unittest", "discover", "-s", "tests"],
                    working_directory=str(root),
                    is_ambiguous=False,
                    reason=None
                )
                
        # Ambiguous or unknown
        return TestDetectionResult(
            framework=TestFramework.UNKNOWN.value,
            command=[],
            working_directory=str(root),
            is_ambiguous=True,
            reason="No known test framework configurations (pytest.ini, tox.ini, pyproject.toml [tool.pytest], or tests/test_*.py) were found."
        )
