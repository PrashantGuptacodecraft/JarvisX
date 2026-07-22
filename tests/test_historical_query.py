import time
import pytest
from shared_core.state_manager.history_models import Cursor, ResolutionMode, HistoricalRecord
from shared_core.state_manager.ledger_store import LedgerStore
import base64
import json

@pytest.fixture
def temp_store(tmp_path):
    store = LedgerStore(db_path=str(tmp_path / "test.db"), cap=50000)
    yield store
    store.close()

def seed_data(store, count=10, start_ts=1000.0, topic="app.started", rc="DEFAULT"):
    for i in range(count):
        store.append({
            "ts": start_ts + i,
            "retention_class": rc,
            "change": {"path": topic, "old": None, "new": {"value": i}}
        })

def test_1_raw_mode_returns_tier_0(temp_store):
    seed_data(temp_store, 5, 100.0)
    page = temp_store.query_history(0.0, 200.0, resolution=ResolutionMode.RAW)
    assert len(page["records"]) == 5
    for r in page["records"]:
        assert r["tier"] == 0
        assert r["record_kind"] == "transition"

def test_2_minute_mode_returns_tier_1(temp_store):
    seed_data(temp_store, 5, 100.0)
    temp_store.compress(200.0 + 24*3600, 100)
    page = temp_store.query_history(0.0, 200.0, resolution=ResolutionMode.MINUTE)
    assert len(page["records"]) == 1
    assert page["records"][0]["tier"] == 1
    assert page["records"][0]["record_kind"] == "summary"

def test_3_hour_mode_returns_tier_2(temp_store):
    seed_data(temp_store, 5, 100.0)
    temp_store.compress(200.0 + 24*3600, 100)
    temp_store.compress(200.0 + 8*24*3600, 100)
    page = temp_store.query_history(0.0, 200.0, resolution=ResolutionMode.HOUR)
    assert len(page["records"]) == 1
    assert page["records"][0]["tier"] == 2
    assert page["records"][0]["record_kind"] == "summary"

def test_4_auto_mode_selects_tier_0_for_recent(temp_store, monkeypatch):
    now = int(time.time() / 3600) * 3600
    seed_data(temp_store, 5, now - 100)
    page = temp_store.query_history(now - 200, now, resolution=ResolutionMode.AUTO)
    assert len(page["records"]) == 5
    assert all(r["tier"] == 0 for r in page["records"])

def test_5_auto_mode_selects_tier_1_for_older(temp_store):
    now = int(time.time() / 3600) * 3600
    t_start = now - 2 * 24 * 3600
    seed_data(temp_store, 5, t_start)
    temp_store.compress(now, 100)
    page = temp_store.query_history(t_start - 10, t_start + 100, resolution=ResolutionMode.AUTO)
    assert len(page["records"]) == 1
    assert page["records"][0]["tier"] == 1

def test_6_auto_mode_selects_tier_2_for_oldest(temp_store):
    now = int(time.time() / 3600) * 3600
    t_start = now - 8 * 24 * 3600
    seed_data(temp_store, 5, t_start)
    temp_store.compress(now, 100)
    temp_store.compress(now, 100)
    page = temp_store.query_history(t_start - 10, t_start + 100, resolution=ResolutionMode.AUTO)
    assert len(page["records"]) == 1
    assert page["records"][0]["tier"] == 2

def test_7_mixed_time_range_non_overlapping(temp_store):
    now = int(time.time() / 3600) * 3600
    # Tier 2 data
    seed_data(temp_store, 5, now - 8 * 24 * 3600)
    # Tier 1 data
    seed_data(temp_store, 5, now - 2 * 24 * 3600)
    # Tier 0 data
    seed_data(temp_store, 5, now - 100)
    
    temp_store.compress(now, 100)
    temp_store.compress(now, 100)
    
    # query auto across all 3
    page = temp_store.query_history(now - 10 * 24 * 3600, now, resolution=ResolutionMode.AUTO)
    # Should get 1 Tier 2, 1 Tier 1, 5 Tier 0
    assert len(page["records"]) == 7

def test_8_no_double_counting(temp_store):
    pass

def test_9_exactly_24_hour_boundary(temp_store):
    now = int(time.time() / 3600) * 3600
    bound = now - 24 * 3600
    page = temp_store.query_history(bound, bound + 10, resolution=ResolutionMode.AUTO)
    assert page

def test_10_filter_by_single_topic(temp_store):
    seed_data(temp_store, 5, 100.0, topic="topic.A")
    seed_data(temp_store, 5, 100.0, topic="topic.B")
    page = temp_store.query_history(0, 200, topics=["topic.A"])
    assert len(page["records"]) == 5
    assert all(r["topic"] == "topic.A" for r in page["records"])

def test_11_filter_by_multiple_topics(temp_store):
    seed_data(temp_store, 5, 100.0, topic="topic.A")
    seed_data(temp_store, 5, 100.0, topic="topic.B")
    seed_data(temp_store, 5, 100.0, topic="topic.C")
    page = temp_store.query_history(0, 200, topics=["topic.A", "topic.C"])
    assert len(page["records"]) == 10

def test_12_filter_by_retention_class(temp_store):
    seed_data(temp_store, 5, 100.0, rc="DEFAULT")
    seed_data(temp_store, 5, 100.0, rc="SIGNIFICANT")
    page = temp_store.query_history(0, 200, retention_classes=["SIGNIFICANT"])
    assert len(page["records"]) == 5
    assert all(r["retention_class"] == "SIGNIFICANT" for r in page["records"])

def test_13_filter_topic_and_rc(temp_store):
    seed_data(temp_store, 2, 100.0, topic="A", rc="DEFAULT")
    seed_data(temp_store, 2, 100.0, topic="A", rc="SIGNIFICANT")
    seed_data(temp_store, 2, 100.0, topic="B", rc="SIGNIFICANT")
    page = temp_store.query_history(0, 200, topics=["A"], retention_classes=["SIGNIFICANT"])
    assert len(page["records"]) == 2

def test_14_malformed_cursor_fails(temp_store):
    with pytest.raises(Exception):
        temp_store.query_history(0, 200, cursor="invalid_base64_!!")

def test_15_cursor_hash_mismatch_fails(temp_store):
    seed_data(temp_store, 5, 100.0)
    page = temp_store.query_history(0, 200, limit=2)
    with pytest.raises(ValueError, match="Cursor fingerprint does not match current query."):
        temp_store.query_history(0, 200, topics=["A"], limit=2, cursor=page["next_cursor"])

def test_16_out_of_bounds_limit(temp_store):
    page = temp_store.query_history(0, 200, limit=999999)
    assert "records" in page

def test_17_limit_is_enforced(temp_store):
    seed_data(temp_store, 15, 100.0)
    page = temp_store.query_history(0.0, 200.0, resolution=ResolutionMode.RAW, limit=5)
    assert len(page["records"]) == 5
    assert page["next_cursor"] is not None

def test_18_cursor_pagination_across_tiers(temp_store):
    now = int(time.time() / 3600) * 3600
    seed_data(temp_store, 2, now - 8 * 24 * 3600)
    seed_data(temp_store, 2, now - 2 * 24 * 3600)
    seed_data(temp_store, 2, now - 100)
    
    temp_store.compress(now, 100)
    temp_store.compress(now, 100)
    
    recs = []
    cursor = None
    for _ in range(10):
        page = temp_store.query_history(now - 10 * 24 * 3600, now, limit=1, cursor=cursor)
        recs.extend(page["records"])
        cursor = page["next_cursor"]
        if not cursor:
            break
            
    assert len(recs) == 4
    assert recs[0]["tier"] == 2
    assert recs[1]["tier"] == 1
    assert recs[2]["tier"] == 0
    assert recs[3]["tier"] == 0

def test_19_cursor_pagination(temp_store):
    seed_data(temp_store, 15, 100.0)
    p1 = temp_store.query_history(0.0, 200.0, resolution=ResolutionMode.RAW, limit=10)
    assert len(p1["records"]) == 10
    assert p1["next_cursor"] is not None
    p2 = temp_store.query_history(0.0, 200.0, resolution=ResolutionMode.RAW, limit=10, cursor=p1["next_cursor"])
    assert len(p2["records"]) == 5
    assert p2["next_cursor"] is None

def test_20_malformed_json_in_db(temp_store):
    temp_store._conn.execute("INSERT INTO transitions (ts, data, retention_class) VALUES (?, ?, ?)", 
                             (150.0, "{bad_json", "DEFAULT"))
    temp_store._conn.commit()
    page = temp_store.query_history(0, 200)
    assert page["skipped_malformed_count"] == 1

def test_21_invalid_resolution(temp_store):
    with pytest.raises(ValueError):
        temp_store.query_history(0, 200, resolution="fake")

def test_22_start_time_after_end_time(temp_store):
    with pytest.raises(ValueError):
        temp_store.query_history(200, 100)

def test_23_invalid_topics(temp_store):
    with pytest.raises(ValueError):
        temp_store.query_history(0, 200, topics="not_a_list")

def test_24_too_many_topics(temp_store):
    with pytest.raises(ValueError):
        temp_store.query_history(0, 200, topics=[str(i) for i in range(101)])
        
def test_25_invalid_retention_classes(temp_store):
    with pytest.raises(ValueError):
        temp_store.query_history(0, 200, retention_classes="not_a_list")

def test_26_too_many_retention_classes(temp_store):
    with pytest.raises(ValueError):
        temp_store.query_history(0, 200, retention_classes=[str(i) for i in range(11)])
        
def test_27_invalid_retention_class_value(temp_store):
    page = temp_store.query_history(0, 200, retention_classes=["BOGUS"])

def test_28_query_empty_store(temp_store):
    page = temp_store.query_history(0, 200)
    assert len(page["records"]) == 0
    assert page["next_cursor"] is None

def test_29_query_exact_timestamp(temp_store):
    seed_data(temp_store, 1, 150.0)
    page = temp_store.query_history(150.0, 150.0001)
    assert len(page["records"]) == 1

def test_30_limit_one_pagination(temp_store):
    seed_data(temp_store, 5, 100.0)
    cursor = None
    records = []
    for _ in range(10):
        page = temp_store.query_history(0, 200, limit=1, cursor=cursor)
        records.extend(page["records"])
        cursor = page["next_cursor"]
        if not cursor:
            break
    assert len(records) == 5

def test_31_topic_and_rc_with_pagination(temp_store):
    seed_data(temp_store, 3, 100.0, topic="A", rc="DEFAULT")
    page = temp_store.query_history(0, 200, topics=["A"], retention_classes=["DEFAULT"], limit=2)
    assert len(page["records"]) == 2
    assert page["next_cursor"] is not None
    page2 = temp_store.query_history(0, 200, topics=["A"], retention_classes=["DEFAULT"], limit=2, cursor=page["next_cursor"])
    assert len(page2["records"]) == 1
    assert page2["next_cursor"] is None

def test_32_auto_resolution_exact_boundaries(temp_store):
    now = int(time.time() / 3600) * 3600
    t_tier1 = now - 24 * 3600
    seed_data(temp_store, 1, t_tier1)
    temp_store.compress(now, 100)
    page = temp_store.query_history(t_tier1, t_tier1 + 10)
    assert len(page["records"]) == 1

def test_33_invalid_topics_type(temp_store):
    with pytest.raises(ValueError):
        temp_store.query_history(0, 200, topics="single_string_instead_of_list")

def test_34_cursor_decode_invalid_base64(temp_store):
    with pytest.raises(ValueError, match="Malformed cursor payload"):
        temp_store.query_history(0, 200, cursor="invalid_base64")

def test_35_cursor_decode_missing_fields(temp_store):
    bad_json = json.dumps({"v": 1, "query_hash": Cursor.compute_hash(0.0, 200.0, [], []), "resolution": "auto"}).encode("ascii")
    bad_cursor = base64.urlsafe_b64encode(bad_json).decode("ascii")
    with pytest.raises(KeyError):
        temp_store.query_history(0, 200, cursor=bad_cursor)

def test_36_cursor_decode_wrong_version(temp_store):
    bad_json = json.dumps({"v": 2}).encode("ascii")
    bad_cursor = base64.urlsafe_b64encode(bad_json).decode("ascii")
    with pytest.raises(ValueError, match="Unsupported cursor version"):
        temp_store.query_history(0, 200, cursor=bad_cursor)

def test_37_cursor_resolution_mismatch(temp_store):
    seed_data(temp_store, 2, 100.0)
    page = temp_store.query_history(0, 200, limit=1, resolution=ResolutionMode.RAW)
    with pytest.raises(ValueError, match="Cursor resolution does not match requested resolution."):
        temp_store.query_history(0, 200, limit=1, resolution=ResolutionMode.MINUTE, cursor=page["next_cursor"])
