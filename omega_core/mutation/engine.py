"""engine.py - M38 Cognitive Mutation Engine."""
import uuid
from .models import CognitiveStrategy, SealedRegistryState
from .harness import BenchmarkHarness

class CognitiveMutationEngine:
    """Restricted mutation engine. Candidates are evaluated and sealed, NEVER automatically activated."""
    
    def __init__(self, baseline: CognitiveStrategy):
        if not baseline.is_baseline:
            raise ValueError("Must initialize with a baseline strategy")
        self.baseline = baseline
        self._sealed_registry = []
        
    def mutate_and_evaluate(self, harness: BenchmarkHarness, historical_traces: list) -> None:
        # Generate candidate safely
        new_weights = []
        for k, v in self.baseline.weights:
            # Deterministic simple mutation for demonstration
            new_weights.append((k, v * 1.1))
            
        candidate = CognitiveStrategy(
            version=f"{self.baseline.version}-mut-{uuid.uuid4().hex[:6]}",
            weights=tuple(new_weights),
            is_baseline=False
        )
        
        # Evaluate
        score = harness.evaluate(candidate, historical_traces)
        baseline_score = harness.evaluate(self.baseline, historical_traces)
        
        # Require measurable minimum improvement (e.g. 5% better)
        if score.passed and score.score > (baseline_score.score * 1.05):
            # Seal it. Do NOT activate.
            self._sealed_registry.append(candidate)
            
    def get_sealed_registry(self) -> SealedRegistryState:
        return SealedRegistryState(tuple(self._sealed_registry))
