# PROJECT STATE — JARVISX (resume anchor)

> Single-glance state for resuming work. Authoritative details live in `omega_context/`.
> Last updated: 2026-07-22 (BC6 locked).

## Model
Dual-brain machine-intelligence OS. **JARVIS MODE** = act on world (existing repo + all future
external features). **OMEGA MODE** = internal cognition (**FROZEN** until JARVIS ≥ its milestone gate).
Shared core underneath both. Highest law: `omega_context/IMPLEMENTATION_CONSTITUTION.md`
(additive only, never break legacy boot, no deleting old code, test-gated, Design→Implement→Test→Validate→Lock).

## Progress (capability milestones, not %)
Authoritative tracker: `omega_context/CAPABILITY_MILESTONES.md` — **95 milestones** across A–F.

- **Phase A — Event Bus: COMPLETE** (A1–A10 locked). `shared_core/event_bus/`.
- **Phase B — State Manager + World-State: COMPLETE 30/30.**
  - Locked (28): B1-B6, B9-B14, BL1-BL10, BC1-BC6.
  - Deferred (2, audited valid — `DEPENDENCY_AUDIT.md`): B7 (SUPPORTING), B8 (OPTIONAL).
- **Phase C — Memory Engine + Knowledge Graph: IN PROGRESS (C1–C8 COMPLETE/LOCKED)**
- Phases D, E, F: PENDING.

## Tests
**217 passed, 0 failed.** Suites include Phase A, Phase B, and Phase C suites (e.g. `test_memory_engine_c8.py`).

## Shipped infrastructure (all additive)
- `shared_core/event_bus/` — thread-safe pub/sub, SYNC/ASYNC, backpressure, coalescing.
- `shared_core/state_manager/` — WorldState + typed sub-states, StateManager, History Ledger
  (`ledger.py`/`ledger_store.py`), OS sampler, ContinuityManager (crash-safe restore).
- `shared_core/scheduler/` — central multi-rate Scheduler (4-tier priority, drift-free, missed-tick
  recovery, exception isolation, backpressure/overload, coalescer hooks, snapshot/restore + timing
  recovery + schema versioning, `diagnostics()`).
- `shared_core/telemetry/` — continuous CPU/RAM/Disk/GPU collectors + watchdog filesystem watcher,
  run as Scheduler tasks; publishes `perception.system.*` + `perception.filesystem.change`.
- `main.py` — additive wiring: bus + event_logger, StateManager + History Ledger, central Scheduler
  (OS sampler migrated onto it, legacy fallback), TelemetryEngine, ContinuityManager (world_state +
  brain + scheduler providers; restore-on-boot + autosave + atexit). Legacy boot unchanged.

## Next action
Begin Phase C (`shared_core/memory/`). Stop after each checkpoint.
