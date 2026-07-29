import json
from pathlib import Path
from shared_core.dev_tools import DependencyAnalyzer, DependencyType
from shared_core.memory_engine.manager import MemoryManager

def test_python_internal_deps(tmp_path):
    d = tmp_path / "repo"
    d.mkdir()
    (d / "main.py").write_text("import sys\nfrom os import path\n")
    
    analyzer = DependencyAnalyzer(d)
    deps = analyzer.analyze()
    
    assert len(deps) == 2
    assert deps[0].target == "sys"
    assert deps[0].dependency_type == DependencyType.INTERNAL
    assert deps[1].target == "os"
    
def test_python_external_deps(tmp_path):
    d = tmp_path / "repo"
    d.mkdir()
    (d / "requirements.txt").write_text("requests>=2.0\npytest==7.0.0\n")
    
    analyzer = DependencyAnalyzer(d)
    deps = analyzer.analyze()
    
    assert len(deps) == 2
    assert deps[0].target == "requests"
    assert deps[0].dependency_type == DependencyType.EXTERNAL
    assert deps[1].target == "pytest"

def test_ts_external_deps(tmp_path):
    d = tmp_path / "repo"
    d.mkdir()
    (d / "package.json").write_text(json.dumps({
        "dependencies": {"react": "^18.0.0"},
        "devDependencies": {"typescript": "4.5"}
    }))
    
    analyzer = DependencyAnalyzer(d)
    deps = analyzer.analyze()
    
    assert len(deps) == 2
    assert deps[0].target == "react"
    assert deps[1].target == "typescript"

def test_ts_internal_deps(tmp_path):
    d = tmp_path / "repo"
    d.mkdir()
    (d / "app.ts").write_text("import { foo } from './utils';\nimport 'react';\n")
    
    analyzer = DependencyAnalyzer(d)
    deps = analyzer.analyze()
    
    assert len(deps) == 2
    # ./utils is internal
    assert deps[0].target == "./utils"
    assert deps[0].dependency_type == DependencyType.INTERNAL
    # react is external
    assert deps[1].target == "react"
    assert deps[1].dependency_type == DependencyType.EXTERNAL

def test_store_in_kg(tmp_path, monkeypatch):
    d = tmp_path / "repo"
    d.mkdir()
    (d / "main.py").write_text("import os\n")
    
    analyzer = DependencyAnalyzer(d)
    deps = analyzer.analyze()
    
    import shared_core.memory_engine.manager
    monkeypatch.setattr(shared_core.memory_engine.manager, 'DB_PATH', tmp_path / "jarvis.db")
    monkeypatch.setattr(shared_core.memory_engine.manager, 'FALLBACK_DB_PATH', tmp_path / "fallback.db")
    
    mm = MemoryManager()
    analyzer.store_in_kg(mm, deps)
    
    res = mm.conn.execute("SELECT * FROM kg_triples WHERE predicate = ?", ("depends_on",)).fetchall()
    assert len(res) >= 1
    # Find our specific triple
    found = False
    for row in res:
        # row: (id, subject, predicate, object, weight, observed_at, created)
        if row[1] == "main.py" and row[3] == "os":
            found = True
            break
    assert found
