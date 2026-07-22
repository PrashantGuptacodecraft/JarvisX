# DEPENDENCY AUDIT (MILESTONE DEFERRAL PROOF)

> Per the Milestone Deferral Protocol (2026-06-29): no milestone may be deferred indefinitely
> without a completed dependency audit. Each audited milestone runs Steps 1–5 and is classified
> **FOUNDATIONAL** (cannot defer), **SUPPORTING** (defer only if a replacement exists), or
> **OPTIONAL** (defer safely). Audited against the A–F milestone gate (`CAPABILITY_MILESTONES.md`)
> and the architecture docs. Append-only; re-audit if scope changes.

Legend for dependency strength: **DIRECT** = a milestone's acceptance test names this capability
as an input. **INDIRECT** = a milestone could use it but the chosen architecture does not require it.

---

## Audit A1 — B7: Screen UI-tree extraction (UIAutomation element tree)

**Capability:** element tree (role/bounds/text) of the foreground window via the vendored
UIAutomation bindings, published to `perception.screen.ui_tree`.

**STEP 1 — Future phases that depend on it**
- Phase C (Memory/KG): none.
- Phase D (Developer Super-Intelligence): `D6` VS Code monitoring — *candidate* consumer.
- Phase E (Tool Factory): none.
- Phase F (Predictive): `F3` contextual features — *candidate* consumer.
- Post-gate JARVIS "Continuous Screen Understanding" capability — true consumer (outside A–F).

**STEP 2 — Direct dependencies**
- **None within the A–F gate.** No milestone B–F lists `ui_tree` as a required input. D6's acceptance test specifies file-watch (`watchdog`) + LSP/linter diagnostics, **not** UIAutomation. F3 specifies "active app + recent bus events," not the UI tree.

**STEP 3 — Indirect dependencies**
- D6 (VS Code monitoring): could enrich with in-editor element awareness, but the chosen Phase-D architecture (file-watch + LSP) does not require it.
- F3 (predictive context): benefits from "which app/control is focused," but `perception.os.active_window` + `focused_process` (already live from B3/B6) supply the needed signal.

**STEP 4 — Architecture-quality degradation if deferred**
- Within A–F: **negligible.** Coarse screen understanding remains available (see replacement).
- Beyond A–F: the post-gate semantic screen-graph is *less rich* without UI-tree, but that system is not part of the current gate and is not blocked.

**STEP 5 — Classification: SUPPORTING**
- **Replacement exists (required for SUPPORTING deferral):**
  - `tools/vision/controller.py` — OCR (pytesseract/easyocr) reads on-screen text.
  - `tools/vision/modules/screen_agent.py` — vision-AI grid click/type (acts on screen without an element tree).
  - `perception.os.active_window` + `system.focused_process` (B3/B6) — foreground context in WorldState.
- These cover the functional needs of every A–F consumer. **→ Deferral ALLOWED (SUPPORTING + replacement present).**

---

## Audit A2 — B8: Window hierarchy model (open windows + z-order + titles)

**Capability:** enumerate open windows with z-order and titles, queryable from WorldState.

**STEP 1 — Future phases that depend on it**
- Phases C, D, E: none.
- Phase F (Predictive): `F3` contextual features — *candidate* (active window only).
- Post-gate JARVIS screen-understanding / multi-window reasoning — true consumer (outside A–F).

**STEP 2 — Direct dependencies**
- **None within the A–F gate.** No milestone consumes a full window list or z-order.

**STEP 3 — Indirect dependencies**
- F3 wants "active app." That is the *foreground* window only, already provided by
  `perception.os.active_window` (B3) and `system.focused_process` (B6). Full enumeration/z-order
  has **no consumer** in A–F.

**STEP 4 — Architecture-quality degradation if deferred**
- Within A–F: **none.** The single high-value signal (foreground window) is already captured and
  flowing into WorldState + the History Ledger. Multi-window enumeration adds no gate capability.

**STEP 5 — Classification: OPTIONAL**
- No A–F milestone depends on it (direct or indirect); the dominant signal (active window) is
  already provided. **→ Deferral SAFE (OPTIONAL).**

---

## Verdict Summary

| Milestone | Classification | Replacement / coverage | Deferral |
|---|---|---|---|
| **B7** Screen UI-tree | **SUPPORTING** | OCR + vision-AI ScreenAgent + active_window/focused_process | ✅ Allowed (replacement exists) |
| **B8** Window hierarchy | **OPTIONAL** | active_window / focused_process (foreground signal) | ✅ Safe (no gate dependency) |

**Conclusion:** Deferring B7 and B8 does **not** degrade the quality of Phases C/D/E/F. No
FOUNDATIONAL milestone is being deferred. Both deferrals are proven valid under the protocol.
Re-audit required if a future phase introduces a direct dependency on a full UI element tree or
multi-window z-order model (at which point B7 may reclassify toward FOUNDATIONAL).

---

## Audit A3 — C4: NetworkX Graph Projection Dependency

**Capability:** In-memory graph projection of the SQLite triple-store using the `networkx` library.

**STEP 1 — Future phases that depend on it**
- Phase C: C6, C7, C8, C9, C11 require traversing relational edges, paths, and neighbors.
- Phase D: D3 (Dependency graph), D4 (Call graph), D12 (Autonomous code suggestions) may leverage graph queries.
- Phase F: F1 (Predictor reads KG habit edges).

**STEP 2 — Direct dependencies**
- **C4 explicitly mandates `networkx`** as the implementation of the in-memory graph projection.

**STEP 3 — Indirect dependencies**
- None that bypass C4.

**STEP 4 — Architecture-quality degradation if deferred**
- **Critical.** Phases C, D, and F require a graph traversal and reasoning engine to fulfill their foundational AI goals. `networkx` is the prescribed dependency for this component. Deferring it blocks C4 and all subsequent dependent milestones.

**STEP 5 — Classification: FOUNDATIONAL**
- **No deferral allowed.** `networkx>=3.2.1` is a strict, explicit minimum-version constraint for C4. Added via established dependency tracking (`requirements.txt`).
