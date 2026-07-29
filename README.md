# JarvisX

JarvisX is an autonomous, AI-driven developer super-intelligence and workspace management system.

## Overview

JarvisX operates through a phased architecture designed to bring a high level of context-awareness, memory, and automated development capabilities:

- **Phase A — Event Bus**: A robust, thread-safe publish/subscribe system (SYNC/ASYNC) with built-in backpressure and coalescing mechanisms.
- **Phase B — State Manager**: A live World-State Engine and History Ledger that continuously monitors OS state, active windows, and hardware metrics.
- **Phase C — Memory Engine & Knowledge Graph**: A SQLite-backed triple-store that maintains an episodic and semantic graph of code dependencies, user habits, and historical execution traces.
- **Phase D — Developer Super-Intelligence**: Advanced automated development tools including autonomous test execution, test-gated refactoring (via LibCST/Rope), automatic regression bisection, knowledge-graph grounded code suggestions, and more.

## Development Status

This project is actively developed in "FAST DELIVERY MODE" following a rigorous capability milestone roadmap. Each component is thoroughly covered by automated test suites. 

Please see the `omega_context/` directory for detailed authoritative roadmaps and capability milestones.

## Testing

To run the full regression suite:
```bash
python -m pytest tests/
```
