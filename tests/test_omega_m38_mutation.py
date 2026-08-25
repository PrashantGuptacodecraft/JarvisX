"""test_omega_m38_mutation.py - M38 restricted tests."""
import pytest
from omega_core.mutation.models import CognitiveStrategy
from omega_core.mutation.harness import BenchmarkHarness
from omega_core.mutation.engine import CognitiveMutationEngine

def test_mutation_engine_respects_restrictions():
    baseline = CognitiveStrategy("v1", (("logic", 1.0), ("creativity", 0.5)), True)
    engine = CognitiveMutationEngine(baseline)
    harness = BenchmarkHarness()
    
    # Run mutation
    engine.mutate_and_evaluate(harness, [])
    
    registry = engine.get_sealed_registry()
    
    # 1. Candidate must be generated and sealed
    assert len(registry.candidates) == 1
    candidate = registry.candidates[0]
    
    # 2. Must be a unique version
    assert candidate.version.startswith("v1-mut-")
    assert not candidate.is_baseline
    
    # 3. Must NOT automatically activate (engine.baseline should remain unchanged)
    assert engine.baseline == baseline
    
    # 4. Measurable improvement verified
    # Baseline logic = 1.0 (score 100)
    # Mutated logic = 1.1 (score 110) > 105
    assert candidate.get_weight("logic") == 1.1
