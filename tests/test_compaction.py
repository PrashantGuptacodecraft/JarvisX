"""Phase B · BC1 — Compaction class-based retention and expiry tests.

Run:  python -m pytest tests/test_compaction.py -v
"""
import os
import sqlite3
import tempfile
import time
import json

from shared_core.state_manager.compaction import RetentionClass, classify, parse_retention_class
from shared_core.state_manager.ledger import HistoryLedger
from shared_core.state_manager.ledger_store import LedgerStore


def test_classify_prefix_matching():
    # 15. Prefix-based topic classification works
    assert classify("perception.os.active_window", {}) == RetentionClass.EPHEMERAL
    assert classify("perception.system.cpu", {}) == RetentionClass.EPHEMERAL
    assert classify("perception.mouse.move", {}) == RetentionClass.EPHEMERAL
    assert classify("system.cpu.temp", {}) == RetentionClass.EPHEMERAL
    
    assert classify("action.result", {}) == RetentionClass.SIGNIFICANT
    assert classify("scheduler.fail.timeout", {}) == RetentionClass.SIGNIFICANT
    assert classify("tool.invoke", {}) == RetentionClass.SIGNIFICANT
    assert classify("system.error.panic", {}) == RetentionClass.SIGNIFICANT
    
    assert classify("some.unknown.topic", {}) == RetentionClass.DEFAULT
    assert classify("", {}) == RetentionClass.DEFAULT


def test_parse_retention_class():
    # 12. Unknown retention-class values fall back to DEFAULT
    assert parse_retention_class("EPHEMERAL") == RetentionClass.EPHEMERAL
    assert parse_retention_class("significant") == RetentionClass.SIGNIFICANT
    assert parse_retention_class("UNKNOWN") == RetentionClass.DEFAULT
    assert parse_retention_class(None) == RetentionClass.DEFAULT


def test_legacy_schema_upgrade():
    # 7. A real temporary database using the legacy schema upgrades successfully.
    # 8. Existing legacy rows resolve safely to DEFAULT.
    # 9. Reopening an already migrated database is safe and idempotent.
    with tempfile.TemporaryDirectory() as d:
        db_path = os.path.join(d, "legacy.db")
        # create legacy schema
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE transitions (id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, data TEXT NOT NULL)")
        # Insert legacy row
        conn.execute("INSERT INTO transitions (ts, data) VALUES (?, ?)", (100.0, "{}"))
        conn.commit()
        conn.close()
        
        # Open with new LedgerStore
        store = LedgerStore(db_path=db_path)
        # Verify column exists and default is populated
        rows = store._conn.execute("SELECT retention_class FROM transitions").fetchall()
        assert rows[0][0] == "DEFAULT"
        store.close()
        
        # Idempotent re-open
        store2 = LedgerStore(db_path=db_path)
        cols = [r[1] for r in store2._conn.execute("PRAGMA table_info(transitions)").fetchall()]
        assert "retention_class" in cols
        store2.close()


def test_expiry_ttls():
    # 1. EPHEMERAL older than 6 hours expires
    # 2. EPHEMERAL younger than 6 hours remains
    # 3. DEFAULT older than 7 days expires
    # 4. DEFAULT younger than 7 days remains
    # 5. SIGNIFICANT older than 30 days expires
    # 6. SIGNIFICANT younger than 30 days remains
    with tempfile.TemporaryDirectory() as d:
        db_path = os.path.join(d, "ttl.db")
        store = LedgerStore(db_path=db_path)
        
        now = 10000000.0
        
        # Ephemeral
        store.append({"ts": now - 7*3600, "retention_class": "EPHEMERAL", "change": {}}) # expires
        store.append({"ts": now - 5*3600, "retention_class": "EPHEMERAL", "change": {}}) # remains
        
        # Default
        store.append({"ts": now - 8*24*3600, "retention_class": "DEFAULT", "change": {}}) # expires
        store.append({"ts": now - 6*24*3600, "retention_class": "DEFAULT", "change": {}}) # remains
        
        # Significant
        store.append({"ts": now - 31*24*3600, "retention_class": "SIGNIFICANT", "change": {}}) # expires
        store.append({"ts": now - 29*24*3600, "retention_class": "SIGNIFICANT", "change": {}}) # remains
        
        deleted = store.expire(now)
        assert deleted == 3
        
        # 10. Expiry is idempotent
        deleted_again = store.expire(now)
        assert deleted_again == 0
        
        leftover = store.recent(10)
        assert len(leftover) == 3
        
        # Ensure correct ones remained
        classes = {t["retention_class"] for t in leftover}
        assert classes == {"EPHEMERAL", "DEFAULT", "SIGNIFICANT"}
        
        # Ensure we didn't delete the young ones
        ages = {now - t["ts"] for t in leftover}
        assert min(ages) == 5*3600
        
        store.close()


def test_expiry_batch_size():
    # 11. Batch size bounds each expiry operation
    with tempfile.TemporaryDirectory() as d:
        db_path = os.path.join(d, "batch.db")
        store = LedgerStore(db_path=db_path)
        now = 10000000.0
        
        for _ in range(10):
            store.append({"ts": now - 7*3600, "retention_class": "EPHEMERAL", "change": {}})
            
        # Try to delete with batch size 4
        deleted = store.expire(now, batch_size=4)
        assert deleted == 4
        assert store.count() == 6
        
        deleted = store.expire(now, batch_size=10)
        assert deleted == 6
        assert store.count() == 0
        store.close()


def test_malformed_timestamps():
    # 13. Malformed timestamps do not crash and are not accidentally deleted
    with tempfile.TemporaryDirectory() as d:
        db_path = os.path.join(d, "malformed.db")
        store = LedgerStore(db_path=db_path)
        
        # Insert a string directly into SQLite bypassing LedgerStore.append to simulate bad row
        store._conn.execute("INSERT INTO transitions (ts, data, retention_class) VALUES (?, ?, ?)", ("bad_string", "{}", "EPHEMERAL"))
        store._conn.commit()
        
        now = 10000000.0
        # "bad_string" < number evaluates to FALSE in SQLite, so it's not deleted.
        deleted = store.expire(now)
        assert deleted == 0
        assert store.count() == 1
        
        # Try appending something unparsable via append() (it falls back to 0.0)
        store.append({"ts": "unparsable", "retention_class": "EPHEMERAL", "change": {}})
        assert store.count() == 2
        # Now it will delete the one that became 0.0
        deleted = store.expire(now)
        assert deleted == 1
        assert store.count() == 1 # The "bad_string" one is still there
        store.close()


def test_existing_callers_work():
    # 14. Existing query, replay and append behavior remains compatible.
    # 16. Existing callers that omit retention class still work.
    with tempfile.TemporaryDirectory() as d:
        db_path = os.path.join(d, "legacy_callers.db")
        store = LedgerStore(db_path=db_path)
        ledger = HistoryLedger(store=store)
        
        # Omit retention_class
        ledger.record(change={"path": "test", "old": 1, "new": 2}, snapshot={})
        
        # It's recorded and queryable
        res = ledger.recent(1)
        assert len(res) == 1
        assert res[0]["change"]["path"] == "test"
        assert res[0]["retention_class"] == "DEFAULT"
        
        assert store.count() == 1
        store.close()

def test_compression_tier0_to_tier1():
    with tempfile.TemporaryDirectory() as d:
        db_path = os.path.join(d, "t0_t1.db")
        store = LedgerStore(db_path=db_path)
        
        now = 10000000.0
        # Newer than 24 hours (should not compress)
        store.append({"ts": now - 3600, "change": {"path": "system.cpu", "new": {"value": 50}}, "retention_class": "EPHEMERAL"})
        
        # Older than 24 hours (should compress).
        base_ts = float(int((now - 48*3600) // 60) * 60)
        
        # Topic 1: numeric structured
        store.append({"ts": base_ts + 1, "change": {"path": "system.cpu", "new": {"cpu_percent": 10}}, "retention_class": "EPHEMERAL"})
        store.append({"ts": base_ts + 5, "change": {"path": "system.cpu", "new": {"cpu_percent": 90}}, "retention_class": "EPHEMERAL"})
        store.append({"ts": base_ts + 10, "change": {"path": "system.cpu", "new": {"cpu_percent": 50}}, "retention_class": "EPHEMERAL"})
        
        # Topic 2: non-numeric
        store.append({"ts": base_ts + 2, "change": {"path": "screen.window", "new": "WindowA"}, "retention_class": "EPHEMERAL"})
        store.append({"ts": base_ts + 8, "change": {"path": "screen.window", "new": "WindowB"}, "retention_class": "EPHEMERAL"})
        
        # Topic 1 but different retention class (should NOT merge with the other EPHEMERAL one)
        store.append({"ts": base_ts + 3, "change": {"path": "system.cpu", "new": {"cpu_percent": 100}}, "retention_class": "SIGNIFICANT"})
        
        # Malformed payload (ts is fine)
        store._conn.execute("INSERT INTO transitions (ts, data, retention_class) VALUES (?, ?, ?)", (base_ts + 4, "{malformed json", "EPHEMERAL"))
        store._conn.commit()

        # Malformed ts (string)
        store._conn.execute("INSERT INTO transitions (ts, data, retention_class) VALUES (?, ?, ?)", ("bad_ts", "{}", "EPHEMERAL"))
        store._conn.commit()

        # Compress
        res = store.compress(now)
        
        # 1. Tier 0 newer than 24h untouched
        row = store._conn.execute("SELECT data FROM transitions WHERE ts = ?", (now - 3600,)).fetchone()
        assert row is not None
        assert json.loads(row[0])["change"]["path"] == "system.cpu"
        
        # 2, 4, 6, 7, 10. Summaries created correctly
        sums = store.recent_summaries(10)
        assert len(sums) == 3
        
        cpu_eph = [s for s in sums if s["topic"] == "system.cpu" and s["retention_class"] == "EPHEMERAL"][0]
        cpu_sig = [s for s in sums if s["topic"] == "system.cpu" and s["retention_class"] == "SIGNIFICANT"][0]
        win_eph = [s for s in sums if s["topic"] == "screen.window" and s["retention_class"] == "EPHEMERAL"][0]
        
        assert cpu_eph["tier"] == 1
        assert cpu_eph["bucket_start"] == base_ts
        assert cpu_eph["event_count"] == 3
        
        # 8. Numeric field aggregation
        agg = cpu_eph["aggregate"]
        assert "cpu_percent" in agg
        assert agg["cpu_percent"]["count"] == 3
        assert agg["cpu_percent"]["min"] == 10.0
        assert agg["cpu_percent"]["max"] == 90.0
        assert agg["cpu_percent"]["avg"] == 50.0
        
        # 9. Non-numeric first/last
        assert win_eph["first_payload"] == "WindowA"
        assert win_eph["last_payload"] == "WindowB"
        assert win_eph["event_count"] == 2
        
        # 16, 17. Malformed reported and skipped
        assert len(res["malformed_row_ids"]) == 1
        assert res["source_rows_skipped"] == 1
        
        # Malformed rows should still be in the DB
        assert store._conn.execute("SELECT COUNT(*) FROM transitions WHERE data = '{malformed json'").fetchone()[0] == 1
        assert store._conn.execute("SELECT COUNT(*) FROM transitions WHERE ts = 'bad_ts'").fetchone()[0] == 1
        
        store.close()

def test_compression_tier1_to_tier2():
    with tempfile.TemporaryDirectory() as d:
        db_path = os.path.join(d, "t1_t2.db")
        store = LedgerStore(db_path=db_path)
        
        now = 10000000.0
        base_ts = float(int((now - 10*24*3600) // 3600) * 3600)
        
        # Insert raw rows spanning across different minutes but same hour
        # Bucket 1: min 0
        store.append({"ts": base_ts + 10, "change": {"path": "system.cpu", "new": {"val": 10}}, "retention_class": "EPHEMERAL"})
        store.append({"ts": base_ts + 20, "change": {"path": "system.cpu", "new": {"val": 30}}, "retention_class": "EPHEMERAL"})
        # Bucket 2: min 10
        store.append({"ts": base_ts + 610, "change": {"path": "system.cpu", "new": {"val": 20}}, "retention_class": "EPHEMERAL"})
        store.append({"ts": base_ts + 620, "change": {"path": "system.cpu", "new": {"val": 40}}, "retention_class": "EPHEMERAL"})
        
        # First compress to push them to Tier 1
        # Use a 'now' such that they are > 24h old but NOT > 7d old
        mid_now = base_ts + 2 * 24 * 3600
        res1 = store.compress(mid_now)
        assert res1["tier0_to_tier1"] == 4
        assert res1["tier1_to_tier2"] == 0
        
        sums = store.recent_summaries(10)
        assert len(sums) == 2
        assert all(s["tier"] == 1 for s in sums)
        
        # Now compress again with 'now' such that they are > 7d old
        res2 = store.compress(now)
        assert res2["tier1_to_tier2"] == 2
        
        sums2 = store.recent_summaries(10)
        assert len(sums2) == 1
        t2 = sums2[0]
        assert t2["tier"] == 2
        assert t2["bucket_start"] == base_ts
        assert t2["event_count"] == 4
        
        # Weighted average test:
        # Bucket 1 avg: 20 (count 2)
        # Bucket 2 avg: 30 (count 2)
        # Total avg: 25. min: 10, max: 40
        agg = t2["aggregate"]["val"]
        assert agg["count"] == 4
        assert agg["min"] == 10.0
        assert agg["max"] == 40.0
        assert agg["avg"] == 25.0
        
        store.close()

def test_compression_batch_split_idempotency():
    with tempfile.TemporaryDirectory() as d:
        db_path = os.path.join(d, "batch_idempotency.db")
        store = LedgerStore(db_path=db_path)
        
        now = 10000000.0
        base_ts = float(int((now - 48*3600) // 60) * 60)
        
        # 10 records in the same minute bucket
        for i in range(10):
            store.append({"ts": base_ts + i, "change": {"path": "counter", "new": {"val": i}}, "retention_class": "DEFAULT"})
            
        # Compress with batch_size=4
        res1 = store.compress(now, batch_size=4)
        assert res1["source_rows_processed"] == 4
        
        sums = store.recent_summaries(10)
        assert len(sums) == 1
        assert sums[0]["event_count"] == 4
        assert sums[0]["aggregate"]["val"]["max"] == 3.0
        
        # Re-run same batch size
        res2 = store.compress(now, batch_size=4)
        assert res2["source_rows_processed"] == 4
        
        sums = store.recent_summaries(10)
        assert len(sums) == 1 # Still 1 bucket!
        assert sums[0]["event_count"] == 8
        assert sums[0]["aggregate"]["val"]["max"] == 7.0
        
        # Finish remaining
        res3 = store.compress(now, batch_size=4)
        assert res3["source_rows_processed"] == 2
        
        sums = store.recent_summaries(10)
        assert len(sums) == 1
        assert sums[0]["event_count"] == 10
        assert sums[0]["aggregate"]["val"]["min"] == 0.0
        assert sums[0]["aggregate"]["val"]["max"] == 9.0
        assert sums[0]["aggregate"]["val"]["avg"] == 4.5
        
        store.close()

def test_compression_rollback_on_failure(monkeypatch):
    with tempfile.TemporaryDirectory() as d:
        db_path = os.path.join(d, "rollback.db")
        store = LedgerStore(db_path=db_path)
        
        now = 10000000.0
        base_ts = float(int((now - 48*3600) // 60) * 60)
        
        store.append({"ts": base_ts + 1, "change": {"path": "test", "new": 1}, "retention_class": "DEFAULT"})
        
        # Inject failure into _upsert_summaries_locked
        original_upsert = store._upsert_summaries_locked
        def mock_upsert(*args, **kwargs):
            raise Exception("Injected failure")
        
        monkeypatch.setattr(store, "_upsert_summaries_locked", mock_upsert)
        
        res = store.compress(now)
        assert res["source_rows_removed"] == 0
        
        # Ensure source rows remain
        assert store.count() == 1
        assert len(store.recent_summaries(10)) == 0
        
        store.close()

def test_compression_legacy_readability():
    with tempfile.TemporaryDirectory() as d:
        db_path = os.path.join(d, "legacy.db")
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE transitions (id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, data TEXT NOT NULL)")
        conn.execute("INSERT INTO transitions (ts, data) VALUES (?, ?)", (100.0, '{"change": {"path": "old_topic", "new": 42}}'))
        conn.commit()
        conn.close()
        
        # Upgrade
        store = LedgerStore(db_path=db_path)
        
        # Legacy readability API
        recent = store.recent(10)
        assert len(recent) == 1
        assert recent[0]["change"]["path"] == "old_topic"
        
        now = 100.0 + 48*3600 # make it 48h old
        store.compress(now)
        
        # Compressed
        sums = store.recent_summaries(10)
        assert len(sums) == 1
        assert sums[0]["topic"] == "old_topic"
        
        # Idempotent re-open
        store.close()
        store2 = LedgerStore(db_path=db_path)
        sums2 = store2.recent_summaries(10)
        assert len(sums2) == 1
        store2.close()
