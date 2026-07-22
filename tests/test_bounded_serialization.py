import json
import os
import tempfile
import time
import pytest
from unittest.mock import patch, MagicMock

from shared_core.state_manager.continuity import ContinuityManager, DEFAULT_MAX_SNAPSHOT_BYTES
from shared_core.state_manager.world_state import WorldState
from shared_core.state_manager.ledger import HistoryLedger
from shared_core.state_manager.ledger_store import LedgerStore


def test_continuity_manager_default_limit():
    cm = ContinuityManager()
    assert cm.max_snapshot_bytes == DEFAULT_MAX_SNAPSHOT_BYTES

def test_continuity_manager_clamp_limits():
    cm1 = ContinuityManager(max_snapshot_bytes=100) # Below 256KiB
    assert cm1.max_snapshot_bytes == 256 * 1024

    cm2 = ContinuityManager(max_snapshot_bytes=50 * 1024 * 1024) # Above 10MiB
    assert cm2.max_snapshot_bytes == 10 * 1024 * 1024

def test_continuity_manager_oversized_save():
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "snap.json")
        cm = ContinuityManager(path, max_snapshot_bytes=256 * 1024)
        
        # Write initial valid file
        with open(path, "w") as f:
            f.write('{"valid": 1}')
            
        def huge_provider():
            return {"data": "x" * (300 * 1024)} # > 256KiB
            
        cm.register_provider("huge", huge_provider, lambda x: None)
        
        # Save should fail and NOT overwrite
        assert cm.save() is False
        
        with open(path, "r") as f:
            assert f.read() == '{"valid": 1}'

def test_continuity_manager_oversized_load():
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "snap.json")
        cm = ContinuityManager(path, max_snapshot_bytes=256 * 1024)
        
        # Create oversized file
        with open(path, "wb") as f:
            f.write(b'{"huge": "' + b'x' * (300 * 1024) + b'"}')
            
        assert cm.load() == {}

def test_world_state_capping():
    ws = WorldState()
    # Mock an OS snapshot sending a huge list
    huge_list = list(range(5000))
    ws.system.running_terminals = huge_list
    
    snap = ws.snapshot()
    # Ensure it was capped at 1000
    assert len(snap["system"]["running_terminals"]) == 1000

def test_ledger_boot_bounded():
    with tempfile.TemporaryDirectory() as td:
        db_path = os.path.join(td, "ledger.db")
        store = LedgerStore(db_path=db_path)
        
        # Insert 200 items (bypassing append memory to just show sqlite has it)
        for i in range(200):
            store.append({"ts": float(i), "change": {}, "snapshot": {}, "retention_class": "DEFAULT"})
            
        # Verify store has 200 items
        assert len(store.recent(500)) == 200
        
        # Now init Ledger, maxlen is 5000, but it should only load 100 max
        ledger = HistoryLedger(store=store, maxlen=5000)
        assert ledger.size() == 100
        
        # Confirm it's the 100 most recent (from ts=100 to 199)
        newest = ledger.recent(1)[-1]
        assert newest["ts"] == 199.0
        store.close()

def test_boot_under_two_seconds():
    # Simple test to prove the initialization of these components is fast
    start = time.time()
    with tempfile.TemporaryDirectory() as td:
        db_path = os.path.join(td, "ledger.db")
        store = LedgerStore(db_path=db_path)
        for i in range(150):
            store.append({"ts": float(i), "change": {}, "snapshot": {}, "retention_class": "DEFAULT"})
            
        ledger = HistoryLedger(store=store, maxlen=5000)
        ws = WorldState()
        snap = ws.snapshot()
        store.close()
        
    duration = time.time() - start
    assert duration < 2.0
