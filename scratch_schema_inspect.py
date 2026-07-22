import sqlite3
import json
from shared_core.memory_engine.manager import MemoryManager

def inspect_schema():
    mgr = MemoryManager()
    conn = mgr.conn
    
    query = """
    SELECT name, type, sql
    FROM sqlite_master
    WHERE type IN ('table', 'view', 'trigger', 'index')
    ORDER BY type, name;
    """
    
    rows = conn.execute(query).fetchall()
    
    results = []
    for row in rows:
        results.append({
            "name": row[0],
            "type": row[1],
            "sql": row[2]
        })
        
    with open("schema_dump.json", "w") as f:
        json.dump(results, f, indent=2)

if __name__ == "__main__":
    inspect_schema()
