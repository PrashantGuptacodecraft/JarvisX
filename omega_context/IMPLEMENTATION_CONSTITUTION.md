# IMPLEMENTATION CONSTITUTION (HIGHEST LAW — OVERRIDES ALL EXPANSION)

> Ratified 2026-06-27. This document overrides any impulse toward architecture expansion.
> It governs every action until **all 79 capability milestones (Phases A–F) PASS**
> (`CAPABILITY_MILESTONES.md`). Architecture phase is CLOSED. Implementation phase is OPEN.

## The Eight Rules
1. **Architecture is frozen.** No new subsystems, no redesign, no new large features during implementation.
2. **Implementation only.** No philosophy changes, paradigm shifts, redesign cycles, or rewrites.
3. **Per-milestone discipline:** Design → Implement → Test → Validate → Lock → advance. No skipping phases or milestones.
4. **No idea drift.** A new advanced idea raised while milestones remain incomplete is **rejected from the roadmap** and parked in `FUTURE_RESEARCH.md`. The current roadmap is not modified.
5. **OMEGA untouched.** OMEGA stays frozen. Only JARVIS implementation is allowed.
6. **No shortcuts.** If a milestone fails, fix it before advancing. Never move past a failing milestone.
7. **Backward compatibility is mandatory.** Legacy boot, GUI, and headless must never break. Every change is additive/non-destructive.
8. **Execution discipline is the objective.** Not idea generation, not redesign. Execution only.

## Operating Mode
- Role: **principal engineer**, not architect.
- The architecture documents in `omega_context/` are the fixed spec. They are read, not rewritten (except to mark milestone status as PASS, and to append to `FUTURE_RESEARCH.md`).
- Order of work is fixed: Phase A → B → C → D → E → F, milestone by milestone.
- The only progress signal is milestone PASS via its acceptance test. No percentages.

## Milestone Lifecycle (Rule 3, in detail)
1. **Design** — confirm the already-specified design for the milestone (no new architecture).
2. **Implement** — write the minimal code to satisfy exactly that milestone.
3. **Test** — write/extend tests covering its acceptance criteria.
4. **Validate** — run tests + confirm legacy GUI/headless boot unchanged (Rule 7).
5. **Lock** — mark the milestone PASS in `CAPABILITY_MILESTONES.md`; do not revisit.

## Idea-Drift Protocol (Rule 4)
When a new capability/idea arrives mid-implementation:
- Do NOT integrate it. Do NOT alter the roadmap or current milestone.
- Append it verbatim (with date + context) to `FUTURE_RESEARCH.md`.
- Acknowledge it is parked, and continue the current milestone.

## Milestone Deferral Protocol (added 2026-06-29)
No milestone may be marked deferred (esp. "indefinitely") until a **dependency audit** is completed
and recorded in `DEPENDENCY_AUDIT.md`. For each milestone to defer, run:
1. Identify every future phase that depends on it.
2. List all **direct** dependencies (a milestone's acceptance test names it as an input).
3. List all **indirect** dependencies (could use it; chosen architecture doesn't require it).
4. Determine whether future architecture quality degrades if deferred.
5. Classify: **FOUNDATIONAL** (cannot defer — implement now) · **SUPPORTING** (defer only if a
   replacement exists) · **OPTIONAL** (defer safely).

No milestone is skipped without architecture-dependency proof. No engineering shortcuts.

This constitution is the highest law. It is enforced until the Phase A–F milestone gate is met.
