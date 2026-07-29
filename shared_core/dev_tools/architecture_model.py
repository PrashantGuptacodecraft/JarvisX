from dataclasses import dataclass, asdict, field
from enum import Enum
from typing import Any, List, Dict, Set, Optional

class LayerAssignmentSource(str, Enum):
    EXPLICIT = "explicit"
    INFERRED = "inferred"
    UNCLASSIFIED = "unclassified"

@dataclass
class ArchitectureConfig:
    explicit_layers: Dict[str, str] = field(default_factory=dict)
    # paths -> layer_name
    
@dataclass
class ModuleNode:
    id: str
    layer: str
    assignment_source: LayerAssignmentSource

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "layer": self.layer,
            "assignment_source": self.assignment_source.value
        }

@dataclass
class DependencyEdge:
    source: str
    target: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

@dataclass
class ArchitectureSnapshot:
    modules: Dict[str, ModuleNode]
    internal_edges: List[DependencyEdge]
    external_edges: List[DependencyEdge]
    cycles: List[List[str]]
    explicit_violations: List[DependencyEdge]
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "modules": {k: v.to_dict() for k, v in self.modules.items()},
            "internal_edges": [e.to_dict() for e in self.internal_edges],
            "external_edges": [e.to_dict() for e in self.external_edges],
            "cycles": self.cycles,
            "explicit_violations": [e.to_dict() for e in self.explicit_violations]
        }

@dataclass
class DriftReport:
    added_modules: List[str]
    removed_modules: List[str]
    added_internal_edges: List[DependencyEdge]
    removed_internal_edges: List[DependencyEdge]
    added_external_edges: List[DependencyEdge]
    removed_external_edges: List[DependencyEdge]
    changed_layer_assignments: Dict[str, Dict[str, str]]
    added_cycles: List[List[str]]
    removed_cycles: List[List[str]]
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "added_modules": self.added_modules,
            "removed_modules": self.removed_modules,
            "added_internal_edges": [e.to_dict() for e in self.added_internal_edges],
            "removed_internal_edges": [e.to_dict() for e in self.removed_internal_edges],
            "added_external_edges": [e.to_dict() for e in self.added_external_edges],
            "removed_external_edges": [e.to_dict() for e in self.removed_external_edges],
            "changed_layer_assignments": self.changed_layer_assignments,
            "added_cycles": self.added_cycles,
            "removed_cycles": self.removed_cycles
        }
