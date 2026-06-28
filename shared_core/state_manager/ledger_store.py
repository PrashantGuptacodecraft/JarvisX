"""ledger_store.py - rolling local persistence for the World-State History Ledger.

Phase B · BL4 (append), BL5 (rolling cap / no unbounded disk growth), BL8 (reload on boot).

A single SQLite table of transitions. After each append, the store prunes anything older than
the rolling row cap, so disk usage is bounded. Later phases (C: memory/KG) may compress old
history into long-term semantic memory before it is pruned.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading

from config.logger import get_logger

log = get_logger("state.ledger")

# Default location under the existing data/ directory (kept stable across phases).
_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")
DEFAULT_DB = os.path.join(_DATA_DIR, "world_ledger.db")


class LedgerStore:
    def __init__(self, db_path: str = DEFAULT_DB, cap: int = 50000, prune_every: int = 200):
        self.db_path = db_path
        self.cap = int(cap)
        self._prune_every = max(1, int(prune_every))
        self._since_prune = 0
        self._lock = threading.Lock()
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS transitions ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, data TEXT NOT NULL)"
        )
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_transitions_ts ON transitions(ts)")
        self._conn.commit()

    def append(self, transition: dict) -> None:
        data = json.dumps(transition, default=str)
        ts = float(transition.get("ts", 0.0))
        with self._lock:
            self._conn.execute("INSERT INTO transitions(ts, data) VALUES (?, ?)", (ts, data))
            self._conn.commit()
            self._since_prune += 1
            if self._since_prune >= self._prune_every:
                self._prune_locked()
                self._since_prune = 0

    def _prune_locked(self) -> int:
        """Delete the oldest rows beyond `cap`. Returns rows deleted."""
        cur = self._conn.execute(
            "DELETE FROM transitions WHERE id <= "
            "(SELECT MAX(id) FROM transitions) - ?", (self.cap,)
        )
        self._conn.commit()
        return cur.rowcount or 0

    def recent(self, n: int = 500) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT data FROM transitions ORDER BY id DESC LIMIT ?", (int(n),)
            ).fetchall()
        out = [json.loads(r[0]) for r in rows]
        out.reverse()   # chronological order
        return out

    def count(self) -> int:
        with self._lock:
            return self._conn.execute("SELECT COUNT(*) FROM transitions").fetchone()[0]

    def close(self) -> None:
        with self._lock:
            try:
                self._conn.close()
            except Exception:
                pass
