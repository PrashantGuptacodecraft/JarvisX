import base64
import hashlib
import json
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Any


class ResolutionMode:
    RAW = "raw"
    MINUTE = "minute"
    HOUR = "hour"
    AUTO = "auto"
    
    @classmethod
    def is_valid(cls, mode: str) -> bool:
        return mode in (cls.RAW, cls.MINUTE, cls.HOUR, cls.AUTO)


@dataclass
class Cursor:
    v: int
    as_of: float
    last_start: float
    last_tier: int
    last_kind: str
    last_id: int
    resolution: str
    query_hash: str

    def encode(self) -> str:
        data = {
            "v": self.v,
            "as_of": self.as_of,
            "last_start": self.last_start,
            "last_tier": self.last_tier,
            "last_kind": self.last_kind,
            "last_id": self.last_id,
            "resolution": self.resolution,
            "query_hash": self.query_hash
        }
        json_bytes = json.dumps(data, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(json_bytes).decode("ascii")

    @classmethod
    def decode(cls, cursor_str: str, expected_hash: str, expected_res: str) -> "Cursor":
        if len(cursor_str) > 1024:
            raise ValueError("Cursor exceeds maximum size.")
        try:
            json_bytes = base64.urlsafe_b64decode(cursor_str.encode("ascii"))
            data = json.loads(json_bytes.decode("utf-8"))
        except Exception:
            raise ValueError("Malformed cursor payload.")
            
        if not isinstance(data, dict):
            raise ValueError("Malformed cursor payload.")
            
        if data.get("v") != 1:
            raise ValueError("Unsupported cursor version.")
            
        if data.get("query_hash") != expected_hash:
            raise ValueError("Cursor fingerprint does not match current query.")
            
        if data.get("resolution") != expected_res:
            raise ValueError("Cursor resolution does not match requested resolution.")
            
        return cls(
            v=data["v"],
            as_of=float(data["as_of"]),
            last_start=float(data["last_start"]),
            last_tier=int(data["last_tier"]),
            last_kind=str(data["last_kind"]),
            last_id=int(data["last_id"]),
            resolution=str(data["resolution"]),
            query_hash=str(data["query_hash"])
        )

    @staticmethod
    def compute_hash(start_time: float, end_time: float, topics: Optional[List[str]], retention_classes: Optional[List[str]]) -> str:
        s = f"{start_time}|{end_time}|{sorted(topics) if topics else 'None'}|{sorted(retention_classes) if retention_classes else 'None'}"
        return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


@dataclass
class HistoricalRecord:
    schema_version: int
    record_kind: str  # "transition" or "summary"
    tier: int
    id: int
    topic: str
    retention_class: str
    start_timestamp: float
    end_timestamp: float
    event_count: int
    first_payload: Optional[dict]
    last_payload: Optional[dict]
    aggregate: dict
    source_min_id: Optional[int]
    source_max_id: Optional[int]
    source_count: int
    provenance: str
    
    # Query context
    requested_resolution: str
    actual_resolution: str
    fallback_reason: Optional[str]
    cursor_ordering_key: tuple
    
    # Quality
    malformed: bool = False
    malformed_reason: Optional[str] = None
    quality_flags: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["cursor_ordering_key"] = list(self.cursor_ordering_key)
        return d


@dataclass
class HistoricalPage:
    records: List[dict]  # We store as dicts so the whole page is JSON-ready
    next_cursor: Optional[str]
    as_of: float
    skipped_malformed_count: int
    warnings: List[str]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class StateDiagnostics:
    schema_version: int
    captured_at: float
    health: str

    state: dict
    ledger: dict
    compaction: dict
    continuity: dict
    scheduler: dict

    warnings: List[str]

    def to_dict(self) -> dict:
        return asdict(self)
