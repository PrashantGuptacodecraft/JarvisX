# HYBRID REPOSITORY STRUCTURE (DUAL-BRAIN TARGET TREE)

> Target layout for the dual-brain OS. **No files are moved yet** — this is the design.
> Migration is non-destructive: existing modules are re-homed by import-facade first,
> physically relocated only in a later, tested phase. Nothing is deleted.

## I. Target Tree

```
JarvisX/
├── main.py                         # boots shared_core, then both brains, over the event bus
├── core_loop.py                    # (→ jarvis_mode/core/orchestrator) JARVIS command loop
│
├── shared_core/                    # ── SHARED BY BOTH BRAINS ──
│   ├── event_bus/                  # NEW  async pub/sub spine (topics, blackboard)
│   ├── memory_engine/              # MOVE memory/manager.py
│   ├── rag/                        # MOVE memory/rag_manager.py
│   ├── knowledge_graph/            # NEW  semantic entity/relation store
│   ├── state_manager/              # NEW  consciousness continuity / serialization
│   ├── scheduler/                  # NEW  time + event task daemon (reminders, ticks)
│   ├── model_router/               # MOVE brain/ai_client.py (multi-provider + failover)
│   ├── security/                   # MOVE tools/security/private_mode.py + containment policy
│   ├── sandbox/                    # MOVE tools/execution/code_sandbox.py
│   ├── persistence/                # NEW  sqlite/chroma/kv adapters (consolidate db paths)
│   ├── logging/                    # MOVE config/logger.py
│   └── config/                     # MOVE config/settings.py
│
├── jarvis_mode/                    # ── SYSTEM 1: EXTERNAL EXECUTION ──
│   ├── core/
│   │   ├── orchestrator/           # MOVE core_loop.py
│   │   ├── intent_engine/          # MOVE brain/core.py (intent detect + route)
│   │   └── planner/                # MOVE brain/planner.py
│   ├── perception/
│   │   ├── os_awareness/           # MOVE tools/system/controller.py + context_watcher.py  [UPGRADE: fs/net/gpu/clipboard/term]
│   │   ├── screen_understanding/   # MOVE tools/vision/controller.py + modules/screen_agent, screen_memory  [UPGRADE: UI tree]
│   │   ├── vision_multimodal/      # MOVE tools/vision/core, control, modules/*, ui/hud_renderer, calibration, gesture_*
│   │   └── browser_intel/          # NEW  + MOVE tools/web/playwright_agent.py  [UPGRADE: tab/DOM/login monitor]
│   ├── action/
│   │   ├── computer_control/       # MOVE tools/system/computer_use.py
│   │   ├── apps/                   # MOVE tools/apps/
│   │   ├── files/                  # MOVE tools/files/
│   │   ├── terminal/               # MOVE tools/terminal/
│   │   ├── browser/                # MOVE tools/browser/
│   │   ├── web/                    # MOVE tools/web/controller.py
│   │   └── whatsapp/               # MOVE tools/whatsapp/
│   ├── voice/                      # MOVE voice/* (listener, speaker, authenticator, spatial_audio)
│   ├── developer_intel/            # NEW  AST index, bug predict, refactor, test runner, VS Code bridge, dep/arch graph
│   ├── tool_factory/               # NEW  gap detect → generate → validate → register tool
│   ├── deployment_intel/           # NEW  build/deploy/log watch + auto-debug + retry
│   ├── predictive_engine/          # MOVE brain/predictor.py  [UPGRADE: proactive preload, temporal]
│   ├── agent_swarm/                # MOVE brain/agents/*  [UPGRADE: 8 standing specialists on bus]
│   ├── automation/                 # MOVE tools/automation/workflow_recorder.py
│   ├── peripherals/
│   │   ├── iot/                    # MOVE tools/iot/
│   │   ├── bci/                    # MOVE tools/bci/
│   │   └── sync/                   # MOVE tools/sync/api_server.py
│   ├── analytics/                  # MOVE analytics/dashboard_server.py
│   └── ui/                         # MOVE ui/* (interface, hud_overlay, avatar, transcript, audio_visualizer)
│
├── omega_mode/                     # ── SYSTEM 2: INTERNAL COGNITION (all NEW) ──
│   ├── meta_cognition/             # reasoning-quality supervisor
│   ├── poly_cognitive/
│   │   ├── intuition/  logic/  creativity/  skepticism/  abstraction/
│   ├── synthesis_matrix/           # debate → converge
│   ├── truth_verification/         # adversarial attack + micro-sim
│   ├── scientific_method/          # hypothesis gen + self-attack
│   ├── cognitive_mutation/         # invent reasoning methods
│   ├── abstract_concept/           # cross-domain isomorphisms
│   ├── imagination_physics/        # impossible-world sims
│   ├── math_discovery/             # Lean4/Coq bridges
│   └── continuity/                 # cognitive-state (de)serialization (uses shared state_manager)
│
├── omega_context/                  # ARCHITECTURE MEMORY / DOCS (this folder)
├── config/   data/   logs/   models/   tests/
└── requirements*.txt  setup.py
```

## II. Migration Strategy (non-destructive, phased)

1. **Phase 0 — Facade, no moves.** Create `shared_core/`, `jarvis_mode/`, `omega_mode/` packages whose `__init__.py` re-export the existing modules from their current paths. Code keeps working; new code imports the new names. Zero risk.
2. **Phase 1 — Extract shared core.** Physically move logger, settings, ai_client, code_sandbox, memory, rag, private_mode into `shared_core/`, leaving import shims at old paths. Add NEW shared pieces: event_bus, state_manager, scheduler, knowledge_graph, persistence.
3. **Phase 2 — Re-home JARVIS.** Move `brain/`, `tools/`, `voice/`, `ui/`, `analytics/` under `jarvis_mode/` with shims. Convert point-tools into bus-publishing services incrementally.
4. **Phase 3 — Build OMEGA.** Greenfield `omega_mode/` per OMEGA roadmap, consuming shared_core only.
5. **Phase 4 — Remove shims.** Once all imports updated and tests green, delete the temporary re-export shims (never the logic).

## III. Invariants
- **No deletion of behavior.** Only relocation + addition.
- **One direction of dependency:** `jarvis_mode/` → `shared_core/`; `omega_mode/` → `shared_core/`. The two brains never import each other directly — they communicate only via `shared_core/event_bus`.
- **`data/`, `models/`, `logs/`, `.env`, `config`** remain stable anchors throughout.
