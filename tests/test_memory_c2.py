import pytest
import sqlite3
import os
from pathlib import Path

from memory.manager import MemoryManager as LegacyMemoryManager
from shared_core.memory_engine.manager import MemoryManager as CanonicalMemoryManager

from memory.rag_manager import RAGManager as LegacyRAGManager
from shared_core.memory_engine.rag_manager import RAGManager as CanonicalRAGManager

@pytest.fixture(params=[LegacyMemoryManager, CanonicalMemoryManager])
def memory_manager(request, tmp_path, monkeypatch):
    """Provides a MemoryManager initialized to a temporary database, testing both Legacy and Canonical paths."""
    db_path = tmp_path / "jarvis.db"
    
    # We must mock DB_PATH in config.settings because MemoryManager imports it directly in its module.
    # To properly mock it, we mock it where it's used inside the module.
    import shared_core.memory_engine.manager
    monkeypatch.setattr(shared_core.memory_engine.manager, 'DB_PATH', db_path)
    monkeypatch.setattr(shared_core.memory_engine.manager, 'FALLBACK_DB_PATH', tmp_path / "fallback.db")
    
    mgr = request.param()
    return mgr

@pytest.fixture(params=[LegacyRAGManager, CanonicalRAGManager])
def rag_manager(request, tmp_path, monkeypatch):
    """Provides a RAGManager initialized to a temporary database, testing both Legacy and Canonical paths."""
    import shared_core.memory_engine.rag_manager
    monkeypatch.setattr(os, 'getcwd', lambda: str(tmp_path))
    mgr = request.param()
    return mgr


def test_episodes_api(memory_manager):
    memory_manager.add_episode("test episode 1", source="user", tags="#test")
    memory_manager.add_episode("test episode 2", source="system", tags="#sys")
    
    eps = memory_manager.get_recent_episodes(limit=10)
    assert len(eps) == 2
    assert eps[0]["description"] == "test episode 2"
    assert eps[1]["description"] == "test episode 1"
    
    sys_eps = memory_manager.get_recent_episodes(source="system")
    assert len(sys_eps) == 1
    assert sys_eps[0]["description"] == "test episode 2"
    
    search_res = memory_manager.search_episodes("episode")
    assert len(search_res) == 2

def test_command_patterns_api(memory_manager):
    memory_manager.save_command_pattern("git status", "git add")
    memory_manager.save_command_pattern("git status", "git add") # test upsert
    memory_manager.save_command_pattern("git commit", "git push")
    
    pats = memory_manager.get_command_patterns()
    assert len(pats) == 2
    git_add = next(p for p in pats if p["next_cmd"] == "git add")
    assert git_add["count"] == 2

def test_facts_api(memory_manager):
    memory_manager.store_fact("sky is blue")
    memory_manager.store_fact("water is wet")
    
    res = memory_manager.recall_fact("sky")
    assert "sky is blue" in res.lower()
    
    all_facts = memory_manager.get_all_facts()
    assert len(all_facts) == 2
    
    memory_manager.forget("sky")
    res_forgot = memory_manager.recall_fact("sky")
    assert "nothing relevant" in res_forgot.lower()

def test_history_api(memory_manager):
    memory_manager.add_history("hello", "hi there")
    hist = memory_manager.get_history()
    assert len(hist) == 1
    assert hist[0]["user"] == "hello"
    assert hist[0]["jarvis"] == "hi there"

def test_reminders_and_todos_api(memory_manager):
    memory_manager.add_reminder("test task", "tomorrow")
    memory_manager.add_todo("buy milk")
    
    rems = memory_manager.get_pending_reminders()
    assert len(rems) == 1
    assert rems[0]["task"] == "test task"
    
    memory_manager.mark_reminder_done(rems[0]["id"])
    rems_after = memory_manager.get_pending_reminders()
    assert len(rems_after) == 0
    
    todos = memory_manager.get_todos()
    assert len(todos) == 1
    assert todos[0]["item"] == "buy milk"

def test_notes_api(memory_manager):
    memory_manager.add_note("this is a note")
    notes = memory_manager.get_notes()
    assert len(notes) == 1
    assert notes[0]["content"] == "this is a note"

def test_contacts_api(memory_manager):
    memory_manager.save_contact("Alice", "1234567890", "whatsapp")
    phone = memory_manager.get_contact_phone("Alice", "whatsapp")
    assert phone == "1234567890"
    
    contacts = memory_manager.list_contacts()
    assert len(contacts) == 1
    assert contacts[0]["name"] == "alice"

def test_profile_api(memory_manager):
    memory_manager.save_profile_item("I like python", category="coding")
    memory_manager.save_profile_detail("coding", "favorite_lang", "python")
    
    entries = memory_manager.get_profile_entries("coding")
    assert len(entries) > 0
    
    snap = memory_manager.get_profile_snapshot()
    assert "coding" in snap
    assert "favorite_lang" in snap["coding"]

def test_projects_api(memory_manager):
    memory_manager.save_project(name="P1", details="Det")
    
    proj = memory_manager.get_project("P1")
    assert proj["name"] == "P1"
    
    projs = memory_manager.list_projects()
    assert len(projs) == 1

def test_knowledge_docs_api(memory_manager):
    memory_manager.save_knowledge_document("Doc1", "/path/to/doc", "Content here")
    docs = memory_manager.list_knowledge_documents()
    assert len(docs) == 1
    assert docs[0]["title"] == "Doc1"
    
    res = memory_manager.search_knowledge("Content")
    assert len(res) == 1

def test_workflows_api(memory_manager):
    memory_manager.save_workflow("W1", ["step1", "step2"], "desc")
    wf = memory_manager.get_workflow("W1")
    assert wf["name"] == "W1"
    
    wfs = memory_manager.list_workflows()
    assert len(wfs) == 1

def test_missions_api(memory_manager):
    memory_manager.save_mission(name="M1", objective="Obj1")
    
    miss = memory_manager.get_mission("M1")
    assert miss["name"] == "M1"
    
    amiss = memory_manager.get_active_mission()
    assert amiss["name"] == "M1"

def test_rag_manager_api(rag_manager):
    # Depending on system, ChromaDB might fail to load. We check if collection is present.
    if not rag_manager.collection:
        pytest.skip("ChromaDB not available for RAGManager")
        
    res = rag_manager.ingest_text("This is test RAG data", source="test_source")
    assert "Successfully" in res
    
    search_res = rag_manager.search("RAG data")
    assert "test_source" in search_res
    assert "This is test RAG data" in search_res
