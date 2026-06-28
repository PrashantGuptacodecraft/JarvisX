# JARVIS MODE ARCHITECTURE (SYSTEM 1 — EXTERNAL EXECUTION INTELLIGENCE)

> Goal: more advanced than Iron Man's JARVIS. Preserve everything built; only upgrade.
> JARVIS perceives the world, reasons about action, and executes. It never improves its
> own cognition internally — that is OMEGA's job (System 2). The two meet on the event bus.

## I. Layered Topology

```
                         ┌──────────────────────────────────────────┐
   WORLD  ───perceive──▶ │  PERCEPTION LAYER                          │
                         │  os_awareness · screen_understanding ·     │
                         │  vision_multimodal · browser_intel · voice │
                         └───────────────┬──────────────────────────┘
                                         │ observations (event bus)
                         ┌───────────────▼──────────────────────────┐
                         │  COGNITION LAYER (JARVIS-local)            │
                         │  intent_engine · planner · predictive ·    │
                         │  developer_intel · agent_swarm orchestrator│
                         └───────────────┬──────────────────────────┘
                                         │ action intents (via security layer)
                         ┌───────────────▼──────────────────────────┐
   WORLD  ◀───act─────── │  ACTION LAYER                              │
                         │  computer_control · apps · files ·         │
                         │  terminal · browser · whatsapp · iot · bci │
                         └──────────────────────────────────────────┘
        UI LAYER (overlay/HUD/avatar/voice I/O) wraps all three.
        SHARED CORE (memory/router/state/bus/security/sandbox/scheduler/kg) underpins all.
```

## II. The 12 Required JARVIS Systems — Architecture + Status

Status legend: ✅ implemented · 🟡 partial/upgrade · 🔴 missing.

### 1. Full OS Awareness — 🟡
- **Have:** `tools/system/controller.py` (CPU, RAM, battery, wifi/IP, processes, kill), `tools/system/context_watcher.py` (active-window poll, 2s).
- **Missing:** continuous **file-system watcher** (global, not just code), **network traffic** inspection, **GPU** telemetry, **terminal activity** stream, **clipboard** monitoring as a live signal, **application-state** model. Today these are point queries, not a continuous fused world-state.
- **Upgrade:** promote to a continuous `os_awareness` daemon publishing a structured `SystemState` snapshot onto the event bus at a fixed tick.

### 2. Continuous Screen Understanding — 🟡
- **Have:** `tools/vision/controller.py` (OCR via pytesseract/easyocr), `modules/screen_agent.py` (grid+vision-AI click/type), `modules/screen_memory.py` (60s episodic capture + AI tags), `modules/object_detector.py` (YOLOv8).
- **Missing:** **UI element detection** (accessibility tree / control enumeration — `.runtime/comtypes_gen/UIAutomationClient` bindings exist but are unused), **window hierarchy** model, **continuous** semantic scene graph (capture is periodic, not streaming).
- **Upgrade:** a `screen_understanding` service producing a live semantic UI graph (elements + roles + bounds + text) every tick, backed by UIAutomation + OCR + vision fusion.

### 3. Autonomous Coding Intelligence — 🔴 (mostly)
- **Have:** `tools/code/analyzer.py` (watchdog file-change → AI review), `tools/terminal/controller.py` + `tools/execution/code_sandbox.py` (run code/commands).
- **Missing:** **AST parsing**, **bug prediction**, **automatic refactoring**, **autonomous test execution**, **dependency analysis**, **architecture understanding**, **optimization suggestions**. No tree-sitter/`ast` usage anywhere.
- **Upgrade:** new `developer_intel` subsystem (see #4) — this is the single biggest JARVIS gap.

### 4. Developer Super-Intelligence — 🔴
- **Have:** nothing direct (analyzer is the closest, shallow).
- **Missing:** continuous **VS Code watching**, project-architecture model, mistake detection **before execution**, missing-feature prediction, auto-written suggestions, automatic local test environments.
- **Upgrade:** new subsystem combining an indexed code graph (AST + imports + call graph), an LSP/VS Code bridge, a pre-run static checker, and a test-runner agent.

### 5. Browser Intelligence — 🟡
- **Have:** `tools/browser/controller.py` (40+ sites, YouTube/Gmail workflows, OCR-driven actions), `tools/web/playwright_agent.py` + `tools/web/controller.py` (Playwright automation, fetch/search).
- **Missing:** continuous **tab monitoring**, **login-state** detection, **form understanding**, **DOM-level** live interaction model, website **error detection**, fully **autonomous multi-step browser workflows**.
- **Upgrade:** a persistent Playwright-driven `browser_intel` service with a live tab/DOM observer feeding the event bus.

### 6. Voice + Multimodal Intelligence — ✅/🟡
- **Have:** `voice/listener.py` (continuous mic, wake-word, barge-in, sounddevice fallback), `voice/speaker.py` (Edge/gTTS/pyttsx3/ElevenLabs TTS), `voice/authenticator.py` (biometric voice), `voice/spatial_audio.py`; vision multimodal: hand tracking, gesture (32), `emotion_detector`, `gaze_tracker`, `air_drawing`, `voice_gesture_fusion`.
- **Missing:** robust **facial recognition** (identity, not just emotion), deeper **environmental awareness** (scene/context fusion), persistent **contextual conversation memory** binding voice ↔ memory engine end-to-end.
- **Upgrade:** mostly mature; add face-ID, environmental scene model, tighten conversation-memory loop.

### 7. Long-Term Memory — 🟡
- **Have:** `memory/manager.py` (SQLite, 14 tables: history, episodes, command_patterns, profile, facts, notes, contacts, projects, missions, workflows, knowledge_docs, reminders, todos), `memory/rag_manager.py` (ChromaDB RAG).
- **Missing:** explicit **semantic knowledge graph** (entities/relations), active **habit/daily-pattern learning**, populated preference/profile learning (tables exist, largely empty), coding-style modeling.
- **Upgrade:** promote memory to **shared core**; add a real knowledge graph and a habit-learning loop. (See shared `knowledge_graph`.)

### 8. Predictive Behavior Engine — 🟡
- **Have:** `brain/predictor.py` (command co-occurrence, confidence, next-command prediction; 64 patterns learned).
- **Missing:** **preload dev environment**, **open apps before asked**, **anticipate repetitive tasks**, time-aware prediction. Prediction exists but drives nothing proactively.
- **Upgrade:** wire predictor → action layer for proactive preloading; add temporal/habit features.

### 9. Autonomous Tool Creation — 🔴
- **Have:** `tools/terminal/write_and_run` + sandbox can generate/run code ad hoc.
- **Missing:** **detect missing tools**, **auto-write new scripts as permanent tools**, **dynamic utility generation**, **permanent integration** (register new tool into the dispatch table at runtime).
- **Upgrade:** new `tool_factory` — gap detector → code generator → sandbox validation → dynamic registration + persistence.

### 10. Multi-Agent Execution Swarm — 🟡
- **Have:** `brain/agents/` — `orchestrator.py` (research/write/execute, ThreadPool), `swarm.py` (Researcher→Coder→Reviewer), `universal_agent.py` (Gemini tool-calling), `researcher/writer/executor.py`.
- **Missing:** the **named specialist roster** you want: coding, browser, deployment, file-system, API, debugging, security, memory agents collaborating **continuously** (current swarm is sequential/on-demand, generic roles).
- **Upgrade:** formalize 8 standing specialist agents over the event bus with a shared blackboard, continuous collaboration rather than one-shot pipelines.

### 11. Real-Time Deployment Intelligence — 🔴
- **Have:** nothing.
- **Missing:** monitor deployments, detect **build failures**, **auto-debug** deploy errors, **auto-retry**, **log inspection**.
- **Upgrade:** new `deployment_intel` subsystem (CI/build/log watchers + debugging agent).

### 12. Full Computer Control — ✅/🟡
- **Have:** `tools/system/computer_use.py` (keyboard, mouse, hotkeys, screenshot, screen size), `tools/terminal` (terminal exec), `tools/apps` (launch/window), process mgmt, gesture control, `tools/automation/workflow_recorder.py` (macro record/replay).
- **Missing:** unified **API orchestration** layer, richer **process management**, robust long-horizon **autonomous workflows** (beyond recorded macros).
- **Upgrade:** consolidate under an `action` facade with an API-orchestration agent.

## III. Supporting Existing Subsystems (keep, fold into JARVIS)
- **UI:** `ui/interface.py` (Tkinter HUD GUI, 1882 lines), `ui/hud_overlay.py`, `ui/avatar.py`, `ui/live_transcript.py`, `ui/audio_visualizer.py`; vision HUD `tools/vision/ui/hud_renderer.py`.
- **Security:** `tools/security/private_mode.py` (AES encryption, capture block) → seeds shared **security layer**.
- **Sync:** `tools/sync/api_server.py` (cross-device REST, port 7777).
- **Peripherals:** `tools/iot/controller.py` (Home Assistant/MQTT), `tools/bci/controller.py` (EEG, hardware-gated).
- **Analytics:** `analytics/dashboard_server.py` (Flask gesture dashboard).
- **Comms:** `tools/whatsapp/controller.py` (1255 lines), `tools/web`, `tools/browser`.

## IV. JARVIS-Owned vs Shared
- **JARVIS owns:** perception, action, voice, developer_intel, agent_swarm, predictive, tool_factory, deployment_intel, UI, peripherals.
- **JARVIS consumes (shared core):** memory engine, model router (`brain/ai_client.py`), state manager, scheduler, security, sandbox, event bus, logging, knowledge graph, persistence.

## V. Upgrade Doctrine
Every JARVIS subsystem must move from **request/response point-tools** to **continuous, event-bus-publishing services** that maintain live world-state. That continuous-perception + proactive-action loop is what pushes JARVIS past Iron Man's JARVIS. See `MISSING_CAPABILITIES.md` for research-lab-level additions.
