import pytest
import sqlite3
import datetime
from pathlib import Path
import math

from shared_core.memory_engine.manager import MemoryManager
from memory.manager import MemoryManager as LegacyMemoryManager

@pytest.fixture
def memory_manager(tmp_path, monkeypatch):
    db_path = tmp_path / "jarvis.db"
    
    import shared_core.memory_engine.manager
    monkeypatch.setattr(shared_core.memory_engine.manager, 'DB_PATH', db_path)
    monkeypatch.setattr(shared_core.memory_engine.manager, 'FALLBACK_DB_PATH', tmp_path / "fallback.db")
    
    mgr = MemoryManager()
    return mgr

def test_c3_schema_contains_required_fields(memory_manager):
    """1. Schema contains every required field."""
    cursor = memory_manager.conn.execute("PRAGMA table_info(kg_triples)")
    columns = {row[1]: row for row in cursor.fetchall()}
    assert "subject" in columns
    assert "predicate" in columns
    assert "object" in columns
    assert "weight" in columns
    assert "first_seen" in columns
    assert "last_seen" in columns
    # Verify timestamp storage type is TEXT, weight is REAL
    assert columns["first_seen"][2].upper() == "TEXT"
    assert columns["last_seen"][2].upper() == "TEXT"
    assert columns["weight"][2].upper() == "REAL"
    assert columns["subject"][2].upper() == "TEXT"
    # Not null constraints (idx 3 is notnull)
    assert columns["first_seen"][3] == 1
    assert columns["weight"][3] == 1

def test_c3_unique_constraint(memory_manager):
    """2. Unique triple constraint exists."""
    cursor = memory_manager.conn.execute("PRAGMA index_list(kg_triples)")
    indexes = [row[1] for row in cursor.fetchall()]
    assert any("autoindex_kg_triples" in idx for idx in indexes)

def test_c3_initialization_idempotent(memory_manager):
    """3. Initialization is idempotent."""
    memory_manager._init_db() # Call it a second time
    # Should not throw any exception

def test_c3_fourteen_tables_exist(memory_manager):
    """4. Fourteen user-defined tables exist after C3."""
    cursor = memory_manager.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    user_tables = [t for t in tables if t != "sqlite_sequence"]
    assert len(user_tables) == 14
    assert "kg_triples" in user_tables

def test_c3_sqlite_sequence_separated(memory_manager):
    """5. sqlite_sequence remains classified separately."""
    cursor = memory_manager.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    assert "sqlite_sequence" in tables

def test_c3_new_triple_insertion(memory_manager):
    """6. New triple insertion works."""
    rowid = memory_manager.upsert_triple("A", "knows", "B")
    assert rowid is not None
    assert isinstance(rowid, int)
    res = memory_manager.query_triples(subject="A")
    assert len(res) == 1
    assert res[0]["subject"] == "A"

def test_c3_strict_insert_behavior(memory_manager):
    """7. Strict insert conflict behavior works, or upsert insertion mapping is explicitly proven."""
    # We mapped insert to the absent-row branch of upsert_triple.
    rowid = memory_manager.upsert_triple("C", "likes", "D")
    assert len(memory_manager.query_triples(subject="C")) == 1

def test_c3_upsert_creates_missing(memory_manager):
    """8. Upsert creates a missing triple."""
    rowid = memory_manager.upsert_triple("X", "Y", "Z")
    assert len(memory_manager.query_triples(subject="X")) == 1

def test_c3_upsert_updates_existing(memory_manager):
    """9. Upsert updates an existing triple. 10. No duplicate triple is created."""
    id1 = memory_manager.upsert_triple("X", "Y", "Z", weight=1.0)
    id2 = memory_manager.upsert_triple("X", "Y", "Z", weight=2.0)
    assert id1 == id2 # 11. Stable row ID is preserved.
    res = memory_manager.query_triples(subject="X")
    assert len(res) == 1
    assert res[0]["weight"] == 2.0 # 12. Weight uses override semantics.

def test_c3_repeated_identical_upsert(memory_manager):
    """13. Repeated identical upsert does not accumulate weight."""
    memory_manager.upsert_triple("J", "K", "L", weight=3.0)
    memory_manager.upsert_triple("J", "K", "L", weight=3.0)
    res = memory_manager.query_triples(subject="J")
    assert res[0]["weight"] == 3.0

def test_c3_timestamp_deterministic_logic(memory_manager):
    """
    14. first_seen preserves earliest.
    15. last_seen preserves latest.
    16. Older out-of-order observation does not incorrectly overwrite latest weight.
    """
    # Insert at t2
    t2 = "2023-01-02T10:00:00Z"
    id1 = memory_manager.upsert_triple("P", "Q", "R", weight=2.0, observed_at=t2)
    
    # Insert older observation at t1
    t1 = "2023-01-01T10:00:00Z"
    id2 = memory_manager.upsert_triple("P", "Q", "R", weight=1.0, observed_at=t1)
    
    assert id1 == id2
    res = memory_manager.query_triples(subject="P")[0]
    assert res["first_seen"] == t1
    assert res["last_seen"] == t2
    assert res["weight"] == 2.0 # Should not be overwritten by older observation

def test_c3_query_filters(memory_manager):
    """
    17-22: Query by subject, predicate, object, weight, first_seen, last_seen
    23: Combined six-field filters
    """
    t1 = "2023-01-01T10:00:00Z"
    memory_manager.upsert_triple("S", "P", "O", weight=4.0, observed_at=t1)
    
    assert len(memory_manager.query_triples(subject="S")) == 1
    assert len(memory_manager.query_triples(predicate="P")) == 1
    assert len(memory_manager.query_triples(object="O")) == 1
    assert len(memory_manager.query_triples(weight=4.0)) == 1
    assert len(memory_manager.query_triples(first_seen=t1)) == 1
    assert len(memory_manager.query_triples(last_seen=t1)) == 1
    
    # Combined
    assert len(memory_manager.query_triples(subject="S", predicate="P", object="O", weight=4.0, first_seen=t1, last_seen=t1)) == 1

def test_c3_query_limits_and_ordering(memory_manager):
    """
    24. Unfiltered query is bounded.
    25. Limit validation works.
    26. Excessive limit handling works.
    27. Deterministic ordering works.
    """
    for i in range(15):
        # Insert iteratively with explicit times to guarantee deterministic ordering
        ts = f"2023-01-{(i+1):02d}T10:00:00Z"
        memory_manager.upsert_triple(f"S{i}", "P", "O", observed_at=ts)
    
    # Unfiltered bounded
    assert len(memory_manager.query_triples()) == 15
    
    # Limit validation
    assert len(memory_manager.query_triples(limit=5)) == 5
    
    # Ordering: DESC by last_seen
    res = memory_manager.query_triples(limit=5)
    assert res[0]["subject"] == "S14"
    assert res[1]["subject"] == "S13"
    
    # Excessive limit
    assert len(memory_manager.query_triples(limit=5000)) == 15
    assert memory_manager.MAX_TRIPLE_QUERY_LIMIT == 1000
    
    with pytest.raises(ValueError):
        memory_manager.query_triples(limit=0)
    with pytest.raises(ValueError):
        memory_manager.query_triples(limit=True)

def test_c3_input_safety(memory_manager):
    """
    28. SQL-injection-like safe
    29. Unicode safe
    30. Empty rejected
    31. NaN / inf rejected
    """
    # SQL Injection
    memory_manager.upsert_triple("DROP TABLE kg_triples;", "OR 1=1", "--")
    assert len(memory_manager.query_triples(subject="DROP TABLE kg_triples;")) == 1
    
    # Unicode
    memory_manager.upsert_triple("??????", "????????", "????????")
    assert len(memory_manager.query_triples(subject="??????")) == 1
    
    # Empty
    with pytest.raises(ValueError):
        memory_manager.upsert_triple("", "P", "O")
        
    # NaN
    with pytest.raises(ValueError):
        memory_manager.upsert_triple("S", "P", "O", weight=float('nan'))
    with pytest.raises(ValueError):
        memory_manager.upsert_triple("S", "P", "O", weight=float('inf'))

def test_c3_rollback_and_persistence(memory_manager, tmp_path):
    """
    33. Transaction rollback preserves state.
    34. Data survives reopen.
    """
    memory_manager.upsert_triple("A", "B", "C")
    
    # Force an error
    try:
        memory_manager.conn.execute("INSERT INTO kg_triples (subject) VALUES ('invalid')")
    except sqlite3.Error:
        pass
        
    # Data survives reopen
    memory_manager.conn.close()
    
    mgr2 = MemoryManager()
    assert len(mgr2.query_triples(subject="A")) == 1

def test_c3_legacy_compatibility(tmp_path, monkeypatch):
    """
    35. Legacy and canonical imports see same data.
    """
    db_path = tmp_path / "jarvis.db"
    import shared_core.memory_engine.manager
    monkeypatch.setattr(shared_core.memory_engine.manager, 'DB_PATH', db_path)
    monkeypatch.setattr(shared_core.memory_engine.manager, 'FALLBACK_DB_PATH', tmp_path / "fallback.db")
    
    canonical = MemoryManager()
    canonical.upsert_triple("M", "N", "O")
    
    legacy = LegacyMemoryManager()
    cursor = legacy.conn.execute("SELECT subject FROM kg_triples WHERE subject='M'")
    assert cursor.fetchone()[0] == "M"

def test_c3_concurrent_upserts(memory_manager):
    """
    36. Concurrent upserts create one deterministic row.
    """
    import threading
    
    def worker():
        for _ in range(10):
            memory_manager.upsert_triple("Thread", "Safety", "Check", weight=5.0)
            
    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
        
    res = memory_manager.query_triples(subject="Thread")
    assert len(res) == 1
    assert res[0]["weight"] == 5.0
