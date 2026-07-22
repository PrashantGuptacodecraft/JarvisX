# STATE COMPACTION POLICY (ARCHITECTURE SPEC — implementation deferred)

> Added 2026-06-29. Architectural requirement only — **no implementation yet**. Must be in place
> before later phases expand state size (Phase C memory must inherit COMPRESSED history, not the
> raw stream). Tracked by milestones **BC1–BC6** in `CAPABILITY_MILESTONES.md`.
>
> Context: today the History Ledger (`ledger_store.py`) bounds growth only by a flat row cap
> (BL5). This policy supersedes that with **class-based retention** + **tiered time compression**,
> and adds growth diagnostics. It builds on existing infra (EventBus, History Ledger, Scheduler,
> ContinuityManager) — additive, no redesign.

## 1. Event Classification + Retention (BC1)
Every recorded transition/event is tagged with a retention class:

| Class | Examples | Retention (TTL) |
|---|---|---|
| **EPHEMERAL** (high-frequency) | mouse movement, rapid active-window flips, transient process/CPU spikes | **6 hours** |
| **SIGNIFICANT** (important) | task execution, scheduler failures, command execution, tool invocation | **30 days** |
| **DEFAULT** (unclassified) | anything not matched above | 7 days (sensible bound) |

- Classification is a pure function `classify(topic, payload) -> RetentionClass`.
- Expiry runs as a scheduled compaction job (BC3); rows past their class TTL are pruned.

## 2. Tiered Snapshot Compression (BC2)
World-state history is **not** kept at full resolution forever:

| Tier | Age | Resolution |
|---|---|---|
| Tier 0 | last **24 h** | full resolution (every transition) |
| Tier 1 | 24 h – 7 d | **minute** summaries (aggregate transitions per minute) |
| Tier 2 | > 7 d | **hourly** summaries (aggregate per hour) |

- Aggregation per window: numeric fields (cpu, memory) → min/max/avg/last; categorical
  (active_window, focused_process) → last value + distinct-count; counters → sum.
- Aggregated summaries live in dedicated tables; raw Tier-0 rows are pruned after summarizing.

## 3. Compaction Job (BC3)
- Runs on the central **Scheduler** (Phase B5), priority BACKGROUND/LOGGING, low frequency
  (e.g., every 10–15 min), exception-isolated, never blocks perception.
- Steps each run: classify-expire (BC1) → roll Tier-0→Tier-1→Tier-2 (BC2) → update diagnostics (BC6).

## 4. Phase C Inheritance (BC4)
- Memory Engine (Phase C) consumes **compressed** history: SIGNIFICANT events + Tier-1/Tier-2
  summaries — **never** the raw EPHEMERAL stream.
- Interface: `StateManager.compacted_history(since=...) -> list[summary|significant_event]`.
- This keeps long-term semantic memory dense and meaningful, not flooded with mouse-move noise.

## 5. Bounded Serialization + Boot Budget (BC5)
- ContinuityManager snapshot stays bounded (already: ledger ring `maxlen`, world-state snapshot).
- Hard budget: **boot restoration < 2 seconds.** Ledger rehydrate loads only recent Tier-0;
  older history stays on disk (lazy-queried). Measured by an acceptance test asserting restore
  wall-time < 2s with a large seeded store.

## 6. State Diagnostics (BC6)
`StateManager.diagnostics() -> dict` exposing at minimum:
- `event_count` (ledger ring + persisted)
- `memory_usage` (approx bytes of in-memory state/ring)
- `snapshot_count` (Tier-0/1/2 counts)
- `compression_ratio` (raw events ÷ stored rows after compaction)
- `serialization_size` (bytes of the continuity snapshot)

## Implementation Notes (for the future checkpoint)
- New module: `shared_core/state_manager/compaction.py` (classifier + tier roller + expiry).
- Extend `ledger_store.py` with summary tables + class column (additive migration).
- Register the compaction job via `Scheduler.register_task(...)` in `main.py` (additive).
- Sequencing: implement **before Phase C completes** so BC4 can feed the Memory Engine. Exact
  checkpoint position set by the user (current fast-track: B12 → B13 → minimal B6 → [compaction] → Phase C).
- Backward compatible: existing ledger keeps working; compaction is additive and degrades to the
  current flat-cap behavior if disabled.
