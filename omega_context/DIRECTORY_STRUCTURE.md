# PROJECT OMEGA: DIRECTORY STRUCTURE

The repository is structured for production-grade AGI research and isolation.

```text
omega/
├── core/
│   ├── supervisor/          # 60Hz daemon and main orchestration loops
│   ├── synthesis/           # Matrix for resolving agent debates
│   └── state/               # Global state tensor management
├── agents/
│   ├── meta_cognition/      # Supervisory oversight logic
│   ├── intuition/           # Heuristic/Latent pattern matchers
│   ├── logic/               # Symbolic reasoning implementations
│   ├── creativity/          # Divergent/high-entropy samplers
│   ├── skepticism/          # Adversarial critique models
│   └── abstraction/         # Dimensionality reduction models
├── memory/
│   ├── continuity/          # State serialization/deserialization logic
│   ├── episodic/            # Vector store connectors (Qdrant)
│   └── semantic/            # Graph store connectors (Neo4j)
├── runtime/
│   ├── orchestrator/        # Subprocess and thread pool management
│   ├── ipc/                 # Inter-process communication (gRPC buffers)
│   └── resource_allocator/  # VRAM and Compute budgeting
├── sandbox/
│   ├── firecracker/         # Micro-VM configuration and bridging
│   └── eval_environment/    # Isolated execution for Truth Verification
├── cognition/
│   ├── architectures/       # Dynamic neural network definitions
│   └── embeddings/          # Custom latent space projectors
├── mutation_engine/
│   ├── profiler/            # AST and execution profiling
│   ├── generator/           # LLM-based C++/Rust code generation
│   └── hot_swapper/         # Dynamic library reloading (FFI)
├── math_engine/
│   ├── lean_bridge/         # FFI to Lean 4 formal prover
│   └── coq_bridge/          # FFI to Coq formal prover
├── simulation/
│   ├── physics/             # Non-Euclidean environment generators
│   └── cellular_automata/   # Complex systems modeling
├── verification/
│   ├── empirical_tests/     # Automated test suite generators
│   └── formal_logic/        # Symbolic verification checks
├── kernel/
│   ├── isolation/           # SeL4/eBPF containment rules
│   └── hypervisor/          # Bare-metal interface abstractions
├── api/
│   ├── internal_grpc/       # Protobuf definitions for inter-agent comms
│   └── telemetry/           # Real-time monitoring metrics
├── config/
│   ├── hyperparameters/     # YAML/JSON tunable model parameters
│   └── system_limits/       # Absolute safety boundaries
├── tests/
│   ├── cognitive_benchmarks/# AGI reasoning evaluation suites
│   ├── containment_tests/   # Penetration tests on the sandbox
│   └── mutation_tests/      # Ensuring self-modification safety
└── docs/
    └── architecture/        # In-depth mathematical blueprints
```
