"""compaction_job.py - Scheduled autonomous background compaction (Phase B · BC3).

Runs BC1 class-based expiry and BC2 tiered snapshot compression continuously via the
central Scheduler. Built with bounded batching, overlap prevention, exception isolation,
and backpressure awareness.
"""
from __future__ import annotations

import threading
import time
import traceback
from dataclasses import dataclass, asdict
from typing import Optional

from config.logger import get_logger
from shared_core.scheduler import Scheduler
from shared_core import publish_safe
from shared_core.event_bus.topics import (
    MAINTENANCE_COMPACTION_STARTED,
    MAINTENANCE_COMPACTION_COMPLETED,
    MAINTENANCE_COMPACTION_SKIPPED,
    MAINTENANCE_COMPACTION_FAILED,
)

log = get_logger("state.compaction")

# ── Central Configuration ──────────────────────────────────────────────────
DEFAULT_COMPACTION_INTERVAL_SECONDS = 300.0
DEFAULT_EXPIRY_BATCH_SIZE = 500
DEFAULT_COMPRESSION_BATCH_SIZE = 500
DEFAULT_COMPACTION_MAX_DURATION_SECONDS = 5.0


@dataclass
class CompactionResult:
    schema_version: int = 1
    cycle_id: str = ""
    started_at: float = 0.0
    completed_at: float = 0.0
    duration_seconds: float = 0.0
    expired_rows: int = 0
    compression_source_rows_examined: int = 0
    source_rows_processed: int = 0
    summaries_created: int = 0
    summaries_updated: int = 0
    source_rows_removed: int = 0
    malformed_rows_skipped: int = 0
    tier_transitions: int = 0
    skipped: bool = False
    skip_reason: Optional[str] = None
    overlap_skip_count: int = 0
    expiry_success: bool = False
    compression_success: bool = False
    partial_success: bool = False
    success: bool = False
    error_stage: Optional[str] = None
    error_type: Optional[str] = None
    error_message: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


class CompactionJob:
    """Bounded, backpressure-aware scheduled task for state ledger compaction."""

    def __init__(
        self,
        store,  # LedgerStore
        bus,
        scheduler: Scheduler,
        interval: float = DEFAULT_COMPACTION_INTERVAL_SECONDS,
        expiry_batch: int = DEFAULT_EXPIRY_BATCH_SIZE,
        compress_batch: int = DEFAULT_COMPRESSION_BATCH_SIZE,
        max_duration: float = DEFAULT_COMPACTION_MAX_DURATION_SECONDS,
    ):
        self.store = store
        self.bus = bus
        self.scheduler = scheduler
        
        try:
            self.interval = max(1.0, float(interval))
        except (ValueError, TypeError):
            self.interval = DEFAULT_COMPACTION_INTERVAL_SECONDS
            
        try:
            self.expiry_batch = max(1, int(expiry_batch))
        except (ValueError, TypeError):
            self.expiry_batch = DEFAULT_EXPIRY_BATCH_SIZE
            
        try:
            self.compress_batch = max(1, int(compress_batch))
        except (ValueError, TypeError):
            self.compress_batch = DEFAULT_COMPRESSION_BATCH_SIZE
            
        try:
            self.max_duration = max(0.1, float(max_duration))
        except (ValueError, TypeError):
            self.max_duration = DEFAULT_COMPACTION_MAX_DURATION_SECONDS
            
        self._guard = threading.Lock()
        self._overlap_count = 0

    def run_cycle(self) -> None:
        """One scheduled maintenance cycle. Guarantees non-overlapping, bounded execution."""
        if not self._guard.acquire(blocking=False):
            # Overlap skip
            self._overlap_count += 1
            log.debug("Compaction cycle skipped (overlap).")
            return

        try:
            self._execute_cycle()
        finally:
            self._guard.release()

    def _execute_cycle(self) -> None:
        start_mono = time.monotonic()
        start_wall = time.time()
        
        # Check backpressure diagnostics
        diag = {}
        try:
            diag = self.scheduler.diagnostics()
        except Exception as exc:
            log.warning(f"Failed to read scheduler diagnostics: {exc}")
            diag = {"overload": False}  # fall back to allowing it if we can't read it? Wait, prompt says: "If diagnostics cannot be read safely: skip the cycle conservatively, record `diagnostics_unavailable`"
            self._publish_skipped("diagnostics_unavailable", start_wall)
            return
            
        # The true overload key is 'overload' in scheduler diagnostics (from our inspection of scheduler.py)
        if diag.get("overload", False):
            self._publish_skipped("scheduler_overload", start_wall)
            return

        cycle_id = f"cmp-{int(start_wall * 1000)}"
        res = CompactionResult(
            cycle_id=cycle_id,
            started_at=start_wall,
            overlap_skip_count=self._overlap_count
        )
        
        publish_safe(MAINTENANCE_COMPACTION_STARTED, {"cycle_id": cycle_id}, source="compaction_job", correlation_id=cycle_id)
        
        # Stage 1: Expiry
        res.error_stage = "expiry"
        try:
            res.expired_rows = self.store.expire(start_wall, batch_size=self.expiry_batch)
            res.expiry_success = True
        except Exception as exc:
            log.error(f"Compaction expiry error: {exc}")
            res.error_type = type(exc).__name__
            # Bounded error message
            res.error_message = str(exc)[:200]
            self._finalize_and_publish(res, start_mono)
            return

        # Check deadline before compression
        elapsed = time.monotonic() - start_mono
        if elapsed >= self.max_duration:
            res.error_stage = "deadline"
            res.skip_reason = "budget_exhausted"
            res.partial_success = True
            self._finalize_and_publish(res, start_mono)
            return

        # Stage 2: Compression
        res.error_stage = "compression"
        try:
            c_res = self.store.compress(start_wall, batch_size=self.compress_batch)
            res.compression_source_rows_examined = c_res.get("source_rows_examined", 0)
            res.source_rows_processed = c_res.get("source_rows_processed", 0)
            res.summaries_created = c_res.get("summaries_created", 0)
            res.summaries_updated = c_res.get("summaries_updated", 0)
            res.source_rows_removed = c_res.get("source_rows_removed", 0)
            res.malformed_rows_skipped = len(c_res.get("malformed_row_ids", []))
            res.tier_transitions = c_res.get("tier0_to_tier1", 0) + c_res.get("tier1_to_tier2", 0)
            res.compression_success = True
        except Exception as exc:
            log.error(f"Compaction compression error: {exc}")
            res.error_type = type(exc).__name__
            res.error_message = str(exc)[:200]
            res.partial_success = res.expiry_success
            self._finalize_and_publish(res, start_mono)
            return

        res.error_stage = None
        res.success = True
        self._finalize_and_publish(res, start_mono)

    def _publish_skipped(self, reason: str, start_wall: float) -> None:
        log.debug(f"Compaction cycle skipped: {reason}")
        res = CompactionResult(
            cycle_id=f"cmp-{int(start_wall * 1000)}",
            started_at=start_wall,
            completed_at=time.time(),
            skipped=True,
            skip_reason=reason,
            overlap_skip_count=self._overlap_count
        )
        publish_safe(MAINTENANCE_COMPACTION_SKIPPED, res.to_dict(), source="compaction_job", correlation_id=res.cycle_id)

    def _finalize_and_publish(self, res: CompactionResult, start_mono: float) -> None:
        res.completed_at = time.time()
        res.duration_seconds = time.monotonic() - start_mono
        
        if res.success:
            publish_safe(MAINTENANCE_COMPACTION_COMPLETED, res.to_dict(), source="compaction_job", correlation_id=res.cycle_id)
        elif res.partial_success or res.error_type is not None:
            publish_safe(MAINTENANCE_COMPACTION_FAILED, res.to_dict(), source="compaction_job", correlation_id=res.cycle_id)
