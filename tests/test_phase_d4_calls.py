import pytest
from pathlib import Path
from shared_core.dev_tools import CallAnalyzer, CallNode, CodeRelationPredicate
from shared_core.memory_engine.manager import MemoryManager

def test_python_call_resolution(tmp_path):
    d = tmp_path / "repo"
    d.mkdir()
    (d / "math_utils.py").write_text("""
def add(a, b):
    return a + b
""")
    (d / "main.py").write_text("""
from math_utils import add

def calculate():
    return add(1, 2)
""")

    analyzer = CallAnalyzer(d)
    calls = analyzer.analyze()
    
    assert len(calls) == 1
    assert calls[0].caller == "calculate"
    assert calls[0].callee == "add"
    assert calls[0].resolved is True
    assert calls[0].language == "python"

def test_ambiguous_call_resolution(tmp_path):
    d = tmp_path / "repo"
    d.mkdir()
    (d / "file1.py").write_text("""
def process():
    pass
""")
    (d / "file2.py").write_text("""
def process():
    pass
""")
    (d / "main.py").write_text("""
def start():
    process()
""")

    analyzer = CallAnalyzer(d)
    calls = analyzer.analyze()
    
    assert len(calls) == 1
    assert calls[0].caller == "start"
    assert calls[0].callee == "process"
    assert calls[0].resolved is False
    assert len(calls[0].candidates) == 2

def test_ts_call_resolution(tmp_path):
    d = tmp_path / "repo"
    d.mkdir()
    (d / "api.ts").write_text("""
export function fetchData() {}
""")
    (d / "app.ts").write_text("""
import { fetchData } from './api';
function run() {
    fetchData();
}
""")

    analyzer = CallAnalyzer(d)
    calls = analyzer.analyze()
    
    assert len(calls) == 1
    assert calls[0].caller == "run"
    assert calls[0].callee == "fetchData"
    assert calls[0].resolved is True
    assert calls[0].language == "typescript"

def test_store_in_kg(tmp_path, monkeypatch):
    d = tmp_path / "repo"
    d.mkdir()
    (d / "main.py").write_text("""
def target():
    pass

def source():
    target()
""")
    
    analyzer = CallAnalyzer(d)
    calls = analyzer.analyze()
    
    import shared_core.memory_engine.manager
    monkeypatch.setattr(shared_core.memory_engine.manager, 'DB_PATH', tmp_path / "jarvis.db")
    monkeypatch.setattr(shared_core.memory_engine.manager, 'FALLBACK_DB_PATH', tmp_path / "fallback.db")
    
    mm = MemoryManager()
    analyzer.store_in_kg(mm, calls)
    
    res = mm.conn.execute("SELECT * FROM kg_triples WHERE predicate = ?", ("calls",)).fetchall()
    assert len(res) >= 1
    
    found = False
    for row in res:
        if row[1] == "source" and row[3] == "target":
            found = True
            break
    assert found
