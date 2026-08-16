"""models.py - Public Data Models for Milestone 35 Abstract Concept Formation."""
from dataclasses import dataclass, field
from typing import Set, Dict, List, Any

@dataclass(frozen=True)
class StructuralMotif:
    """Represents a recurring graph topology (e.g. a cycle or clique)."""
    motif_id: str
    nodes_count: int
    edges_count: int
    # Canonical string representation of the graph structure for isomorphism checks
    structural_signature: str 
    # Example nodes that formed this motif
    exemplar_nodes: tuple = field(default_factory=tuple)


@dataclass(frozen=True)
class AbstractConcept:
    """A high-level concept wrapping a motif, tracking the domains it appears in."""
    concept_id: str
    name: str
    description: str
    motif: StructuralMotif
    instances: tuple = field(default_factory=tuple)  # entity IDs that are instances of this concept

