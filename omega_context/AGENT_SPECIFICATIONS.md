# PROJECT OMEGA: AGENT SPECIFICATIONS

This document defines the strict operational parameters for the primary autonomous agents composing the Poly-Cognitive Engine and auxiliary cores.

---

### 1. Meta-Cognition Supervisor
*   **Responsibilities**: Oversee the reasoning pathways of all internal agents. Detect logical fallacies, cognitive loops, and processing inefficiencies. Halts and reroutes flawed thinking.
*   **Internal APIs**: `read_agent_activation_state()`, `force_context_reset()`, `inject_reasoning_heuristic()`
*   **Expected Inputs**: Live token-by-token output streams and attention heatmaps from the Poly-Cognitive engines.
*   **Outputs**: `SIG_HALT`, `SIG_CONTINUE`, `SIG_MUTATE_PROMPT`.
*   **Memory Usage**: High context window; requires historical trajectories of past reasoning failures.
*   **Communication Protocol**: gRPC over shared memory, intercepting message buses globally.

---

### 2. Intuition Agent
*   **Responsibilities**: Generate immediate, unverified approximations and pattern-matches for a given problem. (System 1 thinking).
*   **Internal APIs**: `query_semantic_latent_space()`
*   **Expected Inputs**: Raw problem statements or continuous state changes.
*   **Outputs**: Dense vectors of probable solutions without logical justification.
*   **Memory Usage**: Extreme speed, low context window.
*   **Communication Protocol**: High-bandwidth asynchronous streams to the Synthesis Matrix.

---

### 3. Logic Agent
*   **Responsibilities**: Execute rigorous, step-by-step deterministic reasoning. Break problems down into formal symbolic logic. (System 2 thinking).
*   **Internal APIs**: `invoke_symbolic_solver()`, `validate_ast()`
*   **Expected Inputs**: Problem statements and intuition vectors to be formalized.
*   **Outputs**: Step-by-step proofs, executable code, verifiable truth tables.
*   **Memory Usage**: Medium speed, very large context window.
*   **Communication Protocol**: Strictly typed JSON/gRPC definitions.

---

### 4. Creativity Agent
*   **Responsibilities**: Generate highly divergent, non-linear, and radical approaches to a problem by injecting entropy into the reasoning process.
*   **Internal APIs**: `sample_imagination_engine()`, `inject_noise_vector()`
*   **Expected Inputs**: Widespread context from the Abstract Concept Formation engine.
*   **Outputs**: Unorthodox hypotheses, alien architectures.
*   **Memory Usage**: High VRAM consumption due to high-temperature and top-p sampling thresholds.
*   **Communication Protocol**: Broadcasts asynchronous "sparks" to the Synthesis Matrix.

---

### 5. Skepticism Agent
*   **Responsibilities**: Act strictly as a highly regularized adversary. Its sole reward function is successfully finding mathematical or logical flaws in the outputs of the Logic and Creativity agents.
*   **Internal APIs**: `invoke_falsification_suite()`
*   **Expected Inputs**: Proposed solutions, proofs, and hypotheses from sister agents.
*   **Outputs**: Boolean rejection flags, detailed critique traces, counter-examples.
*   **Memory Usage**: Highly optimized for context-retrieval to find contradictions in past memory.
*   **Communication Protocol**: Blocking interceptor protocol. No output passes synthesis without surviving the Skepticism Agent.

---

### 6. Abstraction Agent
*   **Responsibilities**: Compress highly detailed problem spaces into generalized principles. Strip away domain-specific terminology to find the underlying structural topology.
*   **Internal APIs**: `apply_dimensionality_reduction()`, `map_isomorphism()`
*   **Expected Inputs**: Resolved outputs from the Truth Verification Core.
*   **Outputs**: Highly compressed heuristic models and abstract axioms.
*   **Memory Usage**: Low transient memory, high write-throughput to long-term graph databases.
*   **Communication Protocol**: Unidirectional updates to the Global Semantic Graph.

---

### 7. Truth Verification Agent
*   **Responsibilities**: Translate synthesized hypotheses into empirical test simulations or formal mathematical proofs. Execute tests and measure results.
*   **Internal APIs**: `spin_micro_simulation()`, `run_lean4_tactic()`
*   **Expected Inputs**: Unified hypothesis from the Poly-Cognitive Engine.
*   **Outputs**: Empirical success/failure matrices, rigorous proof validations.
*   **Memory Usage**: Requires massive external disk and CPU virtualization capabilities.
*   **Communication Protocol**: Interface layer bridging neural space and deterministic execution sandboxes.
