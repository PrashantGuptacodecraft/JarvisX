import time
import pytest
import os
import tempfile
from unittest.mock import MagicMock

from shared_core.event_bus import EventBus
from shared_core.scheduler import Scheduler
from shared_core.state_manager.continuity import ContinuityManager
from shared_core.state_manager.ledger import HistoryLedger
from shared_core.state_manager.ledger_store import LedgerStore
from shared_core.state_manager.manager import StateManager
from shared_core.state_manager.history_models import StateDiagnostics
from shared_core.event_bus.topics import (
    PERCEPTION_DEV_DIAGNOSTICS,
    MAINTENANCE_COMPACTION_COMPLETED,
    MAINTENANCE_COMPACTION_FAILED,
    MAINTENANCE_COMPACTION_SKIPPED
)

def test_diagnostics_structure_and_types():
    bus = EventBus()
    
    with tempfile.TemporaryDirectory() as td:
        db_path = os.path.join(td, "diag.db")
        store = LedgerStore(db_path=db_path)
        ledger = HistoryLedger(store=store)
        
        store.append({"ts": 1.0, "change": {}, "snapshot": {}, "retention_class": "DEFAULT"})
        store.append({"ts": 2.0, "change": {}, "snapshot": {}, "retention_class": "SIGNIFICANT"})
        
        sm = StateManager(bus, ledger=ledger)
        scheduler = Scheduler()
        cont = ContinuityManager()
        
        sm.set_scheduler(scheduler)
        sm.set_continuity(cont)
        
        diag = sm.diagnostics()
        
        assert isinstance(diag, StateDiagnostics)
        assert diag.schema_version == 1
        
        # Verify ledger estimated counts and exact counts unavailable
        assert diag.ledger["store"]["transition_high_water_id"] == 2
        assert diag.ledger["store"]["approximate_tier0_id_span"] == 2
        assert diag.ledger["store"]["exact_row_counts"] == "unavailable_without_full_scan"
        assert diag.ledger["store"]["compression_ratio"] == "unavailable_without_full_scan"
        
        sm.stop()
        scheduler.stop()
        cont.stop()
        ledger.close()
        store.close()

def test_publish_diagnostics():
    bus = EventBus()
    sm = StateManager(bus)
    
    published_events = []
    
    def on_diag(evt):
        published_events.append(evt)
        
    bus.subscribe(PERCEPTION_DEV_DIAGNOSTICS, on_diag, mode="sync")
    
    diag = sm.publish_diagnostics()
    assert len(published_events) == 1
    
    evt = published_events[0]
    assert evt.topic == PERCEPTION_DEV_DIAGNOSTICS
    assert evt.payload["schema_version"] == 1
    assert evt.payload["captured_at"] == diag.captured_at
    
    sm.stop()

def test_compaction_result_caching():
    bus = EventBus()
    sm = StateManager(bus)
    sm.start()
    
    # Simulate various terminal outcomes
    for outcome, payload, topic in [
        ("completed", {"cycle_id": "test-1", "success": True}, MAINTENANCE_COMPACTION_COMPLETED),
        ("failed", {"cycle_id": "test-2", "success": False, "error": "db locked"}, MAINTENANCE_COMPACTION_FAILED),
        ("skipped_overlap", {"cycle_id": "test-3", "success": False, "reason": "overlap"}, MAINTENANCE_COMPACTION_SKIPPED),
        ("skipped_overload", {"cycle_id": "test-4", "success": False, "reason": "overload"}, MAINTENANCE_COMPACTION_SKIPPED),
        ("partial", {"cycle_id": "test-5", "success": False, "expiry_success": True}, MAINTENANCE_COMPACTION_FAILED)
    ]:
        bus.publish(topic, payload)
        import time
        time.sleep(0.05)
        diag = sm.diagnostics()
        assert diag.compaction["cycle_id"] == payload["cycle_id"]
        assert diag.compaction["success"] == payload["success"]
    
    sm.stop()

def test_diagnostics_deleted_rows_approximate():
    """Verify that deleting rows does not trick the diagnostics into reporting a false exact row count."""
    with tempfile.TemporaryDirectory() as td:
        db_path = os.path.join(td, "approx.db")
        store = LedgerStore(db_path=db_path)
        
        # Insert 100 rows
        for i in range(100):
            store._conn.execute("INSERT INTO transitions (id, ts, data, retention_class) VALUES (?, 1.0, '{}', 'DEFAULT')", (i+1,))
            store._conn.execute("INSERT INTO ledger_summaries (id, tier, bucket_start, bucket_end, topic, retention_class, first_payload_json, first_ts, last_payload_json, last_ts, aggregate_json, event_count, source_min_id, source_max_id, source_count, created_at) VALUES (?, 1, ?, ?, 'sys', 'DEFAULT', '{}', 1.0, '{}', 1.0, '{}', 10, 1, 10, 10, 1.0)", (i+1, float(i), float(i+1)))

        # Delete most rows, leaving only ID 1 and ID 100
        store._conn.execute("DELETE FROM transitions WHERE id > 1 AND id < 100")
        store._conn.execute("DELETE FROM ledger_summaries WHERE id > 1 AND id < 100")
        store._conn.commit()
        
        diag = store.diagnostics()
        # The true row count is 2, but the span is 100
        assert diag["transition_high_water_id"] == 100
        assert diag["approximate_tier0_id_span"] == 100
        assert diag["summary_high_water_id"] == 100
        assert diag["approximate_tier1_id_span"] == 100
        assert diag["exact_row_counts"] == "unavailable_without_full_scan"
        assert diag["compression_ratio"] == "unavailable_without_full_scan"
        
        # Test serializability
        import json
        json.dumps(diag)
        
        store.close()
