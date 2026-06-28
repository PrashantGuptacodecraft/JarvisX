"""scheduler.py - central multi-rate task scheduler (Phase B · B5).

Replaces fragmented polling loops with a unified drift-free scheduler. Tasks run concurrently
on a bounded thread pool; one task failure never stops the scheduler (exception isolation).

Backpressure/overload architecture (B12 hooks, not fully implemented):
  - Bounded task queue (never unbounded growth).
  - Overload policy can defer/skip LOW_PRIORITY tasks when queue depth exceeds threshold.
  - Coalescing interface: a future coalescer can collapse N same-key events into 1 aggregated.
  - Queue size monitoring hooks for diagnostics (Phase C/D integration).

Timing behavior:
  - Uses time.monotonic() (drift-free, immune to wall-clock jumps).
  - Missed-tick detection: if the loop falls behind, it realigns to the next valid interval
    boundary instead of executing stale runs.
  - High-precision timing via adaptive sleep + busy-wait within the final 5ms.
"""
from __future__ import annotations

import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Callable, Optional

from config.logger import get_logger

from .task import Priority, ScheduledTask

log = get_logger("scheduler")

# Backpressure policy constants (B12 hooks; overload logic pending).
DEFAULT_QUEUE_CAP = 500
OVERLOAD_THRESHOLD = 0.8  # queue 80% full triggers policy
LOW_PRIORITY_DEFER = (Priority.BACKGROUND, Priority.LOGGING)

# Continuity snapshot schema (forward-compat: validate + migrate on restore).
SCHEDULER_SNAPSHOT_SCHEMA_VERSION = 1
# Migration seam: {from_version: callable(snapshot)->snapshot}. Empty until a schema change lands.
_SNAPSHOT_MIGRATIONS: dict = {}


class Scheduler:
    def __init__(self, max_workers: int = 8, queue_cap: int = DEFAULT_QUEUE_CAP):
        self._tasks: dict[str, ScheduledTask] = {}
        self._lock = threading.RLock()
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="sched-")
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._pending: dict[str, Future] = {}   # task_id -> in-flight Future
        self._queue_cap = queue_cap
        self._tick_count = 0
        self._overload_defers = 0
        # B12 attachment seams (no-op until a backpressure layer attaches).
        self._coalescer = None
        self._coalesce_handler = None
        self._queue_monitors: list = []
        # ContinuityManager integration: saved task-state re-applied on (re)registration.
        self._restored_state: dict = {}

    # ── lifecycle ────────────────────────────────────────────────────────────
    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, name="scheduler-loop", daemon=True)
        self._thread.start()
        log.info("Scheduler started.")

    def stop(self, wait: bool = True) -> None:
        self._running = False
        if wait and self._thread:
            self._thread.join(timeout=2.0)
        self._pool.shutdown(wait=wait, cancel_futures=not wait)

    # ── register / unregister / pause / resume (dynamic control) ─────────────
    def register_task(
        self,
        task_id: str,
        name: str,
        fn: Callable[[], None],
        interval: float,
        priority: Priority = Priority.BACKGROUND,
        source_module: str = "unknown",
        parent_task_id: Optional[str] = None,
        tags: tuple = (),
    ) -> ScheduledTask:
        """Register a new task. Returns the ScheduledTask handle."""
        now = time.monotonic()
        task = ScheduledTask(
            id=task_id,
            name=name,
            fn=fn,
            interval=float(interval),
            priority=priority,
            next_run=now + interval,
            source_module=source_module,
            parent_task_id=parent_task_id,
            tags=tags,
        )
        with self._lock:
            self._tasks[task_id] = task
            # Re-apply any continuity-restored state for this task_id (paused/metrics).
            saved = self._restored_state.get(task_id)
            if saved:
                self._apply_saved_state(task, saved)
        log.debug(f"[scheduler] registered '{name}' ({interval}s, P{int(priority)})")
        return task

    def unregister_task(self, task_id: str) -> bool:
        with self._lock:
            task = self._tasks.pop(task_id, None)
            if task and task_id in self._pending:
                fut = self._pending.pop(task_id)
                fut.cancel()
        return task is not None

    def pause_task(self, task_id: str) -> bool:
        with self._lock:
            task = self._tasks.get(task_id)
            if task:
                task.paused = True
                return True
        return False

    def resume_task(self, task_id: str) -> bool:
        with self._lock:
            task = self._tasks.get(task_id)
            if task:
                task.paused = False
                return True
        return False

    # ── core dispatch loop ───────────────────────────────────────────────────
    def _loop(self) -> None:
        while self._running:
            tick_start = time.monotonic()
            self._tick_count += 1
            due = self._collect_due_tasks(tick_start)
            self._dispatch_batch(due, tick_start)
            self._run_attachments()
            self._sleep_adaptive(0.02)  # 20ms tick granularity

    def _run_attachments(self) -> None:
        """Invoke B12 hook attachments (queue monitors + coalescer flush). No-op if none."""
        if self._queue_monitors:
            qs = self.queue_size()
            for cb in list(self._queue_monitors):
                try:
                    cb(qs)
                except Exception as exc:
                    log.debug(f"[scheduler] queue monitor error: {exc}")
        if self._coalescer is not None and self._coalesce_handler is not None:
            try:
                aggregated = self._coalescer.flush()
                if aggregated:
                    self._coalesce_handler(aggregated)
            except Exception as exc:
                log.debug(f"[scheduler] coalescer flush error: {exc}")

    # ── B12 attachment hooks (architecture seams; logic deferred) ────────────
    def attach_coalescer(self, coalescer, handler=None) -> None:
        """Attach a Coalescer + a handler(aggregated_list) invoked each tick after flush."""
        self._coalescer = coalescer
        self._coalesce_handler = handler

    def register_queue_monitor(self, callback) -> None:
        """Register a callback(queue_size:int) invoked each tick (for diagnostics)."""
        self._queue_monitors.append(callback)

    def _collect_due_tasks(self, now: float) -> list[ScheduledTask]:
        due = []
        with self._lock:
            for task in self._tasks.values():
                if task.paused or task.next_run > now:
                    continue
                # Overlap guard: skip if prior run still in flight.
                if task.running:
                    task.overlap_skips += 1
                    continue
                due.append(task)
        due.sort(key=lambda t: (t.priority, t.next_run))  # higher priority first
        return due

    def _dispatch_batch(self, due: list[ScheduledTask], now: float) -> None:
        # B12 hook: bounded queue + overload policy (defer low-priority if near cap).
        queue_size = len(self._pending)
        overload = (queue_size >= self._queue_cap * OVERLOAD_THRESHOLD)
        for task in due:
            if queue_size >= self._queue_cap:
                task.deferred += 1
                self._overload_defers += 1
                continue
            if overload and task.priority in LOW_PRIORITY_DEFER:
                task.deferred += 1
                self._overload_defers += 1
                continue
            # Realign next_run (missed-tick recovery: skip to next valid boundary).
            missed = max(0, int((now - task.next_run) / task.interval))
            if missed > 0:
                task.missed_ticks += missed
            task.next_run += (missed + 1) * task.interval
            task.running = True
            fut = self._pool.submit(self._execute, task, now)
            with self._lock:
                self._pending[task.id] = fut
            queue_size += 1

    def _execute(self, task: ScheduledTask, dispatch_time: float) -> None:
        """Run a single task with exception isolation + latency tracking."""
        start = time.monotonic()
        error = None
        try:
            task.fn()
        except Exception as exc:
            error = str(exc)
            log.error(f"[scheduler] task '{task.name}' error: {exc}")
        latency = time.monotonic() - start
        task.record_completion(latency, error)
        with self._lock:
            self._pending.pop(task.id, None)

    def _sleep_adaptive(self, target: float) -> None:
        """High-precision sleep: coarse sleep + busy-wait for final 5ms."""
        deadline = time.monotonic() + target
        remain = deadline - time.monotonic()
        if remain > 0.005:
            time.sleep(remain - 0.005)
        while time.monotonic() < deadline:
            pass

    # ── metrics / queue monitoring hooks (B12 diagnostics integration) ───────
    def health(self) -> dict:
        with self._lock:
            tasks = list(self._tasks.values())
            queue_size = len(self._pending)
        return {
            "running": self._running,
            "tick_count": self._tick_count,
            "registered_tasks": len(tasks),
            "queue_size": queue_size,
            "queue_cap": self._queue_cap,
            "overload": queue_size >= self._queue_cap * OVERLOAD_THRESHOLD,
            "overload_defers_total": self._overload_defers,
            "tasks": [t.metrics() for t in tasks],
        }

    def queue_size(self) -> int:
        """B12 hook: current pending task count for external monitors."""
        with self._lock:
            return len(self._pending)

    # ── ContinuityManager integration (snapshot / restore) ───────────────────
    def snapshot(self) -> dict:
        """JSON-serializable scheduler runtime state (metadata + health).

        Persists task metadata, intervals, priorities, paused state, health metrics, AND
        deterministic timing state (seconds remaining until next run) so restart preserves
        temporal continuity, not just metadata.
        Does NOT persist callables, threads, in-flight futures, or raw monotonic values
        (monotonic is meaningless across processes; wall-clock `remaining` is the safe equivalent).
        """
        now_m = time.monotonic()
        with self._lock:
            tasks = [{
                "task_id": t.id,
                "name": t.name,
                "interval": t.interval,
                "priority": int(t.priority),
                "paused": t.paused,
                "source_module": t.source_module,
                "parent_task_id": t.parent_task_id,
                "tags": list(t.tags),
                "run_count": t.run_count,
                "error_count": t.error_count,
                "missed_ticks": t.missed_ticks,
                "overlap_skips": t.overlap_skips,
                "deferred": t.deferred,
                "total_latency": t.total_latency,
                "last_error": t.last_error,
                # timeline state: seconds until next scheduled run (not raw monotonic).
                "remaining": max(0.0, t.next_run - now_m),
            } for t in self._tasks.values()]
            return {
                "schema_version": SCHEDULER_SNAPSHOT_SCHEMA_VERSION,
                "tasks": tasks,
                "tick_count": self._tick_count,
                "overload_defers_total": self._overload_defers,
                "saved_wall": time.time(),   # wall-clock anchor for elapsed-since-save math
            }

    def restore(self, snapshot: dict) -> int:
        """Restore scheduler runtime state safely. Returns count of tasks state was applied to.

        Saved task-state is also stashed so tasks registered AFTER restore (the normal boot
        order) still pick up their paused-state/metrics. No threads or callables are touched.
        """
        if not isinstance(snapshot, dict):
            return 0
        # Schema-version validation + migration seam (forward compatibility).
        version = snapshot.get("schema_version", 0)
        if version != SCHEDULER_SNAPSHOT_SCHEMA_VERSION:
            snapshot = self._migrate_snapshot(snapshot, version)
            if snapshot is None:
                return 0   # unsupported/newer schema → skip restore rather than corrupt state
        saved = {t.get("task_id"): t for t in snapshot.get("tasks", []) if t.get("task_id")}
        # Deterministic timing recovery: convert saved "remaining" into an absolute wall
        # deadline, accounting for time the process was down (elapsed since save).
        saved_wall = snapshot.get("saved_wall")
        elapsed_down = max(0.0, time.time() - saved_wall) if isinstance(saved_wall, (int, float)) else 0.0
        for st in saved.values():
            rem = st.get("remaining")
            if isinstance(rem, (int, float)):
                rem_now = max(0.0, rem - elapsed_down)   # subtract downtime → resume, not restart
                st["_wall_deadline"] = time.time() + rem_now
        applied = 0
        with self._lock:
            self._restored_state = saved
            self._tick_count = max(self._tick_count, int(snapshot.get("tick_count", 0) or 0))
            self._overload_defers = max(
                self._overload_defers, int(snapshot.get("overload_defers_total", 0) or 0))
            for tid, st in saved.items():
                task = self._tasks.get(tid)
                if task is not None:
                    self._apply_saved_state(task, st)
                    applied += 1
        return applied

    def _migrate_snapshot(self, snapshot: dict, from_version: int):
        """Migrate an older snapshot up to the current schema. Returns migrated dict, or None
        if the snapshot is from a NEWER, unsupported schema (skip rather than corrupt)."""
        if from_version > SCHEDULER_SNAPSHOT_SCHEMA_VERSION:
            log.warning(
                f"[scheduler] snapshot schema v{from_version} is newer than supported "
                f"v{SCHEDULER_SNAPSHOT_SCHEMA_VERSION}; skipping restore.")
            return None
        data = dict(snapshot)
        cur = from_version
        while cur < SCHEDULER_SNAPSHOT_SCHEMA_VERSION:
            migrate = _SNAPSHOT_MIGRATIONS.get(cur)
            if migrate is None:
                # No registered migration (e.g. legacy v0): best-effort: newer fields take
                # defaults, older fields are read as-is. Stop and accept what we have.
                log.info(f"[scheduler] no migration from schema v{cur}; best-effort restore.")
                break
            data = migrate(data)
            cur += 1
        data["schema_version"] = SCHEDULER_SNAPSHOT_SCHEMA_VERSION
        return data

    def _apply_saved_state(self, task: ScheduledTask, st: dict) -> None:
        """Apply persisted state to a task (paused + metrics + timeline). Never fn/threads."""
        task.paused = bool(st.get("paused", task.paused))
        for f in ("run_count", "error_count", "missed_ticks", "overlap_skips", "deferred"):
            v = st.get(f)
            if isinstance(v, int):
                setattr(task, f, v)
        tl = st.get("total_latency")
        if isinstance(tl, (int, float)):
            task.total_latency = float(tl)
        if st.get("last_error") is not None:
            task.last_error = st.get("last_error")
        # Deterministic timing recovery: resume with remaining interval, not a fresh one.
        wd = st.get("_wall_deadline")
        if isinstance(wd, (int, float)):
            task.next_run = time.monotonic() + max(0.0, wd - time.time())
