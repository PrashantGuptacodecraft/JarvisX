# REPOSITORY AUDIT — EVERY FILE MAPPED (DUAL-BRAIN)

> Categories:
> **A** = Existing JARVIS system, already implemented (keep, maintain)
> **B** = Existing JARVIS system, partial — needs upgrade
> **C** = Missing advanced JARVIS system — must be built (no file yet)
> **D** = New OMEGA system — does not exist yet
> Plus **S** = belongs in Shared Core. Files can be tagged `A/S` etc.
> Audited scope: ~50 first-party source files (excludes `.runtime/comtypes_gen/*` auto-generated COM bindings and `__pycache__`).

## I. Entry / Orchestration
| File | LoC | Cat | Notes |
|---|---|---|---|
| `main.py` | 436 | A | System builder; wires all controllers + optional modules. Will boot both brains. |
| `core_loop.py` | 228 | A | Queue-driven JARVIS event loop. → `jarvis_mode/core/orchestrator`. |
| `setup.py` | 84 | A | Packaging. |
| `gesture_timing_checker.py` | 120 | A | Dev utility. |

## II. Brain → JARVIS Cognition (+ Shared)
| File | LoC | Cat | Notes |
|---|---|---|---|
| `brain/core.py` | 1923 | B | Intent engine + router (40+ intents). Upgrade: continuous context, OMEGA bus hook. |
| `brain/ai_client.py` | 511 | A/S | Multi-provider LLM router + failover → **shared_core/model_router**. |
| `brain/planner.py` | 464 | B | Autonomous multi-step planner. Upgrade: long-horizon, bus-aware. |
| `brain/predictor.py` | 133 | B | Command co-occurrence prediction. Upgrade: proactive preload, temporal/habit. |
| `brain/agents/orchestrator.py` | 197 | B | Research/write/execute, ThreadPool. → agent_swarm. |
| `brain/agents/swarm.py` | 58 | B | Researcher→Coder→Reviewer. Upgrade: 8 standing specialists. |
| `brain/agents/universal_agent.py` | 233 | B | Gemini tool-calling agent. Upgrade: bus + tool_factory. |
| `brain/agents/researcher.py` | 68 | B | Specialist. |
| `brain/agents/writer.py` | 84 | B | Specialist. |
| `brain/agents/executor.py` | 70 | B | Specialist. |

## III. Perception — OS / Screen / Vision / Browser
| File | LoC | Cat | Notes |
|---|---|---|---|
| `tools/system/controller.py` | 163 | B | CPU/RAM/battery/wifi/processes/kill. Upgrade: continuous + fs/net/gpu/clipboard/term. |
| `tools/system/context_watcher.py` | 51 | B | Active-window poll. Upgrade: full app-state model. |
| `tools/system/computer_use.py` | 84 | A | Keyboard/mouse/screenshot. (Action layer.) |
| `tools/vision/controller.py` | 33 | B | OCR (pytesseract/easyocr). Upgrade: streaming + UI tree. |
| `tools/vision/core/hand_tracker.py` | 212 | A | MediaPipe hands, 30fps. |
| `tools/vision/core/finger_analyzer.py` | 111 | A | Joint-angle finger states. |
| `tools/vision/core/gesture_classifier.py` | 150 | A | 32 gestures. |
| `tools/vision/core/gesture_buffer.py` | 111 | A | Smoothing buffer. |
| `tools/vision/control/action_dispatcher.py` | 232 | A | Gesture→OS action, cooldowns. |
| `tools/vision/control/mouse_controller.py` | 123 | A | Accel curve, edge magnetism. |
| `tools/vision/gesture_engine.py` | 638 | A | Vision orchestrator. |
| `tools/vision/gesture_controller.py` | 222 | A | High-level gesture entry. |
| `tools/vision/calibration_manager.py` | 247 | A | Screen-map calibration. |
| `tools/vision/ui/hud_renderer.py` | 183 | A | OpenCV HUD. |
| `tools/vision/modules/screen_agent.py` | 201 | B | Vision-AI GUI automation. Upgrade: UI-tree grounded. |
| `tools/vision/modules/screen_memory.py` | 178 | B | Episodic screen capture. Upgrade: continuous + KG. |
| `tools/vision/modules/object_detector.py` | 160 | A | YOLOv8-nano. |
| `tools/vision/modules/emotion_detector.py` | 213 | A | deepface/fer emotion + stress. |
| `tools/vision/modules/gaze_tracker.py` | 231 | A | Iris gaze + dwell-click. |
| `tools/vision/modules/air_drawing.py` | 629 | A | Air-draw canvas (locally modified). |
| `tools/vision/modules/ar_overlay.py` | 140 | A | AR overlays. |
| `tools/vision/modules/gesture_heatmap.py` | 130 | A | Heatmap overlay. |
| `tools/vision/modules/voice_gesture_fusion.py` | 136 | A | Voice+gesture fusion. |
| `tools/web/playwright_agent.py` | 101 | B | Playwright automation → browser_intel. |
| `tools/web/controller.py` | 371 | B | Fetch/search/summarize. |
| `tools/browser/controller.py` | 911 | B | 40+ sites, YouTube/Gmail, OCR actions. Upgrade: live tab/DOM/login. |

## IV. Action — Apps / Files / Terminal / Comms
| File | LoC | Cat | Notes |
|---|---|---|---|
| `tools/apps/controller.py` | 80 | A | App launch/window. |
| `tools/files/controller.py` | 572 | A | Find/read/create/organize, doc gen. |
| `tools/terminal/controller.py` | 175 | A | Shell + Python exec, safe-mode. |
| `tools/whatsapp/controller.py` | 1255 | A | Messaging/call workflows. |
| `tools/tasks/controller.py` | 49 | A | Reminders/todos surface. |
| `tools/automation/workflow_recorder.py` | 253 | A | Macro record/replay. |

## V. Memory / Knowledge / Persistence (Shared)
| File | LoC | Cat | Notes |
|---|---|---|---|
| `memory/manager.py` | 1259 | B/S | SQLite, 14 tables → **shared_core/memory_engine**. Upgrade: habit learning. |
| `memory/rag_manager.py` | 99 | B/S | ChromaDB RAG → **shared_core/rag**. Upgrade: wired KG. |
| *(knowledge graph)* | — | C/S | **MISSING** — semantic entity/relation store. |

## VI. Shared Infrastructure (existing seeds)
| File | LoC | Cat | Notes |
|---|---|---|---|
| `config/settings.py` | 188 | A/S | Central config → shared_core/config. |
| `config/logger.py` | 42 | A/S | Rotating logger → shared_core/logging. |
| `tools/execution/code_sandbox.py` | 59 | A/S | Isolated exec → shared_core/sandbox. |
| `tools/security/private_mode.py` | 173 | A/S | AES + capture block → shared_core/security. |
| `tools/sync/api_server.py` | 157 | A | Cross-device REST. |
| `analytics/dashboard_server.py` | 94 | A | Flask gesture dashboard. |
| *(event bus)* | — | C/S | **MISSING** — async pub/sub spine. |
| *(state manager)* | — | C/S | **MISSING** — continuity/serialization. |
| *(scheduler)* | — | C/S | **MISSING** — time/event daemon. |

## VII. Voice / UI
| File | LoC | Cat | Notes |
|---|---|---|---|
| `voice/listener.py` | 589 | A | Continuous mic, wake-word, barge-in. |
| `voice/speaker.py` | 702 | A | Multi-engine TTS. |
| `voice/authenticator.py` | 183 | A | Biometric voice auth. |
| `voice/spatial_audio.py` | 141 | A | Spatial audio. |
| `ui/interface.py` | 1882 | A | Tkinter HUD GUI (locally modified). |
| `ui/hud_overlay.py` | 315 | A | Desktop overlay. |
| `ui/avatar.py` | 170 | A | Animated face. |
| `ui/live_transcript.py` | 161 | A | Live captions. |
| `ui/audio_visualizer.py` | 90 | A | Audio viz. |

## VIII. Peripherals
| File | LoC | Cat | Notes |
|---|---|---|---|
| `tools/iot/controller.py` | 149 | A | Home Assistant/MQTT (gated). |
| `tools/bci/controller.py` | 153 | A | EEG (hardware-gated). |

## IX. Category C — Missing JARVIS Systems (NO FILE YET)
- `developer_intel/` — AST index, bug prediction, refactor engine, autonomous test runner, dependency analysis, architecture model, VS Code/LSP bridge.
- `tool_factory/` — missing-tool detection, dynamic script generation, validation, permanent registration.
- `deployment_intel/` — build/deploy monitoring, failure detection, auto-debug, auto-retry, log inspection.
- `browser_intel/` (service form) — continuous tab/DOM/login/form/error observer.
- `os_awareness/` (daemon form) — fused continuous SystemState (fs/net/gpu/clipboard/terminal).
- Shared **event_bus**, **state_manager**, **scheduler**, **knowledge_graph**, **persistence** adapters.

## X. Category D — OMEGA Systems (NONE EXIST — all greenfield)
`meta_cognition/`, `poly_cognitive/{intuition,logic,creativity,skepticism,abstraction}/`,
`synthesis_matrix/`, `truth_verification/`, `scientific_method/`, `cognitive_mutation/`,
`abstract_concept/`, `imagination_physics/`, `math_discovery/`, `continuity/`.

## XI. Tally
- **Category A (done):** ~38 files — strong JARVIS perception/action/voice/UI foundation.
- **Category B (upgrade):** ~16 files — cognition, memory, browser, OS-awareness, screen, agents.
- **Category C (build):** ~10 subsystems — developer_intel, tool_factory, deployment_intel, bus, state, scheduler, KG, etc.
- **Category D (OMEGA):** 10 subsystems — 0% built.
