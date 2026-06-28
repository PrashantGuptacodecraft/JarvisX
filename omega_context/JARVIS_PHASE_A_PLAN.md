# JARVIS PHASE-A PLAN (OMEGA FROZEN)

> Strategic directive (2026-06-27): **OMEGA development frozen.** All engineering goes to
> JARVIS MODE until every Phase A–F capability milestone PASSES. Priority order is fixed
> (P1→P6 below). **Progress is tracked by capability milestones, NOT percentages** — the
> authoritative tracker is `CAPABILITY_MILESTONES.md`. This document is the engineering plan.
> **Still no implementation** — this is Phase-A planning.

## 0. Program Shape: Six Phases (= the six priorities)

| Phase | Priority | Subsystem | Milestones | Gate |
|---|---|---|---|---|
| **A** | P1 | Shared Core **Event Bus** | 10 (A1–A10) | unblocks all others |
| **B** | P2 | **State Manager + World-State Engine** (+ History Ledger) | 24 (B1–B14 + BL1–BL10) | needs A |
| **C** | P3 | **Memory Engine + Knowledge Graph** | 14 (C1–C14) | needs A, B |
| **D** | P4 | **Developer Super-Intelligence** (flagship) | 16 (D1–D16) | needs A, B, C |
| **E** | P5 | **Autonomous Tool Factory** | 12 (E1–E12) | needs A, C, D |
| **F** | P6 | **Predictive Behavior Engine** | 13 (F1–F13) | needs A, B, C |

Dependencies are strictly downward — A is the spine, everything rides it. Phases B/C can overlap once A lands; D is the flagship and the largest lift; E/F build on the substrate.

### Definition of "JARVIS research-lab level"
Not a percentage — a milestone gate: **all 89 capability milestones across Phases A–F PASS**,
each validated by its acceptance test in `CAPABILITY_MILESTONES.md`. Browser/Deployment/
multimodal-depth are deliberately **out of the A–F milestone set** (post-gate polish). The OMEGA
freeze lifts only when the A–F gate is met.

---

## 1. PHASE A — SHARED CORE EVENT BUS (build-ready design)

**Mission:** one in-process, thread-safe nervous system. Every subsystem publishes facts and subscribes to what it needs. No subsystem calls another directly for cross-cutting signals.

### 1.1 Module layout
```
shared_core/
├── __init__.py            # exposes get_bus() singleton accessor
└── event_bus/
    ├── __init__.py
    ├── bus.py             # EventBus: publish/subscribe/unsubscribe, dispatch
    ├── event.py           # Event dataclass + EventMeta
    ├── topics.py          # canonical topic constants + taxonomy
    ├── subscription.py    # Subscription handle (filter, mode, queue)
    └── journal.py         # optional event journaling hook (for Phase B/continuity)
```
Phase A creates `shared_core/` as a real package. (First brick of the hybrid tree — non-destructive; nothing else moves yet.)

### 1.2 Event model
```python
@dataclass(frozen=True)
class Event:
    topic: str            # dotted, e.g. "perception.os.snapshot"
    payload: dict         # JSON-serializable
    source: str           # publisher id, e.g. "os_awareness"
    ts: float             # monotonic + wall captured at publish
    id: str               # uuid4
    correlation_id: str | None = None   # ties request→result chains
```
Rules: payloads MUST be JSON-serializable (enables journaling + future cross-process + Phase-B snapshotting). No live object references in payloads.

### 1.3 Concurrency model (decisive choice)
The existing system is **threaded, not asyncio** (`core_loop` daemon thread, listener/gesture/context_watcher/screen_memory each in their own threads). Therefore the bus is **thread-first**:

- **Thread-safe** registry guarded by a lock; publish is callable from any thread.
- **Two delivery modes per subscription:**
  - `SYNC` — handler runs inline on the publisher's thread (for cheap, ordered, low-latency consumers like the state manager).
  - `ASYNC` — event is dropped into the subscriber's own bounded queue, drained by one dedicated worker thread per subscriber (for slow/IO/LLM consumers, so a slow handler never blocks a fast perceiver).
- An **asyncio bridge** (`subscribe_async`) is provided so future async consumers can `await` events via a thread-safe `call_soon_threadsafe` hop. Not required for Phase A consumers.

This avoids forcing an asyncio rewrite of the main loop while still giving non-blocking fan-out.

### 1.4 Topic taxonomy (canonical, wildcard-subscribable)
```
perception.os.*        perception.screen.*     perception.vision.*
perception.browser.*   perception.voice.*      perception.dev.*
cognition.intent       cognition.plan          cognition.request
cognition.result       cognition.trace
action.request         action.result           action.error
memory.write           memory.query            memory.kg.update
predict.suggestion     predict.preload
system.health          system.lifecycle        system.config
tool.created           tool.invoked
```
Subscriptions support exact (`action.result`) and prefix-wildcard (`perception.*`, `perception.os.*`) matching. `topics.py` holds these as constants so no stringly-typed drift.

### 1.5 EventBus API (frozen surface)
```python
bus = get_bus()                       # process singleton
sub = bus.subscribe(pattern, handler, mode=ASYNC, source="state_manager",
                    maxlen=256, coalesce_key=None)
bus.publish(topic, payload, source=..., correlation_id=None)
bus.unsubscribe(sub)
bus.stats()                           # per-topic counts, queue depths, drops
bus.drain()                           # for tests: process all async queues to empty
```

### 1.6 Backpressure & coalescing (must-have for high-rate perception)
- Each ASYNC subscription has a **bounded** queue (`maxlen`). On overflow: **drop-oldest** by default.
- `coalesce_key`: for high-frequency topics (e.g. `perception.os.snapshot` at 4Hz), if a key is set, a newer event **replaces** the unprocessed older one in queue — the consumer always sees the latest, never a backlog.
- `bus.stats()` exposes drop counts so we can tune rates. Silent drops are logged at DEBUG with counters (no silent truncation).

### 1.7 Journaling hook (seed for Phase B continuity)
`journal.py` provides an optional subscriber that appends events on a whitelist of topics to the persistence layer (ring-buffered table). Off by default in Phase A; Phase B turns it on for state replay / "restart = pause." Kept here so the interface exists from day one.

### 1.8 Integration into the live system (non-breaking)
Exact seams, from reading `main.py` / `core_loop.py`:

1. **Create the bus first** in `build_jarvis()` (top, before `speaker`): `bus = get_bus()`. Pass it to constructors that opt in; legacy constructors are untouched (bus is optional kw).
2. **core_loop._process**: after computing `response`, publish `cognition.intent` (the command) and `action.result` (the response) with a per-turn `correlation_id` (reuse the existing `turn_token`). Pure addition — existing flow unchanged.
3. **ContextWatcher** (already a thread, already writes `brain.volatile_memory["active_window"]`): also `bus.publish("perception.os.active_window", {...})`. Keeps the old write for compatibility.
4. **ScreenMemory / CodeAnalyzer / gesture**: add publishes alongside their current callbacks. No removals.
5. **The command `queue.Queue`** stays as-is for now (listener/BCI/sync feed it). Later phases may bridge it onto the bus; Phase A does **not** touch it — zero regression risk.

Adoption is **opt-in and additive**: a subsystem keeps working if it ignores the bus. We migrate publishers/subscribers incrementally in B–F.

### 1.9 Definition of Done (Phase A)
- [ ] `shared_core/event_bus` package with `EventBus`, `Event`, topic constants.
- [ ] SYNC + ASYNC delivery, per-subscriber worker threads, bounded queues, coalescing.
- [ ] Wildcard subscriptions; `stats()`; `drain()` for deterministic tests.
- [ ] Bus instantiated in `build_jarvis`; **3 real publishers wired** (intent/result in core_loop, active_window in ContextWatcher, one perception publisher) and **1 demo subscriber** (a logger) — proving end-to-end with zero regression.
- [ ] Unit tests: pub/sub, wildcard, backpressure drop-oldest, coalesce-latest, thread-safety (concurrent publishers), unsubscribe.
- [ ] App still boots in GUI + headless unchanged.
- **Result:** all 10 Phase-A milestones (A1–A10 in `CAPABILITY_MILESTONES.md`) PASS; substrate ready for B–F.

> The DoD checklist above maps 1:1 onto milestones A1–A10. Phase A is COMPLETE only when
> every one is validated by its acceptance test — no partial credit, no percentage.

### 1.10 Risks & mitigations
- *Slow handler stalls perception* → ASYNC mode + bounded queues + coalescing.
- *Hidden ordering assumptions* → SYNC mode available where ordering matters (state manager).
- *Adoption churn* → additive opt-in; no existing call path removed in Phase A.
- *Serialization friction* → enforce JSON-able payloads via a dev-mode assert.

---

## 2. PHASES B–F (architecture-level; detailed plans authored at each phase start)

### Phase B — State Manager + World-State Engine (P2)
- `shared_core/state_manager/` subscribes to all `perception.*`, maintains a single versioned **`WorldState`** (typed sub-states: `SystemState`, `ScreenState`, `VisionState`, `BrowserState`, `VoiceState`, `DevState`) + per-field history ring buffers.
- **Perception Tick Scheduler**: fixed-rate samplers publish snapshots (OS ~2–4Hz, screen ~1Hz, etc.) with coalescing.
- **Continuity**: periodic + on-shutdown serialize WorldState + subsystem cursors via persistence; restore on boot → "restart = pause."
- Upgrades the OS-awareness daemon (add fs-watch, network, GPU, clipboard, terminal, app-state) and screen UI-tree (UIAutomation bindings already vendored in `.runtime/`).
- Query API: `state.snapshot()`, `state.get("os.cpu")`, `state.history("screen.active_window")`.
- **WORLD-STATE HISTORY LEDGER (mandatory addition, BL1–BL10).** Beyond present state, the
  machine continuously records **state transitions over time** into a chronological ledger.
  - *Current State* = live WorldState snapshot. *Historical Ledger* = ordered sequence of prior states.
  - Each transition records: timestamp · active_window · focused_process · cpu · memory ·
    running_terminals · browser_state_change · clipboard_change · file_modifications · network_summary.
  - Module: `shared_core/state_manager/ledger.py` (bounded in-memory ring) +
    `ledger_store.py` (rolling SQLite persistence under `data/`, pruned by cap/time-window).
  - Flow: bus event → StateManager updates WorldState → emits a transition → HistoryLedger
    records (ring + persistence). No unbounded memory or disk growth.
  - Retrospective query API: `ledger.at(t)` (point-in-time), `ledger.between(t0,t1)` (sequence),
    `ledger.recent(n)`. Answers: "what was happening 10 min ago?", "what sequence preceded the
    deployment error?", "which app was active before the crash?"
  - Later phases (C: memory/KG) may compress old history into long-term semantic memory.

### Phase C — Memory Engine + Knowledge Graph (P3)
- Promote `memory/manager.py` + `rag_manager.py` → `shared_core/memory_engine` (+ shim).
- **Knowledge Graph**: dependency-light **SQLite triple-store** (`subject, predicate, object, weight, first_seen, last_seen`) + in-memory `networkx` projection. Entities: Person/Project/File/App/Command/Tool/Event/Habit. Relations: works_on, edits, depends_on, precedes, authored_by, located_in. (Neo4j remains the documented future target; not adopted now on Windows/single-machine.)
- Subscribe to `action.result` + `cognition.trace` → record execution history **with relationships** (who/what/when/outcome). Episodic→semantic consolidation job on the scheduler.
- Populate the long-empty profile/preference tables from observed behavior. Habit edges feed Phase F.

### Phase D — Developer Super-Intelligence (P4, flagship)
`jarvis_mode/developer_intel/` components:
- `ast_indexer` — Python `ast` + **tree-sitter** (multi-lang) → symbol/import/call graph into the KG.
- `dependency_graph` — internal import graph + external deps (requirements/pip metadata) → KG.
- `architecture_model` — layers, cycles, module map; narratable; drift detection.
- `bug_predictor` — static/type/lint/dataflow (**pyright/ruff/mypy** headless) + LLM review via model_router; **pre-execution hook** on terminal/code_sandbox = "predict bugs before run."
- `test_runner` — detect pytest/unittest, run, parse, maintain red/green map, regression bisect; auto-provision venvs.
- `refactor_engine` — AST transforms via **rope/libcst**, test-gated application.
- `suggestion_engine` — autonomous suggestions grounded in code-KG + learned coding-style model.
- `vscode_bridge` — continuous monitoring. **Decision to confirm at Phase D start:** (a) watchdog file-watch of the workspace (lowest friction, uses existing `watchdog` dep) + parse VS Code state files, vs (b) a companion VS Code extension over a local socket (richest: live diagnostics/cursor/open-tabs), vs (c) LSP client driving language servers directly. Recommend starting (a)+(c), add (b) if we want true in-editor inline UX. All publish `perception.dev.*`.

### Phase E — Autonomous Tool Factory (P5)
- Define a formal **ToolSpec/registry** (today's controllers are ad-hoc) so tools plug in uniformly.
- `gap_detector` (intent with no handler / repeated manual sequences from KG) → `generator` (model_router writes a ToolSpec-conforming module) → `validator` (sandbox + generated tests) → `registrar` (runtime import + register into brain dispatch) → persist to `jarvis_mode/tools/generated/` + registry. Gated by security layer + human confirm. Emits `tool.created`.

### Phase F — Predictive Behavior Engine (P6)
- Upgrade `brain/predictor.py`: add **temporal** (time-of-day/day-of-week) + **contextual** (active app, recent bus events, KG habit edges) features.
- Proactive actions: `predict.preload` (warm dev env), `predict.suggestion` (open apps before asked), anticipate repetitive tasks — executed via the action layer behind confidence thresholds + guardrails (reversible, user-interruptible).

---

## 3. Cross-cutting (every phase)
- Each subsystem ships as a **bus-publishing service** with tests; nothing ships untested.
- Reuse the shared **model_router** (`brain/ai_client.py`) for all LLM calls — no new provider code.
- Respect the **privacy guardrails** in `prashant_profile.md` at the system level.
- Maintain non-destructive migration: shims first, physical moves later, never delete behavior.

## 4. Immediate next action (on your go)
Implement **Phase A**: scaffold `shared_core/event_bus`, wire the bus into `build_jarvis`, add 3 publishers + 1 subscriber + unit tests, verify GUI/headless boot unchanged. Then author the detailed Phase-B plan.
```
STATUS: Phase-A planning complete and build-ready. Awaiting go-ahead to implement Phase A.
```
