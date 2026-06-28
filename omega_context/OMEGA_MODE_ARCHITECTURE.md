# OMEGA MODE ARCHITECTURE (SYSTEM 2 — INTERNAL COGNITIVE PERFECTION)

> OMEGA is the second brain. It does NOT act on the world. Its sole purpose is recursive
> improvement of reasoning quality. It is sandbox-contained and reaches the world only by
> handing verified results to JARVIS over the event bus. The original OMEGA docs
> (`SYSTEM_ARCHITECTURE.md`, `AGENT_SPECIFICATIONS.md`, `IMPLEMENTATION_ROADMAP.md`,
> `TECH_STACK.md`, `MASTER_CONSTITUTION.md`, `DEVELOPMENT_PROTOCOL.md`) now describe THIS
> system only — they are System 2's detailed spec. This file is the System-2 overview and
> its interface to System 1.

## I. Current State: 0% — Nothing Built
No file in the repository implements any OMEGA subsystem today. OMEGA is entirely greenfield.
All OMEGA work is **new** (Category D). Nothing existing is reclassified into OMEGA.

## II. OMEGA Subsystems (all NEW)

| # | Subsystem | Purpose | Spec ref |
|---|-----------|---------|----------|
| 1 | **Meta-Cognition Layer** | Evaluate quality of its own reasoning; halt/reroute flawed thought | AGENT_SPECIFICATIONS §1 |
| 2 | **Poly-Cognitive Processing** | 5 concurrent engines: intuition, logic, creativity, skepticism, abstraction | SYSTEM_ARCHITECTURE §2 |
| 3 | **Synthesis Matrix** | Force the 5 engines to debate and converge | IMPLEMENTATION_ROADMAP Phase 3 |
| 4 | **Truth Verification Core** | Adversarially attack every conclusion before acceptance | SYSTEM_ARCHITECTURE §3 |
| 5 | **Cognitive Mutation Engine** | Invent better reasoning methods (AST/genetic over its own strategies) | SYSTEM_ARCHITECTURE §4 |
| 6 | **Abstract Concept Formation** | Discover hidden isomorphisms across unrelated domains | SYSTEM_ARCHITECTURE §5 |
| 7 | **Imagination Physics Engine** | Simulate impossible worlds to derive alien paradigms | SYSTEM_ARCHITECTURE §6 |
| 8 | **Mathematical Discovery Engine** | Invent mathematics/algorithms; Lean4/Coq verification | SYSTEM_ARCHITECTURE §7 |
| 9 | **Internal Scientific Method Engine** | Generate hypotheses, design experiments, attack own conclusions | MASTER_CONSTITUTION §III |
| 10 | **Consciousness Continuity Layer** | Serialize/restore exact cognitive state (uses shared state manager) | SYSTEM_ARCHITECTURE §8 |

## III. Cognitive Flow

```
   objective (self-generated or handed from JARVIS via bus)
        │
        ▼
   META-COGNITION SUPERVISOR ──monitors──┐
        │ routes objective                │
        ▼                                 │
   POLY-COGNITIVE ENGINE                  │
   ┌──────────┬───────┬──────────┬───────┴────┬────────────┐
   │intuition │ logic │creativity│ skepticism │ abstraction│  (concurrent)
   └────┬─────┴───┬───┴────┬─────┴─────┬──────┴─────┬──────┘
        └─────────┴────────┴── SYNTHESIS MATRIX (debate→converge)
                              │ unified hypothesis
                              ▼
                     TRUTH VERIFICATION CORE  ◀── scientific method engine
                     (adversarial attack + micro-sims + Lean4/Coq)
                              │ survives?
                  ┌───────────┴────────────┐
              rejected → back to engines   accepted → commit to continuity
                                            │
                              CONGNITIVE MUTATION ENGINE
                              (improve the reasoning method itself)
                              ABSTRACT CONCEPT / IMAGINATION PHYSics
                              (feed new paradigms back to creativity)
```

## IV. Interface to JARVIS (the only bridge)
- **Inbound:** JARVIS publishes hard reasoning problems and its own decision traces to a `cognition.request` / `cognition.trace` topic. OMEGA may consume these to improve or to critique.
- **Outbound:** OMEGA publishes verified heuristics, improved strategies, or solved results to `cognition.result`. JARVIS (and its planner/agents) may adopt them. OMEGA performs **no** I/O, file mutation, network, or process control directly — enforced by the shared security/containment layer.
- **Latency contract:** OMEGA explicitly trades latency for quality (DEVELOPMENT_PROTOCOL §4). JARVIS must treat OMEGA as async and never block real-world action on it.

## V. Containment (inherited, non-negotiable)
OMEGA runs behind the shared **sandbox** + **security layer**. No `os.system`/`subprocess`/network/file-mutation from any OMEGA engine. All empirical tests run in isolated sandboxes mediated by the Truth Verification Core. See DEVELOPMENT_PROTOCOL §5.

## VI. Build Order
OMEGA is built per the existing 7-phase `IMPLEMENTATION_ROADMAP.md`, but **deferred behind JARVIS upgrades and shared-core extraction** per `DUAL_BRAIN_ROADMAP.md`. Minimum first slice: Continuity (shared) → Poly-Cognitive (5 engines as LLM-role agents) → Synthesis → Truth Verification. Math/mutation/imagination engines come last.
