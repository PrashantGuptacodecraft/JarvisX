from pathlib import Path
from typing import List, Dict, Set
from .architecture_model import (
    ArchitectureConfig, ModuleNode, DependencyEdge, 
    ArchitectureSnapshot, LayerAssignmentSource
)
from .dependency_analyzer import DependencyAnalyzer
from .dependency_model import DependencyType

class ArchitectureAnalyzer:
    def __init__(self, root_dir: Path):
        self.root_dir = root_dir.resolve()
        self.dep_analyzer = DependencyAnalyzer(self.root_dir)

    def _normalize_path(self, path: Path) -> str:
        try:
            return str(path.resolve().relative_to(self.root_dir).as_posix())
        except ValueError:
            return str(path.as_posix())

    def _assign_layer(self, norm_path: str, config: ArchitectureConfig) -> tuple[str, LayerAssignmentSource]:
        for explicit_prefix, layer_name in config.explicit_layers.items():
            if norm_path.startswith(explicit_prefix):
                return layer_name, LayerAssignmentSource.EXPLICIT
                
        parts = norm_path.split("/")
        if len(parts) == 1:
            return "root", LayerAssignmentSource.INFERRED
        elif len(parts) > 1:
            first_seg = parts[0]
            if first_seg:
                return first_seg, LayerAssignmentSource.INFERRED
                
        return "unclassified", LayerAssignmentSource.UNCLASSIFIED

    def _resolve_target_to_file(self, target: str, source_file: str) -> str:
        # Simple heuristic to map Python/TS import targets back to file paths if possible
        if target.startswith((".", "/")):
            # It's likely TS relative import
            # resolve relative to source_file directory
            src_dir = Path(source_file).parent
            # handle relative
            # For simplicity, we just use the raw string if we can't resolve it cleanly
            # A real resolver would use full path math.
            pass
            
        # For Python: target "shared_core.utils" -> "shared_core/utils.py" or "shared_core/utils/__init__.py"
        py_path = target.replace(".", "/") + ".py"
        py_init = target.replace(".", "/") + "/__init__.py"
        if (self.root_dir / py_path).exists():
            return py_path
        if (self.root_dir / py_init).exists():
            return py_init
            
        # Return the original target if we can't resolve it to a file
        # We will strip quotes just in case
        return target.strip('"\'')

    def analyze(self, config: ArchitectureConfig = None) -> ArchitectureSnapshot:
        if config is None:
            config = ArchitectureConfig()
            
        deps = self.dep_analyzer.analyze()
        
        modules: Dict[str, ModuleNode] = {}
        internal_edges: Set[tuple[str, str]] = set()
        external_edges: Set[tuple[str, str]] = set()
        
        # Discover all repository files
        for ext in ("*.py", "*.ts", "*.tsx", "*.java"):
            for f in self.root_dir.rglob(ext):
                norm = self._normalize_path(f)
                layer, source = self._assign_layer(norm, config)
                modules[norm] = ModuleNode(id=norm, layer=layer, assignment_source=source)
                
        # Process dependencies
        for dep in deps:
            if dep.dependency_type == DependencyType.INTERNAL:
                resolved_target = self._resolve_target_to_file(dep.target, dep.source)
                
                # Make sure the resolved target is in our modules map
                if resolved_target not in modules:
                    layer, source = self._assign_layer(resolved_target, config)
                    modules[resolved_target] = ModuleNode(id=resolved_target, layer=layer, assignment_source=source)
                    
                internal_edges.add((dep.source, resolved_target))
            else:
                external_edges.add((dep.source, dep.target))
                
        internal_edges_list = [DependencyEdge(source=s, target=t) for s, t in sorted(internal_edges)]
        external_edges_list = [DependencyEdge(source=s, target=t) for s, t in sorted(external_edges)]
        
        cycles = self._find_cycles(internal_edges_list)
        
        return ArchitectureSnapshot(
            modules=modules,
            internal_edges=internal_edges_list,
            external_edges=external_edges_list,
            cycles=cycles,
            explicit_violations=[] # To be implemented if config has allowed_dependencies
        )

    def _find_cycles(self, internal_edges: List[DependencyEdge]) -> List[List[str]]:
        from collections import defaultdict
        
        graph = defaultdict(list)
        for edge in internal_edges:
            graph[edge.source].append(edge.target)
            
        index = 0
        indices = {}
        lowlink = {}
        on_stack = set()
        stack = []
        cycles = []
        
        def strongconnect(v):
            nonlocal index
            indices[v] = index
            lowlink[v] = index
            index += 1
            stack.append(v)
            on_stack.add(v)
            
            for w in graph[v]:
                if w not in indices:
                    strongconnect(w)
                    lowlink[v] = min(lowlink[v], lowlink[w])
                elif w in on_stack:
                    lowlink[v] = min(lowlink[v], indices[w])
                    
            if lowlink[v] == indices[v]:
                scc = []
                while True:
                    w = stack.pop()
                    on_stack.remove(w)
                    scc.append(w)
                    if w == v:
                        break
                if len(scc) > 1 or (len(scc) == 1 and scc[0] in graph[scc[0]]):
                    scc.sort()
                    cycles.append(scc)
                    
        for v in sorted(list(graph.keys())):
            if v not in indices:
                strongconnect(v)
                
        # Deduplicate and sort cycles deterministically
        unique_cycles = []
        for c in cycles:
            if c not in unique_cycles:
                unique_cycles.append(c)
        unique_cycles.sort(key=lambda c: c[0])
        return unique_cycles
