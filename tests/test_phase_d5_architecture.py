import pytest
from pathlib import Path
import json

from shared_core.dev_tools import (
    ArchitectureAnalyzer, ArchitectureConfig, ArchitectureQuery, LayerAssignmentSource
)

def test_architecture_layers_and_modules(tmp_path):
    d = tmp_path / "repo"
    d.mkdir()
    
    # root module
    (d / "main.py").write_text("import sys")
    # subfolder
    shared = d / "shared_core"
    shared.mkdir()
    (shared / "utils.py").write_text("def x(): pass")
    
    analyzer = ArchitectureAnalyzer(d)
    
    # 1. Inferred Mode
    snapshot = analyzer.analyze()
    assert "main.py" in snapshot.modules
    assert snapshot.modules["main.py"].layer == "root"
    assert snapshot.modules["main.py"].assignment_source == LayerAssignmentSource.INFERRED
    
    assert "shared_core/utils.py" in snapshot.modules
    assert snapshot.modules["shared_core/utils.py"].layer == "shared_core"
    
    # 2. Explicit Mode
    config = ArchitectureConfig(explicit_layers={"shared_core": "core_layer"})
    snapshot2 = analyzer.analyze(config)
    assert snapshot2.modules["shared_core/utils.py"].layer == "core_layer"
    assert snapshot2.modules["shared_core/utils.py"].assignment_source == LayerAssignmentSource.EXPLICIT

def test_architecture_cycles(tmp_path):
    d = tmp_path / "repo"
    d.mkdir()
    
    a_dir = d / "pkg"
    a_dir.mkdir()
    
    (a_dir / "a.py").write_text("from pkg.b import b_func")
    (a_dir / "b.py").write_text("from pkg.c import c_func")
    (a_dir / "c.py").write_text("from pkg.a import a_func")
    
    analyzer = ArchitectureAnalyzer(d)
    snapshot = analyzer.analyze()
    
    assert len(snapshot.cycles) == 1
    cycle = snapshot.cycles[0]
    assert "pkg/a.py" in cycle
    assert "pkg/b.py" in cycle
    assert "pkg/c.py" in cycle

def test_architecture_drift(tmp_path):
    d = tmp_path / "repo"
    d.mkdir()
    
    (d / "a.py").write_text("import sys")
    analyzer = ArchitectureAnalyzer(d)
    old_snap = analyzer.analyze()
    
    # Drift
    (d / "b.py").write_text("import os")
    new_snap = analyzer.analyze()
    
    drift = ArchitectureQuery.compare(old_snap, new_snap)
    assert "b.py" in drift.added_modules
    assert "os" in drift.added_modules
    assert len(drift.removed_modules) == 0
    
    narration = ArchitectureQuery.narrate_drift(drift)
    assert "2 modules were added since the previous snapshot" in narration

def test_architecture_narrate(tmp_path):
    d = tmp_path / "repo"
    d.mkdir()
    
    (d / "a.py").write_text("import sys")
    analyzer = ArchitectureAnalyzer(d)
    snap = analyzer.analyze()
    
    narration = ArchitectureQuery.narrate_snapshot(snap)
    assert "Layer root contains 2 modules." in narration
    assert "Total external dependencies" in narration
