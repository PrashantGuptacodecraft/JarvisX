import pytest
import sqlite3
import os
from pathlib import Path

from memory.manager import MemoryManager as LegacyMemoryManager
from shared_core.memory_engine.manager import MemoryManager as CanonicalMemoryManager

from memory.rag_manager import RAGManager as LegacyRAGManager
from shared_core.memory_engine.rag_manager import RAGManager as CanonicalRAGManager

def test_data_retention_and_legacy_compatibility(tmp_path, monkeypatch):
    """
    Tests that a database created and populated by the LegacyMemoryManager
    is perfectly readable and mutable by the CanonicalMemoryManager without data loss.
    """
    db_path = tmp_path / "jarvis.db"
    
    import shared_core.memory_engine.manager
    monkeypatch.setattr(shared_core.memory_engine.manager, 'DB_PATH', db_path)
    monkeypatch.setattr(shared_core.memory_engine.manager, 'FALLBACK_DB_PATH', tmp_path / "fallback.db")
    
    # 1. Populate using Legacy
    legacy_mgr = LegacyMemoryManager()
    legacy_mgr.store_fact("Legacy fact")
    legacy_mgr.add_episode("Legacy episode")
    legacy_mgr.save_project(name="LegacyProject", details="B")
    
    # Verify legacy populated
    assert len(legacy_mgr.get_all_facts()) == 1
    legacy_mgr.conn.close()
    
    # 2. Re-open using Canonical
    canonical_mgr = CanonicalMemoryManager()
    
    # Verify data intact
    facts = canonical_mgr.get_all_facts()
    assert len(facts) == 1
    assert "Legacy fact" in facts[0]["value"]
    
    eps = canonical_mgr.get_recent_episodes()
    assert len(eps) == 1
    assert "Legacy episode" in eps[0]["description"]
    
    projs = canonical_mgr.list_projects()
    assert len(projs) == 1
    assert projs[0]["name"] == "LegacyProject"
    
    # 3. Mutate using Canonical
    canonical_mgr.store_fact("Canonical fact")
    assert len(canonical_mgr.get_all_facts()) == 2

def test_rag_manager_retention_and_compatibility(tmp_path, monkeypatch):
    """
    Tests that Chroma collection created by Legacy is fully readable by Canonical.
    """
    monkeypatch.setattr(os, 'getcwd', lambda: str(tmp_path))
    
    legacy_rag = LegacyRAGManager()
    if not legacy_rag.collection:
        pytest.skip("ChromaDB not available")
        
    legacy_rag.ingest_text("Legacy RAG data", source="legacy_source")
    
    # recreate as canonical
    canonical_rag = CanonicalRAGManager()
    res = canonical_rag.search("RAG data")
    
    assert "legacy_source" in res
    assert "Legacy RAG data" in res
