# MISSING CAPABILITIES — BEYOND IRON MAN'S JARVIS (RESEARCH-LAB LEVEL)

> Capabilities to push JARVIS MODE far past a normal assistant and past the fictional JARVIS.
> Includes systems you did not list. Each is tagged: **[J]** JARVIS, **[S]** Shared, **[O]** OMEGA.
> None exist yet unless noted.

## I. The Substrate That Makes "Always Aware" Real
1. **Unified Event Bus + Blackboard [S]** — async pub/sub; every perceiver publishes, every actor/agent subscribes. Without this, "continuous understanding" is impossible. *Highest leverage missing piece.*
2. **World-State Model [J/S]** — a single live, queryable snapshot fusing OS + screen + browser + voice + location into one structured object, versioned over time.
3. **Perception Tick Scheduler [S]** — fixed-rate sampling of all sensors with backpressure, so the system has a heartbeat, not just reactions.
4. **Consciousness Continuity / State Manager [S]** — serialize the entire live state + agent memory so a restart resumes mid-thought (shared with OMEGA).

## II. Developer / Coding Super-Intelligence (your biggest differentiator)
5. **Live Code Knowledge Graph [J]** — AST + import graph + call graph + symbol index of *your* repos, updated on save (tree-sitter / `ast` / LSP).
6. **Pre-Execution Mistake Detector [J]** — static + type + lint + dataflow checks that fire *before* you run code; predicts runtime errors and undefined-symbol bugs.
7. **Autonomous Test Intelligence [J]** — generate, run, and triage tests automatically; maintain a live red/green map; bisect regressions.
8. **Refactoring Engine [J]** — AST-level safe transforms (rename, extract, inline, dead-code removal) with test-gated application.
9. **Architecture Comprehension [J]** — build and narrate a model of project architecture; detect drift, cycles, and missing layers.
10. **Missing-Feature Predictor [J]** — infer intended-but-absent features from code shape + your habits; propose scaffolds.
11. **VS Code / LSP Bridge [J]** — read editor state, diagnostics, open files, cursor; offer inline suggestions in real time.
12. **Auto Local Test-Environment Provisioner [J]** — spin up venvs/containers/services on demand to run code safely.

## III. Autonomy & Self-Extension
13. **Tool Factory [J]** — detect missing capability → generate script → sandbox-validate → register permanently into the dispatch table → persist. Self-growing toolset.
14. **Skill Library / Reusable Procedures [J]** — learned, parameterized macros promoted to first-class skills (Voyager-style).
15. **Deployment Intelligence [J]** — watch CI/builds/deploys; detect failures; auto-read logs; auto-debug; auto-retry with fixes.
16. **Autonomous Workflow Engine [J]** — long-horizon, branching, resumable workflows beyond recorded macros, with checkpoints.
17. **Self-Healing Supervisor [J]** — watchdog that restarts crashed subsystems, quarantines faulty tools, and reports health.

## IV. Perception Depth (beyond fiction)
18. **Continuous Network Awareness [J]** — connections, bandwidth, suspicious traffic, per-app network use.
19. **GPU/Compute Telemetry [J]** — VRAM/util/thermals; budget heavy tasks accordingly.
20. **Clipboard + Terminal Activity Stream [J]** — treat clipboard and shell history as live context signals.
21. **UI Accessibility-Tree Reader [J]** — true element-level screen understanding (roles, bounds, values) via UIAutomation — bindings already vendored in `.runtime/`, currently unused.
22. **Facial Identity Recognition [J]** — who is present, not just their emotion; presence-aware behavior.
23. **Environmental / Scene Awareness [J]** — fuse camera + audio into a model of the physical context.
24. **Audio Scene Analysis [J]** — detect events (doorbell, phone, name spoken) beyond speech.

## V. Memory & Reasoning Quality
25. **Semantic Knowledge Graph [S]** — explicit entities/relations over people, projects, files, habits; the backbone of real long-term memory.
26. **Habit & Temporal Pattern Learner [J]** — "you open X at 9am, run tests before commits"; drives proactivity.
27. **Coding-Style Model [J]** — learn your conventions; make all generated code match.
28. **Cost/Latency-Aware Model Router [S]** — pick model per task (local vs frontier) on a quality/cost/latency budget; cache aggressively.
29. **Episodic + Procedural + Semantic Memory Unification [S]** — one engine, three memory types, with consolidation/forgetting.

## VI. Safety, Security, Governance (research-lab discipline)
30. **Permission & Capability Model [S]** — explicit grants for dangerous actions; least-privilege per tool/agent.
31. **Hardened Sandbox (Firecracker/gVisor target) [S]** — real isolation for generated code and OMEGA empiricism.
32. **Action Audit Ledger [S]** — immutable log of every real-world action with rationale, for review/rollback.
33. **Containment Kernel for OMEGA [S/O]** — enforce that System 2 has zero direct world access.
34. **Reversibility / Undo Layer [J]** — snapshot before destructive actions; one-command rollback.

## VII. OMEGA Internal-Cognition Additions (System 2)
35. **Reasoning-Trace Recorder [O]** — capture every internal thought step for meta-evaluation and mutation.
36. **Adversarial Verifier Pool [O]** — N independent skeptics must fail to refute before a conclusion commits.
37. **Cross-Domain Isomorphism Miner [O]** — TDA over the knowledge graph to find structural analogies.
38. **Formal Proof Bridge (Lean4/Coq) [O]** — verify generated logic/math.
39. **Strategy Mutation + Benchmark Harness [O]** — evolve reasoning methods, score them on held-out hard tasks, hot-swap winners.

## VIII. Quietly Critical (easy to forget)
40. **Health/Telemetry Dashboard [J]** — unified, beyond the gesture dashboard.
41. **Config Hot-Reload [S]** — change behavior without restart.
42. **Graceful Degradation Matrix [S]** — every optional dep has a defined fallback (partially present already).
43. **Multi-Device Presence [J]** — extend `tools/sync` into a real presence/handoff layer across machines.
44. **Privacy Guardrails Enforcement [S]** — honor the profile's "never assume" list at the system level, not per-prompt.
