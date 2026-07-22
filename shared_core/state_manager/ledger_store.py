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
        
        # BC1: Idempotent schema migration
        cur = self._conn.execute("PRAGMA table_info(transitions)")
        cols = [row[1] for row in cur.fetchall()]
        if "retention_class" not in cols:
            self._conn.execute("ALTER TABLE transitions ADD COLUMN retention_class TEXT DEFAULT 'DEFAULT'")
            
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_transitions_ts ON transitions(ts)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_transitions_class_ts ON transitions(retention_class, ts)")
        # BC4: Enhanced cursor pagination indexes
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_transitions_ts_id ON transitions(ts, id)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_transitions_rc_ts_id ON transitions(retention_class, ts, id)")

        # BC2: Summaries table
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS ledger_summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tier INTEGER NOT NULL,
                bucket_start REAL NOT NULL,
                bucket_end REAL NOT NULL,
                topic TEXT NOT NULL,
                retention_class TEXT NOT NULL DEFAULT 'DEFAULT',
                first_payload_json TEXT,
                first_ts REAL,
                last_payload_json TEXT,
                last_ts REAL,
                aggregate_json TEXT NOT NULL,
                event_count INTEGER NOT NULL,
                source_min_id INTEGER,
                source_max_id INTEGER,
                source_count INTEGER NOT NULL,
                schema_version INTEGER NOT NULL DEFAULT 1,
                created_at REAL NOT NULL
            )
        """)
        self._conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_summaries_uniq "
            "ON ledger_summaries(tier, bucket_start, topic, retention_class)"
        )
        # BC4: Enhanced cursor pagination indexes
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_summaries_tier_bstart_id ON ledger_summaries(tier, bucket_start, id)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_summaries_tier_topic_bstart_id ON ledger_summaries(tier, topic, bucket_start, id)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_summaries_tier_rc_bstart_id ON ledger_summaries(tier, retention_class, bucket_start, id)")
        
        self._conn.commit()

    def append(self, transition: dict) -> None:
        data = json.dumps(transition, default=str)
        try:
            ts = float(transition.get("ts", 0.0))
        except (ValueError, TypeError):
            ts = 0.0
            
        ret_class = transition.get("retention_class", "DEFAULT")
        if ret_class not in ("EPHEMERAL", "DEFAULT", "SIGNIFICANT"):
            ret_class = "DEFAULT"
            
        with self._lock:
            self._conn.execute("INSERT INTO transitions(ts, data, retention_class) VALUES (?, ?, ?)", (ts, data, ret_class))
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

    def expire(self, now: float, batch_size: int = 500) -> int:
        """BC1: Remove expired records transactionally in bounded batches."""
        deleted = 0
        with self._lock:
            try:
                cur = self._conn.execute(
                    """
                    SELECT id FROM transitions 
                    WHERE (retention_class = 'EPHEMERAL' AND ts < ?)
                       OR (retention_class = 'DEFAULT' AND ts < ?)
                       OR (retention_class = 'SIGNIFICANT' AND ts < ?)
                    LIMIT ?
                    """,
                    (now - 21600, now - 604800, now - 2592000, int(batch_size))
                )
                rows = cur.fetchall()
                if not rows:
                    return 0
                
                ids = [r[0] for r in rows]
                placeholders = ",".join("?" for _ in ids)
                del_cur = self._conn.execute(f"DELETE FROM transitions WHERE id IN ({placeholders})", ids)
                self._conn.commit()
                deleted = del_cur.rowcount or 0
            except sqlite3.Error as exc:
                log.warning(f"Ledger expiry failed: {exc}")
                
        return deleted

    def compress(self, now: float, batch_size: int = 500) -> dict:
        """BC2: Tiered Snapshot Compression (Tier 1 -> Tier 2, then Tier 0 -> Tier 1)."""
        import time
        res = {
            "source_rows_examined": 0,
            "source_rows_processed": 0,
            "source_rows_skipped": 0,
            "summaries_created": 0,
            "summaries_updated": 0,
            "source_rows_removed": 0,
            "tier0_to_tier1": 0,
            "tier1_to_tier2": 0,
            "malformed_row_ids": [],
        }
        remaining = batch_size
        if remaining > 0:
            processed = self._compress_tier1_to_tier2(now, remaining, res)
            remaining -= processed
        if remaining > 0:
            self._compress_tier0_to_tier1(now, remaining, res)
        return res

    def _compress_tier1_to_tier2(self, now: float, batch_size: int, res: dict) -> int:
        processed = 0
        with self._lock:
            try:
                self._conn.execute("BEGIN TRANSACTION")
                cur = self._conn.execute(
                    "SELECT id, bucket_start, bucket_end, topic, retention_class, "
                    "first_payload_json, first_ts, last_payload_json, last_ts, "
                    "aggregate_json, event_count, source_min_id, source_max_id, source_count "
                    "FROM ledger_summaries WHERE tier = 1 AND bucket_start < ? ORDER BY bucket_start ASC LIMIT ?",
                    (now - 7 * 24 * 3600, int(batch_size))
                )
                rows = cur.fetchall()
                if not rows:
                    self._conn.commit()
                    return 0
                res["source_rows_examined"] += len(rows)
                
                buckets = {}
                deletable_ids = []
                for r in rows:
                    sid, bstart, bend, topic, rc, f_json, f_ts, l_json, l_ts, agg_json, ev_c, src_min, src_max, src_c = r
                    try:
                        f_pay = json.loads(f_json) if f_json else None
                        l_pay = json.loads(l_json) if l_json else None
                        agg = json.loads(agg_json) if agg_json else {}
                    except Exception:
                        res["malformed_row_ids"].append(sid)
                        res["source_rows_skipped"] += 1
                        continue
                        
                    t2_start = float(int(bstart // 3600) * 3600)
                    t2_end = t2_start + 3600.0
                    key = (t2_start, topic, rc)
                    
                    if key not in buckets:
                        buckets[key] = {
                            "tier": 2, "bstart": t2_start, "bend": t2_end, "topic": topic, "rc": rc,
                            "f_pay": f_pay, "f_ts": f_ts, "l_pay": l_pay, "l_ts": l_ts,
                            "agg": agg.copy(), "ev_c": ev_c, "src_min": src_min, "src_max": src_max, "src_c": src_c
                        }
                    else:
                        b = buckets[key]
                        if f_ts is not None and (b["f_ts"] is None or f_ts < b["f_ts"]):
                            b["f_ts"] = f_ts; b["f_pay"] = f_pay
                        if l_ts is not None and (b["l_ts"] is None or l_ts > b["l_ts"]):
                            b["l_ts"] = l_ts; b["l_pay"] = l_pay
                        for k, v in agg.items():
                            if k not in b["agg"]:
                                b["agg"][k] = v.copy()
                            else:
                                bk = b["agg"][k]
                                old_c = bk["count"]
                                bk["count"] += v["count"]
                                if v["min"] is not None and (bk["min"] is None or v["min"] < bk["min"]): bk["min"] = v["min"]
                                if v["max"] is not None and (bk["max"] is None or v["max"] > bk["max"]): bk["max"] = v["max"]
                                if bk["avg"] is not None and v["avg"] is not None and bk["count"] > 0:
                                    bk["avg"] = (bk["avg"] * old_c + v["avg"] * v["count"]) / bk["count"]
                                elif bk["avg"] is None:
                                    bk["avg"] = v["avg"]
                        b["ev_c"] += ev_c; b["src_c"] += src_c
                        if src_min is not None and (b["src_min"] is None or src_min < b["src_min"]): b["src_min"] = src_min
                        if src_max is not None and (b["src_max"] is None or src_max > b["src_max"]): b["src_max"] = src_max
                    deletable_ids.append(sid)
                    processed += 1
                    res["source_rows_processed"] += 1
                    res["tier1_to_tier2"] += 1
                
                self._upsert_summaries_locked(list(buckets.values()), res)
                if deletable_ids:
                    places = ",".join("?" for _ in deletable_ids)
                    d_cur = self._conn.execute(f"DELETE FROM ledger_summaries WHERE id IN ({places})", deletable_ids)
                    res["source_rows_removed"] += d_cur.rowcount
                self._conn.commit()
            except Exception as e:
                self._conn.rollback()
                log.warning(f"Tier 1->2 compression failed: {e}")
        return processed

    def _compress_tier0_to_tier1(self, now: float, batch_size: int, res: dict) -> int:
        processed = 0
        with self._lock:
            try:
                self._conn.execute("BEGIN TRANSACTION")
                cur = self._conn.execute(
                    "SELECT id, ts, data, retention_class FROM transitions "
                    "WHERE ts < ? ORDER BY ts ASC LIMIT ?",
                    (now - 24 * 3600, int(batch_size))
                )
                rows = cur.fetchall()
                if not rows:
                    self._conn.commit()
                    return 0
                res["source_rows_examined"] += len(rows)
                buckets = {}
                deletable_ids = []
                for r in rows:
                    sid, ts_raw, data_str, rc = r
                    try:
                        ts = float(ts_raw)
                        payload = json.loads(data_str)
                    except Exception:
                        res["malformed_row_ids"].append(sid)
                        res["source_rows_skipped"] += 1
                        continue
                        
                    change = payload.get("change", {})
                    topic = change.get("path", "unknown")
                    val = change.get("new")
                    
                    t1_start = float(int(ts // 60) * 60)
                    t1_end = t1_start + 60.0
                    key = (t1_start, topic, rc)
                    
                    if key not in buckets:
                        buckets[key] = {
                            "tier": 1, "bstart": t1_start, "bend": t1_end, "topic": topic, "rc": rc,
                            "f_pay": val, "f_ts": ts, "l_pay": val, "l_ts": ts,
                            "agg": {}, "ev_c": 1, "src_min": sid, "src_max": sid, "src_c": 1
                        }
                    else:
                        b = buckets[key]
                        if ts < b["f_ts"]: b["f_ts"] = ts; b["f_pay"] = val
                        if ts > b["l_ts"]: b["l_ts"] = ts; b["l_pay"] = val
                        b["ev_c"] += 1; b["src_c"] += 1
                        if b["src_min"] is None or sid < b["src_min"]: b["src_min"] = sid
                        if b["src_max"] is None or sid > b["src_max"]: b["src_max"] = sid
                        
                    b = buckets[key]
                    if isinstance(val, dict):
                        for k, v in val.items():
                            if isinstance(v, (int, float)) and not isinstance(v, bool):
                                if k not in b["agg"]:
                                    b["agg"][k] = {"count": 1, "min": float(v), "max": float(v), "avg": float(v)}
                                else:
                                    bk = b["agg"][k]
                                    old_c = bk["count"]
                                    bk["count"] += 1
                                    if float(v) < bk["min"]: bk["min"] = float(v)
                                    if float(v) > bk["max"]: bk["max"] = float(v)
                                    bk["avg"] = (bk["avg"] * old_c + float(v)) / bk["count"]
                    elif isinstance(val, (int, float)) and not isinstance(val, bool):
                        k = "value"
                        if k not in b["agg"]:
                            b["agg"][k] = {"count": 1, "min": float(val), "max": float(val), "avg": float(val)}
                        else:
                            bk = b["agg"][k]
                            old_c = bk["count"]
                            bk["count"] += 1
                            if float(val) < bk["min"]: bk["min"] = float(val)
                            if float(val) > bk["max"]: bk["max"] = float(val)
                            bk["avg"] = (bk["avg"] * old_c + float(val)) / bk["count"]

                    deletable_ids.append(sid)
                    processed += 1
                    res["source_rows_processed"] += 1
                    res["tier0_to_tier1"] += 1

                self._upsert_summaries_locked(list(buckets.values()), res)
                if deletable_ids:
                    places = ",".join("?" for _ in deletable_ids)
                    d_cur = self._conn.execute(f"DELETE FROM transitions WHERE id IN ({places})", deletable_ids)
                    res["source_rows_removed"] += d_cur.rowcount
                self._conn.commit()
            except Exception as e:
                self._conn.rollback()
                log.warning(f"Tier 0->1 compression failed: {e}")
        return processed

    def _upsert_summaries_locked(self, buckets, res: dict):
        import time
        for b in buckets:
            cur = self._conn.execute(
                "SELECT id, first_payload_json, first_ts, last_payload_json, last_ts, "
                "aggregate_json, event_count, source_min_id, source_max_id, source_count "
                "FROM ledger_summaries WHERE tier=? AND bucket_start=? AND topic=? AND retention_class=?",
                (b["tier"], b["bstart"], b["topic"], b["rc"])
            )
            row = cur.fetchone()
            if not row:
                self._conn.execute(
                    "INSERT INTO ledger_summaries (tier, bucket_start, bucket_end, topic, retention_class, "
                    "first_payload_json, first_ts, last_payload_json, last_ts, aggregate_json, "
                    "event_count, source_min_id, source_max_id, source_count, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (b["tier"], b["bstart"], b["bend"], b["topic"], b["rc"], 
                     json.dumps(b["f_pay"]) if b["f_pay"] is not None else None, b["f_ts"],
                     json.dumps(b["l_pay"]) if b["l_pay"] is not None else None, b["l_ts"],
                     json.dumps(b["agg"]), b["ev_c"], b["src_min"], b["src_max"], b["src_c"], time.time())
                )
                res["summaries_created"] += 1
            else:
                sid, f_json, f_ts, l_json, l_ts, agg_json, ev_c, src_min, src_max, src_c = row
                old_f_pay = json.loads(f_json) if f_json else None
                old_l_pay = json.loads(l_json) if l_json else None
                old_agg = json.loads(agg_json) if agg_json else {}
                
                new_f_ts = f_ts; new_f_pay = old_f_pay
                if b["f_ts"] is not None and (f_ts is None or b["f_ts"] < f_ts):
                    new_f_ts = b["f_ts"]; new_f_pay = b["f_pay"]
                    
                new_l_ts = l_ts; new_l_pay = old_l_pay
                if b["l_ts"] is not None and (l_ts is None or b["l_ts"] > l_ts):
                    new_l_ts = b["l_ts"]; new_l_pay = b["l_pay"]
                    
                new_src_min = src_min
                if b["src_min"] is not None and (src_min is None or b["src_min"] < src_min):
                    new_src_min = b["src_min"]
                    
                new_src_max = src_max
                if b["src_max"] is not None and (src_max is None or b["src_max"] > src_max):
                    new_src_max = b["src_max"]
                    
                for k, v in b["agg"].items():
                    if k not in old_agg:
                        old_agg[k] = v.copy()
                    else:
                        bk = old_agg[k]
                        old_c = bk["count"]
                        bk["count"] += v["count"]
                        if v["min"] is not None and (bk["min"] is None or v["min"] < bk["min"]): bk["min"] = v["min"]
                        if v["max"] is not None and (bk["max"] is None or v["max"] > bk["max"]): bk["max"] = v["max"]
                        if bk["avg"] is not None and v["avg"] is not None and bk["count"] > 0:
                            bk["avg"] = (bk["avg"] * old_c + v["avg"] * v["count"]) / bk["count"]
                        elif bk["avg"] is None:
                            bk["avg"] = v["avg"]
                            
                self._conn.execute(
                    "UPDATE ledger_summaries SET first_payload_json=?, first_ts=?, last_payload_json=?, last_ts=?, "
                    "aggregate_json=?, event_count=?, source_min_id=?, source_max_id=?, source_count=? WHERE id=?",
                    (json.dumps(new_f_pay) if new_f_pay is not None else None, new_f_ts,
                     json.dumps(new_l_pay) if new_l_pay is not None else None, new_l_ts,
                     json.dumps(old_agg), ev_c + b["ev_c"], new_src_min, new_src_max, src_c + b["src_c"], sid)
                )
                res["summaries_updated"] += 1

    def recent(self, n: int = 500) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT data FROM transitions ORDER BY id DESC LIMIT ?", (int(n),)
            ).fetchall()
        out = [json.loads(r[0]) for r in rows]
        out.reverse()   # chronological order
        return out

    def recent_summaries(self, n: int = 500) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT tier, bucket_start, bucket_end, topic, retention_class, first_payload_json, last_payload_json, aggregate_json, event_count, source_min_id, source_max_id, source_count "
                "FROM ledger_summaries ORDER BY id DESC LIMIT ?", (int(n),)
            ).fetchall()
        out = []
        for r in rows:
            tier, bstart, bend, topic, rc, f_json, l_json, agg_json, ev_c, src_min, src_max, src_c = r
            out.append({
                "tier": tier, "bucket_start": bstart, "bucket_end": bend, "topic": topic, "retention_class": rc,
                "first_payload": json.loads(f_json) if f_json else None,
                "last_payload": json.loads(l_json) if l_json else None,
                "aggregate": json.loads(agg_json) if agg_json else {},
                "event_count": ev_c, "source_min_id": src_min, "source_max_id": src_max, "source_count": src_c
            })
        out.reverse()
        return out

    def query_history(
        self,
        start_time: float,
        end_time: float,
        topics: list[str] | None = None,
        retention_classes: list[str] | None = None,
        resolution: str = "auto",
        limit: int = 1000,
        cursor: str | None = None,
    ) -> dict:
        """BC4: Compaction-Aware Historical Query Interface."""
        from .history_models import Cursor, ResolutionMode, HistoricalRecord, HistoricalPage
        import time

        if not ResolutionMode.is_valid(resolution):
            raise ValueError(f"Invalid resolution: {resolution}")

        if not isinstance(start_time, (int, float)) or not isinstance(end_time, (int, float)):
            raise ValueError("start_time and end_time must be finite numeric values")
        
        start_time = float(start_time)
        end_time = float(end_time)

        if start_time >= end_time:
            raise ValueError("start_time must be strictly less than end_time")
            
        limit = max(1, min(10000, int(limit)))

        if topics is not None:
            if not isinstance(topics, list): raise ValueError("topics must be a list")
            if len(topics) > 100: raise ValueError("too many topics")
            topics = [str(t) for t in topics]
        else:
            topics = []

        if retention_classes is not None:
            if not isinstance(retention_classes, list): raise ValueError("retention_classes must be a list")
            if len(retention_classes) > 10: raise ValueError("too many retention_classes")
            retention_classes = list({str(rc).upper() for rc in retention_classes})
        else:
            retention_classes = []

        query_hash = Cursor.compute_hash(start_time, end_time, topics, retention_classes)

        if cursor is not None:
            c = Cursor.decode(cursor, expected_hash=query_hash, expected_res=resolution)
            as_of = c.as_of
        else:
            as_of = time.time()
            c = None

        t_tier1 = as_of - 24 * 3600
        t_tier2 = as_of - 7 * 24 * 3600

        segments = []
        if resolution == ResolutionMode.RAW:
            segments.append((0, start_time, end_time))
        elif resolution == ResolutionMode.MINUTE:
            segments.append((1, start_time, end_time))
        elif resolution == ResolutionMode.HOUR:
            segments.append((2, start_time, end_time))
        elif resolution == ResolutionMode.AUTO:
            if start_time < t_tier2:
                segments.append((2, start_time, min(t_tier2, end_time)))
            if start_time < t_tier1 and end_time > t_tier2:
                segments.append((1, max(start_time, t_tier2), min(t_tier1, end_time)))
            if end_time > t_tier1:
                segments.append((0, max(start_time, t_tier1), end_time))

        candidates = []
        warnings = []
        skipped_malformed = 0

        def get_cursor_condition(table_tier: int, table_kind: str, cur_obj, ts_col: str, id_col: str):
            if not cur_obj: return "", []
            conds = [f"{ts_col} > ?"]
            params = [cur_obj.last_start]
            tier_cmp = (table_tier > cur_obj.last_tier) - (table_tier < cur_obj.last_tier)
            kind_cmp = (table_kind > cur_obj.last_kind) - (table_kind < cur_obj.last_kind)
            if tier_cmp > 0:
                conds.append(f"{ts_col} = ?")
                params.append(cur_obj.last_start)
            elif tier_cmp == 0:
                if kind_cmp > 0:
                    conds.append(f"{ts_col} = ?")
                    params.append(cur_obj.last_start)
                elif kind_cmp == 0:
                    conds.append(f"({ts_col} = ? AND {id_col} > ?)")
                    params.extend([cur_obj.last_start, cur_obj.last_id])
            return " AND (" + " OR ".join(conds) + ")", params

        with self._lock:
            for pref_tier, s_start, s_end in segments:
                target_tiers = [pref_tier]
                if pref_tier > 0:
                    target_tiers.append(pref_tier - 1)
                if pref_tier == 2:
                    target_tiers.append(0)

                for t in target_tiers:
                    query_parts = []
                    params = []
                    
                    if t > 0:
                        query_parts.append("tier = ? AND bucket_end > ? AND bucket_start < ?")
                        params.extend([t, s_start, s_end])
                        if topics:
                            places = ",".join("?" for _ in topics)
                            query_parts.append(f"topic IN ({places})")
                            params.extend(topics)
                        if retention_classes:
                            places = ",".join("?" for _ in retention_classes)
                            query_parts.append(f"retention_class IN ({places})")
                            params.extend(retention_classes)
                            
                        cur_cond, cur_params = get_cursor_condition(t, "summary", c, "bucket_start", "id")
                        where = " AND ".join(query_parts) + cur_cond
                        sql = f"SELECT id, bucket_start, bucket_end, topic, retention_class, first_payload_json, last_payload_json, aggregate_json, event_count, source_min_id, source_max_id, source_count FROM ledger_summaries WHERE {where} ORDER BY bucket_start ASC, id ASC LIMIT ?"
                        params.extend(cur_params)
                        params.append(limit + 1)
                        
                        try:
                            rows = self._conn.execute(sql, params).fetchall()
                        except sqlite3.Error as e:
                            warnings.append(f"Tier {t} query error: {e}")
                            continue
                            
                        for r in rows:
                            sid, bstart, bend, topic, rc, f_json, l_json, agg_json, ev_c, src_min, src_max, src_c = r
                            try:
                                f_pay = json.loads(f_json) if f_json else None
                                l_pay = json.loads(l_json) if l_json else None
                                agg = json.loads(agg_json) if agg_json else {}
                            except Exception:
                                skipped_malformed += 1
                                continue
                            
                            rec = HistoricalRecord(
                                schema_version=1,
                                record_kind="summary",
                                tier=t,
                                id=sid,
                                topic=topic,
                                retention_class=rc,
                                start_timestamp=bstart,
                                end_timestamp=bend,
                                event_count=ev_c,
                                first_payload=f_pay,
                                last_payload=l_pay,
                                aggregate=agg,
                                source_min_id=src_min,
                                source_max_id=src_max,
                                source_count=src_c,
                                provenance=f"tier{t}_summary",
                                requested_resolution=resolution,
                                actual_resolution=ResolutionMode.HOUR if t == 2 else ResolutionMode.MINUTE,
                                fallback_reason="uncovered_fallback" if t < pref_tier else None,
                                cursor_ordering_key=(bstart, t, "summary", sid)
                            )
                            candidates.append(rec)
                            
                    else:
                        query_parts.append("ts >= ? AND ts < ?")
                        params.extend([s_start, s_end])
                        query_parts.append("ts <= ?")
                        params.append(as_of)
                        
                        if topics:
                            places = ",".join("?" for _ in topics)
                            query_parts.append(f"json_extract(data, '$.change.path') IN ({places})")
                            params.extend(topics)
                        if retention_classes:
                            places = ",".join("?" for _ in retention_classes)
                            query_parts.append(f"retention_class IN ({places})")
                            params.extend(retention_classes)
                            
                        cur_cond, cur_params = get_cursor_condition(0, "transition", c, "ts", "id")
                        where = " AND ".join(query_parts) + cur_cond
                        sql = f"SELECT id, ts, data, retention_class FROM transitions WHERE {where} ORDER BY ts ASC, id ASC LIMIT ?"
                        params.extend(cur_params)
                        params.append(limit + 1)
                        
                        try:
                            rows = self._conn.execute(sql, params).fetchall()
                        except sqlite3.Error as e:
                            warnings.append(f"Tier 0 query error: {e}")
                            continue
                            
                        for r in rows:
                            sid, ts_val, data_str, rc = r
                            try:
                                payload = json.loads(data_str)
                                change = payload.get("change", {})
                                topic = change.get("path", "unknown")
                            except Exception:
                                skipped_malformed += 1
                                continue
                                
                            rec = HistoricalRecord(
                                schema_version=1,
                                record_kind="transition",
                                tier=0,
                                id=sid,
                                topic=topic,
                                retention_class=rc,
                                start_timestamp=ts_val,
                                end_timestamp=ts_val,
                                event_count=1,
                                first_payload=payload,
                                last_payload=payload,
                                aggregate={},
                                source_min_id=sid,
                                source_max_id=sid,
                                source_count=1,
                                provenance="tier0_transition",
                                requested_resolution=resolution,
                                actual_resolution=ResolutionMode.RAW,
                                fallback_reason="uncovered_fallback" if 0 < pref_tier else None,
                                cursor_ordering_key=(ts_val, 0, "transition", sid)
                            )
                            candidates.append(rec)

        # Build coverage intervals mapping: (tier, topic, rc) -> list of (min_id, max_id)
        coverage_t2 = {}
        coverage_t1 = {}
        for rec in candidates:
            if rec.record_kind == "summary" and rec.source_min_id is not None and rec.source_max_id is not None:
                key = (rec.topic, rec.retention_class)
                if rec.tier == 2:
                    coverage_t2.setdefault(key, []).append((rec.source_min_id, rec.source_max_id))
                elif rec.tier == 1:
                    coverage_t1.setdefault(key, []).append((rec.source_min_id, rec.source_max_id))
                
        filtered_candidates = []
        for rec in candidates:
            covered = False
            if rec.record_kind == "transition":
                key = (rec.topic, rec.retention_class)
                # Tier 0 can be covered by Tier 2 or Tier 1
                for c_min, c_max in coverage_t2.get(key, []) + coverage_t1.get(key, []):
                    if c_min <= rec.id <= c_max:
                        covered = True
                        break
            elif rec.record_kind == "summary" and rec.tier == 1:
                key = (rec.topic, rec.retention_class)
                # Tier 1 can only be covered by Tier 2
                if rec.source_min_id is not None and rec.source_max_id is not None:
                    for c_min, c_max in coverage_t2.get(key, []):
                        if c_min <= rec.source_min_id and rec.source_max_id <= c_max:
                            covered = True
                            break
            
            if not covered:
                filtered_candidates.append(rec)
                
        filtered_candidates.sort(key=lambda x: x.cursor_ordering_key)
        final_records = filtered_candidates[:limit]
        
        next_cursor_str = None
        if len(filtered_candidates) > limit:
            last = final_records[-1]
            nc = Cursor(
                v=1,
                as_of=as_of,
                last_start=last.start_timestamp,
                last_tier=last.tier,
                last_kind=last.record_kind,
                last_id=last.id,
                resolution=resolution,
                query_hash=query_hash
            )
            next_cursor_str = nc.encode()
            
        return HistoricalPage(
            records=[r.to_dict() for r in final_records],
            next_cursor=next_cursor_str,
            as_of=as_of,
            skipped_malformed_count=skipped_malformed,
            warnings=warnings
        ).to_dict()

    def count(self) -> int:
        with self._lock:
            return self._conn.execute("SELECT COUNT(*) FROM transitions").fetchone()[0]

    def close(self) -> None:
        with self._lock:
            try:
                self._conn.close()
            except Exception:
                pass

    def diagnostics(self) -> dict:
        """BC6: Metadata queries providing O(1) bounds on database size."""
        with self._lock:
            # O(1) index queries on primary keys (using max/min to avoid O(N) COUNT scans)
            t0_cur = self._conn.execute("SELECT MAX(id), MIN(id) FROM transitions")
            t0_max, t0_min = t0_cur.fetchone()
            t0_span = (t0_max - t0_min + 1) if (t0_max is not None and t0_min is not None) else 0

            t1_cur = self._conn.execute("SELECT MAX(id), MIN(id) FROM ledger_summaries WHERE tier = 1")
            t1_max, t1_min = t1_cur.fetchone()
            t1_span = (t1_max - t1_min + 1) if (t1_max is not None and t1_min is not None) else 0

            t2_cur = self._conn.execute("SELECT MAX(id), MIN(id) FROM ledger_summaries WHERE tier = 2")
            t2_max, t2_min = t2_cur.fetchone()
            t2_span = (t2_max - t2_min + 1) if (t2_max is not None and t2_min is not None) else 0

            sum_cur = self._conn.execute("SELECT MAX(id) FROM ledger_summaries")
            sum_max = sum_cur.fetchone()[0]

            return {
                "transition_high_water_id": t0_max or 0,
                "summary_high_water_id": sum_max or 0,
                "approximate_tier0_id_span": t0_span,
                "approximate_tier1_id_span": t1_span,
                "approximate_tier2_id_span": t2_span,
                "exact_row_counts": "unavailable_without_full_scan",
                "compression_ratio": "unavailable_without_full_scan",
                "cap_limit": self.cap,
                "db_path": self.db_path
            }
