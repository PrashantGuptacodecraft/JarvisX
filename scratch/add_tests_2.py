import re

with open("tests/test_historical_query.py", "r") as f:
    text = f.read()

more_tests = """
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
    now = time.time()
    t_tier1 = now - 24 * 3600
    t_tier2 = now - 7 * 24 * 3600
    # Data exactly at boundary
    seed_data(temp_store, 1, t_tier1)
    temp_store.compress(now, 100)
    page = temp_store.query_history(t_tier1, t_tier1 + 10)
    # Tier 0 should start at t_tier1 (max(start_time, t_tier1)), so t_tier1 is queried from Tier 0
    # Wait, if start_time is t_tier1, it's Tier 0.
    assert len(page["records"]) == 1

def test_33_invalid_topics_type(temp_store):
    with pytest.raises(ValueError):
        temp_store.query_history(0, 200, topics="single_string_instead_of_list")

def test_34_cursor_decode_invalid_base64(temp_store):
    with pytest.raises(ValueError, match="Malformed cursor payload"):
        temp_store.query_history(0, 200, cursor="invalid_base64")

def test_35_cursor_decode_missing_fields(temp_store):
    import base64
    import json
    bad_json = json.dumps({"v": 1}).encode("ascii")
    bad_cursor = base64.urlsafe_b64encode(bad_json).decode("ascii")
    with pytest.raises(KeyError):
        temp_store.query_history(0, 200, cursor=bad_cursor)

def test_36_cursor_decode_wrong_version(temp_store):
    import base64
    import json
    bad_json = json.dumps({"v": 2}).encode("ascii")
    bad_cursor = base64.urlsafe_b64encode(bad_json).decode("ascii")
    with pytest.raises(ValueError, match="Unsupported cursor version"):
        temp_store.query_history(0, 200, cursor=bad_cursor)

def test_37_cursor_resolution_mismatch(temp_store):
    seed_data(temp_store, 2, 100.0)
    page = temp_store.query_history(0, 200, limit=1, resolution=ResolutionMode.RAW)
    with pytest.raises(ValueError, match="Cursor resolution does not match requested resolution."):
        temp_store.query_history(0, 200, limit=1, resolution=ResolutionMode.MINUTE, cursor=page["next_cursor"])
"""

text += "\n" + more_tests

with open("tests/test_historical_query.py", "w") as f:
    f.write(text)
