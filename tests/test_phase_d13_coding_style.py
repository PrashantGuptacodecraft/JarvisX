import pytest
from pathlib import Path

from shared_core.dev_tools.style_model import CodingStyleModel, StyleEvidenceSource
from shared_core.dev_tools.style_analyzer import StyleAnalyzer
from shared_core.dev_tools.style_application import StyleApplication

@pytest.fixture
def workspace(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    return repo

def test_style_analyzer_reads_editorconfig(workspace):
    editorconfig = workspace / ".editorconfig"
    editorconfig.write_text("[*]\nindent_style = space\nindent_size = 4\nmax_line_length = 100\n")
    
    analyzer = StyleAnalyzer(str(workspace))
    model = analyzer.analyze()
    
    assert model.indent_style == "space"
    assert model.indent_size == 4
    assert model.max_line_length == 100
    
    evs = [e for e in model.evidences if e.source == StyleEvidenceSource.CONFIG]
    assert len(evs) == 3

def test_style_analyzer_reads_pyproject(workspace):
    pyproject = workspace / "pyproject.toml"
    pyproject.write_text("[tool.ruff]\nline-length = 120\n")
    
    analyzer = StyleAnalyzer(str(workspace))
    model = analyzer.analyze()
    
    assert model.max_line_length == 120

def test_style_application_validates_code(workspace):
    model = CodingStyleModel(indent_style="space", indent_size=4, max_line_length=50)
    app = StyleApplication(model)
    
    # Valid code
    valid_code = "def foo():\n    return 42\n"
    assert app.validate_code(valid_code) is True
    
    # Invalid indent (using tabs)
    invalid_indent = "def foo():\n\treturn 42\n"
    assert app.validate_code(invalid_indent) is False
    
    # Invalid length
    invalid_length = "def foo():\n    return " + ("a" * 60) + "\n"
    assert app.validate_code(invalid_length) is False
