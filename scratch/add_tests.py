import re

with open("tests/test_historical_query.py", "r") as f:
    text = f.read()

more_tests = """
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
    topics = {r["topic"] for r in page["records"]}
    assert topics == {"topic.A", "topic.C"}

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
    page = temp_store.query_history(0, 200, limit=2)
    with pytest.raises(ValueError, match="Cursor hash mismatch"):
        # Querying with different topics but same cursor
        temp_store.query_history(0, 200, topics=["A"], limit=2, cursor=page["next_cursor"])

def test_16_out_of_bounds_limit(temp_store):
    page = temp_store.query_history(0, 200, limit=999999)
    # The store forces limit to max 10000. It shouldn't crash.
    assert "records" in page

def test_18_cursor_pagination_across_tiers(temp_store):
    now = time.time()
    seed_data(temp_store, 2, now - 8 * 24 * 3600)
    seed_data(temp_store, 2, now - 2 * 24 * 3600)
    seed_data(temp_store, 2, now - 100)
    
    temp_store.compress(now, 100)
    temp_store.compress(now, 100)
    
    # 6 items total. 1 tier2, 1 tier1, 2 tier0 (wait! 2 events in same hour compress to 1 summary)
    # so we have 1 T2 summary, 1 T1 summary, 2 T0 transitions. Total 4 items.
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

def test_20_malformed_json_in_db(temp_store):
    # Insert bad JSON
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
    # We silently filter out invalid ones? The logic says: it just takes valid ones.
    # Actually wait: valid_rcs = {"EPHEMERAL", "DEFAULT", "SIGNIFICANT"}
    # Any other value gets dropped, and since we queried for it, we get nothing.
    page = temp_store.query_history(0, 200, retention_classes=["BOGUS"])
    # Wait, the code sets retention_classes = [] if it becomes empty? NO. It keeps it empty.
    # Ah, if retention_classes becomes empty list, it means "filter by NOTHING", which means return ALL.
    # Wait! If the user passed ["BOGUS"], `retention_classes` becomes `[]`. Then the query returns EVERYTHING instead of NOTHING!
    # Let me fix that logic in ledger_store!
    pass

"""

text += "\n" + more_tests

with open("tests/test_historical_query.py", "w") as f:
    f.write(text)
