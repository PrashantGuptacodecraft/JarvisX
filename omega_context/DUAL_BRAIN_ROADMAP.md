> ⛔ **STRATEGIC OVERRIDE (2026-06-27): OMEGA FROZEN.** All engineering goes to JARVIS MODE
> until every capability milestone in Phases **A–F** PASSES (see `CAPABILITY_MILESTONES.md` —
> the authoritative tracker). **Progress is tracked by capability milestones, NOT percentages.**
> No OMEGA (Phases 7–8 below) work until the A–F milestone gate is met.
> Active program = JARVIS Phases **A–F**, see `JARVIS_PHASE_A_PLAN.md`:
> A) Event Bus → B) State Manager + World-State → C) Memory + Knowledge Graph →
> D) Developer Super-Intelligence (flagship) → E) Tool Factory → F) Predictive Engine.
> The phases below remain the long-term map; OMEGA phases are deferred behind the 85% gate.

# DUAL-BRAIN IMPLEMENTATION ROADMAP (PRIORITY ORDERED)

> Ordering principle: build the **substrate** that makes everything else compound (event bus,
> shared core, continuity) → then the **highest-differentiation JARVIS** systems (perception
> continuity, developer super-intelligence) → then **OMEGA** cognition → then advanced/exotic.
> Non-destructive throughout (see `HYBRID_REPOSITORY_STRUCTURE.md` migration). **No coding yet.**

## PHASE 0 — Non-Destructive Re-Homing (foundation, low risk)
*Goal: dual-brain package skeleton without breaking the running system.*
1. Create `shared_core/`, `jarvis_mode/`, `omega_mode/` packages with re-export shims to current modules.
2. Stand up **Event Bus + Blackboard [S]** — the spine. (#1 priority capability.)
3. Extract **model_router**, **logging**, **config**, **sandbox**, **security** seeds into `shared_core/`.
4. Define the `WorldState` schema and the perception-tick contract.

## PHASE 1 — Continuous Perception Substrate (JARVIS "always aware")
*Goal: live, fused world-state on the bus.*
5. **OS Awareness daemon [J]** — continuous CPU/GPU/RAM/net/fs/clipboard/terminal/app-state → `WorldState`.
6. **Screen Understanding service [J]** — streaming OCR + **UIAutomation element tree** (use vendored bindings) + window hierarchy → semantic UI graph.
7. **Perception Tick Scheduler [S]** + backpressure.
8. **State Manager / Continuity [S]** — serialize/restore full live state (restart = pause).

## PHASE 2 — Memory Becomes Real (shared)
9. **Memory Engine → shared_core [S]** — move manager+RAG; unify episodic/procedural/semantic.
10. **Semantic Knowledge Graph [S]** — entities/relations over people/projects/files/habits.
11. **Habit & Temporal Pattern Learner [J]** + populate profile/preference learning.
12. Upgrade **Predictive Engine [J]** → proactive preload / app-open / anticipation off the KG + habits.

## PHASE 3 — Developer Super-Intelligence (biggest differentiator)
13. **Live Code Knowledge Graph [J]** — AST + imports + call graph + symbol index (tree-sitter/`ast`).
14. **Pre-Execution Mistake Detector [J]** — static/type/lint/dataflow before run.
15. **Autonomous Test Intelligence [J]** — generate/run/triage, red-green map, regression bisect.
16. **Refactoring Engine [J]** — test-gated AST transforms.
17. **VS Code / LSP Bridge [J]** + **Architecture Comprehension [J]** + **Missing-Feature Predictor [J]**.
18. **Auto Local Test-Environment Provisioner [J]**.

## PHASE 4 — Autonomy & Self-Extension
19. **Tool Factory [J]** — gap-detect → generate → sandbox-validate → permanent register.
20. **Skill Library [J]** — promote learned procedures to first-class skills.
21. **Autonomous Workflow Engine [J]** — long-horizon, resumable, checkpointed.
22. **Multi-Agent Swarm upgrade [J]** — 8 standing specialists (coding/browser/deploy/fs/api/debug/security/memory) on the bus + blackboard.
23. **Self-Healing Supervisor [J]**.

## PHASE 5 — Browser & Deployment Intelligence
24. **Browser Intel service [J]** — persistent Playwright; live tab/DOM/login/form/error observer; autonomous workflows.
25. **Deployment Intelligence [J]** — CI/build/deploy/log watch → auto-debug → auto-retry.

## PHASE 6 — Multimodal Depth & Safety
26. **Facial Identity Recognition [J]** + **Environmental/Scene Awareness [J]** + **Audio Scene Analysis [J]**.
27. Tighten **conversation-memory loop** (voice ↔ memory engine).
28. **Permission/Capability Model [S]**, **Action Audit Ledger [S]**, **Reversibility/Undo [J]**, **Privacy Guardrails enforcement [S]**.
29. **Hardened Sandbox [S]** (Firecracker/gVisor target).

## PHASE 7 — OMEGA MODE Bootstrap (System 2, greenfield)
*Only after shared core + continuity are solid.*
30. **Reasoning-Trace Recorder [O]** + **Continuity for cognition [O]**.
31. **Poly-Cognitive Engine [O]** — 5 role-engines (intuition/logic/creativity/skepticism/abstraction) as concurrent agents.
32. **Synthesis Matrix [O]** — debate → converge.
33. **Truth Verification Core [O]** + **Adversarial Verifier Pool [O]** + **Internal Scientific Method [O]**.
34. **Containment Kernel for OMEGA [S/O]** — enforce zero direct world access.

## PHASE 8 — OMEGA Advanced (exotic, last)
35. **Abstract Concept Formation [O]** (cross-domain isomorphism miner / TDA).
36. **Mathematical Discovery + Formal Proof Bridge (Lean4/Coq) [O]**.
37. **Imagination Physics Engine [O]**.
38. **Cognitive Mutation Engine [O]** — strategy mutation + benchmark harness + hot-swap.

## CROSS-CUTTING (continuous, every phase)
- **Cost/Latency-Aware Model Router [S]** upgrades as usage grows.
- **Health/Telemetry Dashboard [J]**, **Config Hot-Reload [S]**, **Graceful Degradation Matrix [S]**.
- Tests + audit ledger added alongside each subsystem (no subsystem ships untested).

## Priority Rationale (one line each)
- **Bus first** — every continuous/proactive feature depends on it.
- **Perception + continuity next** — the "aware, never-forgets" substrate is JARVIS's identity.
- **Developer intelligence** — highest personal value and the clearest "beyond Iron Man" edge.
- **Autonomy/self-extension** — compounding returns once perception+memory exist.
- **OMEGA last** — needs the shared core mature; highest risk, least immediate external value.
```
DONE: complete system mapping. NEXT (on your word): begin Phase 0 — bus + package skeleton.
```
