import pytest
from pathlib import Path
from shared_core.dev_tools.tree_sitter_parser import TreeSitterParser
from shared_core.dev_tools.symbol_model import SymbolType

@pytest.fixture
def parser():
    return TreeSitterParser()

def test_parse_typescript(tmp_path, parser):
    source = """
    const GLOBAL_VAR = 42;
    
    class MyClass {
        class_var: number = 1;
        
        my_method(local_var: number) {
            let inner_var = 2;
        }
        
        async my_async_method() {
            return;
        }
    }
    
    function standalone_function(param: string) {
    }
    """
    test_file = tmp_path / "test_source.ts"
    test_file.write_text(source, encoding="utf-8")
    
    symbols = parser.parse_file(test_file)
    names = {s.name: s for s in symbols}
    
    assert "GLOBAL_VAR" in names
    assert names["GLOBAL_VAR"].symbol_type == SymbolType.VARIABLE
    assert names["GLOBAL_VAR"].parent_scope is None
    
    assert "MyClass" in names
    assert names["MyClass"].symbol_type == SymbolType.CLASS
    
    assert "my_method" in names
    assert names["my_method"].symbol_type == SymbolType.FUNCTION
    assert names["my_method"].parent_scope == "MyClass"
    assert names["my_method"].is_async is False
    
    assert "my_async_method" in names
    assert names["my_async_method"].symbol_type == SymbolType.FUNCTION
    assert names["my_async_method"].is_async is True
    
    assert "local_var" in names
    assert names["local_var"].symbol_type == SymbolType.VARIABLE
    assert names["local_var"].parent_scope == "my_method"
    
    assert "inner_var" in names
    assert names["inner_var"].symbol_type == SymbolType.VARIABLE
    
    assert "standalone_function" in names
    assert names["standalone_function"].symbol_type == SymbolType.FUNCTION

def test_parse_java(tmp_path, parser):
    source = """
    package com.example;
    
    public class MyJavaClass {
        private int classField = 1;
        
        public MyJavaClass() {
            int constructorVar = 2;
        }
        
        public void myMethod(String param) {
            int local_var = 2;
        }
    }
    """
    test_file = tmp_path / "TestSource.java"
    test_file.write_text(source, encoding="utf-8")
    
    symbols = parser.parse_file(test_file)
    qnames = {s.qualified_name: s for s in symbols}
    
    assert "MyJavaClass" in qnames
    assert qnames["MyJavaClass"].symbol_type == SymbolType.CLASS
    
    assert "MyJavaClass.classField" in qnames
    assert qnames["MyJavaClass.classField"].symbol_type == SymbolType.VARIABLE
    assert qnames["MyJavaClass.classField"].parent_scope == "MyJavaClass"
    
    assert "MyJavaClass.MyJavaClass" in qnames
    assert qnames["MyJavaClass.MyJavaClass"].symbol_type == SymbolType.FUNCTION
    
    assert "MyJavaClass.myMethod" in qnames
    assert qnames["MyJavaClass.myMethod"].symbol_type == SymbolType.FUNCTION
    assert qnames["MyJavaClass.myMethod"].parent_scope == "MyJavaClass"
    
    assert "MyJavaClass.myMethod.param" in qnames
    assert qnames["MyJavaClass.myMethod.param"].symbol_type == SymbolType.VARIABLE
    
    assert "MyJavaClass.myMethod.local_var" in qnames
    assert qnames["MyJavaClass.myMethod.local_var"].symbol_type == SymbolType.VARIABLE
