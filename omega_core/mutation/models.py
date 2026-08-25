"""models.py - M38 Cognitive Mutation Engine Models."""
from dataclasses import dataclass
from typing import Dict, Tuple

@dataclass(frozen=True)
class CognitiveStrategy:
    version: str
    weights: Tuple[Tuple[str, float], ...] # Immutably represent dict as tuple of pairs
    is_baseline: bool

    def get_weight(self, key: str) -> float:
        for k, v in self.weights:
            if k == key:
                return v
        return 0.0

@dataclass(frozen=True)
class BenchmarkScore:
    strategy_version: str
    score: float
    passed: bool

@dataclass(frozen=True)
class SealedRegistryState:
    candidates: Tuple[CognitiveStrategy, ...]
