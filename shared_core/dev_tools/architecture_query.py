from typing import List
from .architecture_model import ArchitectureSnapshot, DriftReport, DependencyEdge

class ArchitectureQuery:
    
    @staticmethod
    def narrate_snapshot(snapshot: ArchitectureSnapshot) -> str:
        lines = []
        
        # Summarize layers
        layers = {}
        for mod in snapshot.modules.values():
            layers[mod.layer] = layers.get(mod.layer, 0) + 1
            
        for layer, count in sorted(layers.items()):
            lines.append(f"Layer {layer} contains {count} modules.")
            
        # Summarize cycles
        if snapshot.cycles:
            for cycle in snapshot.cycles:
                lines.append(f"A dependency cycle exists between {', '.join(cycle)}.")
                
        # Total edges
        lines.append(f"Total internal dependencies: {len(snapshot.internal_edges)}")
        lines.append(f"Total external dependencies: {len(snapshot.external_edges)}")
        
        return "\n".join(lines)

    @staticmethod
    def compare(old: ArchitectureSnapshot, new: ArchitectureSnapshot) -> DriftReport:
        old_modules = set(old.modules.keys())
        new_modules = set(new.modules.keys())
        
        added_modules = sorted(list(new_modules - old_modules))
        removed_modules = sorted(list(old_modules - new_modules))
        
        changed_layer_assignments = {}
        for mod_id in old_modules.intersection(new_modules):
            old_layer = old.modules[mod_id].layer
            new_layer = new.modules[mod_id].layer
            if old_layer != new_layer:
                changed_layer_assignments[mod_id] = {"old": old_layer, "new": new_layer}
                
        old_internal = set((e.source, e.target) for e in old.internal_edges)
        new_internal = set((e.source, e.target) for e in new.internal_edges)
        added_internal = [DependencyEdge(source=s, target=t) for s, t in sorted(list(new_internal - old_internal))]
        removed_internal = [DependencyEdge(source=s, target=t) for s, t in sorted(list(old_internal - new_internal))]
        
        old_external = set((e.source, e.target) for e in old.external_edges)
        new_external = set((e.source, e.target) for e in new.external_edges)
        added_external = [DependencyEdge(source=s, target=t) for s, t in sorted(list(new_external - old_external))]
        removed_external = [DependencyEdge(source=s, target=t) for s, t in sorted(list(old_external - new_external))]
        
        old_cycles = set(tuple(c) for c in old.cycles)
        new_cycles = set(tuple(c) for c in new.cycles)
        added_cycles = [list(c) for c in sorted(list(new_cycles - old_cycles))]
        removed_cycles = [list(c) for c in sorted(list(old_cycles - new_cycles))]
        
        return DriftReport(
            added_modules=added_modules,
            removed_modules=removed_modules,
            added_internal_edges=added_internal,
            removed_internal_edges=removed_internal,
            added_external_edges=added_external,
            removed_external_edges=removed_external,
            changed_layer_assignments=changed_layer_assignments,
            added_cycles=added_cycles,
            removed_cycles=removed_cycles
        )

    @staticmethod
    def narrate_drift(drift: DriftReport) -> str:
        lines = []
        if drift.added_modules:
            lines.append(f"{len(drift.added_modules)} modules were added since the previous snapshot.")
        if drift.removed_modules:
            lines.append(f"{len(drift.removed_modules)} modules were removed since the previous snapshot.")
            
        if drift.added_internal_edges:
            lines.append(f"{len(drift.added_internal_edges)} internal dependencies were added.")
        if drift.removed_internal_edges:
            lines.append(f"{len(drift.removed_internal_edges)} internal dependencies were removed.")
            
        if drift.added_external_edges:
            lines.append(f"{len(drift.added_external_edges)} external dependencies were added.")
        if drift.removed_external_edges:
            lines.append(f"{len(drift.removed_external_edges)} external dependencies were removed.")
            
        if drift.changed_layer_assignments:
            lines.append(f"{len(drift.changed_layer_assignments)} layer assignments changed.")
            
        if drift.added_cycles:
            lines.append(f"{len(drift.added_cycles)} dependency cycles were introduced.")
        if drift.removed_cycles:
            lines.append(f"{len(drift.removed_cycles)} dependency cycles were removed.")
            
        if not lines:
            return "No architectural drift detected."
            
        return "\n".join(lines)
