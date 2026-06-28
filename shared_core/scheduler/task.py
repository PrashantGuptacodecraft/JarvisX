"""task.py - scheduled task model + priority tiers (Phase B · B5).

A ScheduledTask carries its config (interval, priority) and its live metrics (latency, run
counts, missed ticks). All timing uses time.monotonic() (drift-free, immune to wall-clock jumps).
"""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Callable, Optional


class Priority(IntEnum):
    """Lower number = higher priority (dispatched first within a tick)."""
    CRITICAL = 1     # critical system tasks
    USER = 2         # user-interaction tasks
    BACKGROUND = 3   # background monitoring
    LOGGING = 4      # logging / maintenance


@dataclass
class ScheduledTask:
    id: str
    name: str
    fn: Callable[[], None]
    interval: float                 # seconds (supports sub-second)
    priority: Priority
    next_run: float                 # monotonic deadline
    paused: bool = False
    running: bool = False

    # ── identity + causal-trace hooks (structural only; engine deferred to Phase C/D) ──
    source_module: str = "unknown"        # who registered the task
    parent_task_id: Optional[str] = None  # optional causal parent (failure ancestry / chaining)
    tags: tuple = ()                      # optional metadata for correlation / attribution

    # ── metrics ──────────────────────────────────────────────────────────────
    run_count: int = 0
    error_count: int = 0
    missed_ticks: int = 0           # intervals skipped because the loop fell behind
    overlap_skips: int = 0          # runs skipped because the prior run was still in flight
    deferred: int = 0               # runs deferred by overload/backpressure policy (B12 hook)
    last_latency: float = 0.0       # seconds
    total_latency: float = 0.0
    last_run_ts: Optional[float] = None   # wall-clock of last completion
    last_error: Optional[str] = None
    history: deque = field(default_factory=lambda: deque(maxlen=50))   # recent latencies

    @property
    def avg_latency(self) -> float:
        return (self.total_latency / self.run_count) if self.run_count else 0.0

    def record_completion(self, latency: float, error: Optional[str]) -> None:
        self.running = False
        self.run_count += 1
        self.last_latency = latency
        self.total_latency += latency
        self.last_run_ts = time.time()
        self.history.append(latency)
        if error is not None:
            self.error_count += 1
            self.last_error = error

    def metrics(self) -> dict:
        return {
            "task_id": self.id,
            "name": self.name,
            "source_module": self.source_module,
            "parent_task_id": self.parent_task_id,
            "tags": list(self.tags),
            "priority": int(self.priority),
            "interval": self.interval,
            "paused": self.paused,
            "running": self.running,
            "run_count": self.run_count,
            "error_count": self.error_count,
            "missed_ticks": self.missed_ticks,
            "overlap_skips": self.overlap_skips,
            "deferred": self.deferred,
            "last_latency_ms": round(self.last_latency * 1000, 3),
            "avg_latency_ms": round(self.avg_latency * 1000, 3),
            "last_error": self.last_error,
        }
