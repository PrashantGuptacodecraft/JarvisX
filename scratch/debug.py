import sqlite3
import pytest
from tests.test_historical_query import seed_data, temp_store
from shared_core.state_manager.history_models import ResolutionMode

def test_debug(temp_store):
    seed_data(temp_store, 5, 100.0)
    res = temp_store.compress(200.0 + 24*3600, 100)
    print("COMPRESS RES:", res)
    
    rows0 = temp_store._conn.execute("SELECT * FROM transitions").fetchall()
    print("TIER 0:", rows0)
    
    rows1 = temp_store._conn.execute("SELECT * FROM ledger_summaries").fetchall()
    print("SUMMARIES:", rows1)
    
    page = temp_store.query_history(0.0, 200.0, resolution=ResolutionMode.MINUTE)
    print("PAGE:", page)
