import pytest
import textwrap
from pathlib import Path
from shared_core.dev_tools.ast_parser import PythonASTParser, SymbolType

@pytest.fixture
def parser():
    return PythonASTParser()

def test_parse_single_file_functions_classes_vars(tmp_path, parser):
    source = textwrap.dedent("""
        GLOBAL_VAR = 42
        
        class MyClass:
            class_var: int = 1
            
            def my_method(self):
                local_var = 2
                pass
                
        def standalone_function():
            pass
    """)
    test_file = tmp_path / "test_source.py"
    test_file.write_text(source, encoding="utf-8")
    
    symbols = parser.parse_file(test_file)
    names = {s.name: s for s in symbols}
    
    assert "GLOBAL_VAR" in names
    assert names["GLOBAL_VAR"].symbol_type == SymbolType.VARIABLE
    assert names["GLOBAL_VAR"].parent_scope is None
    assert names["GLOBAL_VAR"].qualified_name == "GLOBAL_VAR"
    
    assert "MyClass" in names
    assert names["MyClass"].symbol_type == SymbolType.CLASS
    assert names["MyClass"].qualified_name == "MyClass"
    
    assert "class_var" in names
    assert names["class_var"].symbol_type == SymbolType.VARIABLE
    assert names["class_var"].parent_scope == "MyClass"
    assert names["class_var"].qualified_name == "MyClass.class_var"
    
    assert "my_method" in names
    assert names["my_method"].symbol_type == SymbolType.FUNCTION
    assert names["my_method"].parent_scope == "MyClass"
    assert names["my_method"].qualified_name == "MyClass.my_method"
    
    assert "local_var" in names
    assert names["local_var"].symbol_type == SymbolType.VARIABLE
    assert names["local_var"].parent_scope == "my_method"
    assert names["local_var"].qualified_name == "MyClass.my_method.local_var"

    assert "standalone_function" in names
    assert names["standalone_function"].symbol_type == SymbolType.FUNCTION
    assert names["standalone_function"].parent_scope is None
    
    assert names["GLOBAL_VAR"].location.line == 2
    assert names["MyClass"].location.line == 4
    assert names["my_method"].location.line == 7

def test_parse_directory_recursive(tmp_path, parser):
    dir1 = tmp_path / "pkg1"
    dir1.mkdir()
    (dir1 / "file1.py").write_text("def func1(): pass", encoding="utf-8")
    
    dir2 = dir1 / "pkg2"
    dir2.mkdir()
    (dir2 / "file2.py").write_text("class Class2: pass", encoding="utf-8")
    
    (dir1 / "file3.txt").write_text("def func3(): pass", encoding="utf-8")
    
    symbols = parser.parse_directory(tmp_path)
    assert len(symbols) == 2
    names = {s.name for s in symbols}
    assert "func1" in names
    assert "Class2" in names

def test_handles_syntax_errors_gracefully(tmp_path, parser):
    test_file = tmp_path / "bad_syntax.py"
    test_file.write_text("def bad_syntax(:::)", encoding="utf-8")
    
    symbols = parser.parse_file(test_file)
    assert symbols == []

def test_parse_real_repo(parser):
    """Test AST parser against a real repository directory to fulfill D1 acceptance criteria."""
    core_dir = Path(__file__).parent.parent / "shared_core"
    symbols = parser.parse_directory(core_dir)
    
    assert len(symbols) > 50, "Should extract a substantial number of symbols from shared_core"
    
    names = {s.name for s in symbols}
    assert "MemoryManager" in names
    assert "EventBus" in names
    assert "WorldState" in names

def test_variable_extraction(tmp_path, parser):
    source = textwrap.dedent("""
        a = 1
        b: int = 2
        c += 1
        (d := 4)
        e, f = (5, 6)
        
        for g in []: pass
        with open() as h: pass
        
        def func(i, j=1, *args, **kwargs):
            self.value = 10
            x = 1
            pass
    """)
    test_file = tmp_path / "test_vars.py"
    test_file.write_text(source, encoding="utf-8")
    
    symbols = parser.parse_file(test_file)
    var_names = {s.name for s in symbols if s.symbol_type == SymbolType.VARIABLE}
    
    expected = {"a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "args", "kwargs", "x"}
    assert expected.issubset(var_names)
    assert "value" not in var_names
    assert "self" not in var_names # Wait, self is a parameter!
