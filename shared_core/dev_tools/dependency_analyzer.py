import ast
import json
import os
import re
from pathlib import Path
from typing import List, Optional
import tree_sitter

from .dependency_model import DependencyNode, DependencyType
from .symbol_model import SymbolLocation
from .tree_sitter_parser import TreeSitterParser

class DependencyAnalyzer:
    def __init__(self, root_dir: Path):
        self.root_dir = root_dir.resolve()
        self.ts_parser = TreeSitterParser(self.root_dir)
        
    def _normalize_path(self, path: Path) -> str:
        try:
            return str(path.resolve().relative_to(self.root_dir).as_posix())
        except ValueError:
            return str(path.as_posix())

    def analyze(self) -> List[DependencyNode]:
        deps = []
        deps.extend(self._analyze_python_deps())
        deps.extend(self._analyze_ts_deps())
        deps.extend(self._analyze_java_deps())
        return deps
        
    def store_in_kg(self, memory_manager, deps: List[DependencyNode]):
        # "stored in KG"
        for dep in deps:
            memory_manager.upsert_triple(
                subject=dep.source,
                predicate="depends_on",
                object=dep.target
            )

    def _analyze_python_deps(self) -> List[DependencyNode]:
        deps = []
        # External
        req_path = self.root_dir / "requirements.txt"
        if req_path.exists():
            try:
                content = req_path.read_text('utf-8')
                for line in content.splitlines():
                    line = line.split('#')[0].strip()
                    if not line:
                        continue
                    # Very basic pip parse: split by ==, >=, etc.
                    pkg = re.split(r'[=><~]+', line)[0].strip()
                    if pkg:
                        deps.append(DependencyNode(
                            source=self._normalize_path(req_path),
                            target=pkg,
                            dependency_type=DependencyType.EXTERNAL,
                            language="python"
                        ))
            except Exception:
                pass

        # Internal (AST)
        for py_file in self.root_dir.rglob("*.py"):
            norm_path = self._normalize_path(py_file)
            try:
                content = py_file.read_text('utf-8')
                tree = ast.parse(content)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            deps.append(DependencyNode(
                                source=norm_path,
                                target=alias.name,
                                dependency_type=DependencyType.INTERNAL,
                                language="python",
                                source_location={"line": node.lineno, "column": node.col_offset}
                            ))
                    elif isinstance(node, ast.ImportFrom):
                        if node.module:
                            deps.append(DependencyNode(
                                source=norm_path,
                                target=node.module,
                                dependency_type=DependencyType.INTERNAL,
                                language="python",
                                source_location={"line": node.lineno, "column": node.col_offset}
                            ))
            except Exception:
                pass
        return deps

    def _analyze_ts_deps(self) -> List[DependencyNode]:
        deps = []
        # External
        pkg_path = self.root_dir / "package.json"
        if pkg_path.exists():
            try:
                data = json.loads(pkg_path.read_text('utf-8'))
                for key in ["dependencies", "devDependencies"]:
                    if key in data:
                        for pkg in data[key]:
                            deps.append(DependencyNode(
                                source=self._normalize_path(pkg_path),
                                target=pkg,
                                dependency_type=DependencyType.EXTERNAL,
                                language="typescript"
                            ))
            except Exception:
                pass
                
        # Internal (Tree-sitter)
        for ext in ("*.ts", "*.tsx"):
            for ts_file in self.root_dir.rglob(ext):
                norm_path = self._normalize_path(ts_file)
                try:
                    source = ts_file.read_bytes()
                    lang = self.ts_parser.tsx_lang if ext == "*.tsx" else self.ts_parser.ts_lang
                    parser = tree_sitter.Parser(lang)
                    tree = parser.parse(source)
                    
                    def walk(node: tree_sitter.Node):
                        if node.type == "import_statement":
                            src_node = node.child_by_field_name("source")
                            if src_node:
                                tgt = src_node.text.decode('utf-8').strip('"\'')
                                # Identify internal vs external: internal starts with . or /
                                dtype = DependencyType.INTERNAL if tgt.startswith((".", "/")) else DependencyType.EXTERNAL
                                deps.append(DependencyNode(
                                    source=norm_path,
                                    target=tgt,
                                    dependency_type=dtype,
                                    language="typescript",
                                    source_location={
                                        "line": node.start_point.row + 1,
                                        "column": node.start_point.column
                                    }
                                ))
                        for child in node.children:
                            walk(child)
                            
                    walk(tree.root_node)
                except Exception:
                    pass
        return deps

    def _analyze_java_deps(self) -> List[DependencyNode]:
        deps = []
        # External: basic pom.xml parse (very simplified for milestone D3 external extraction)
        pom_path = self.root_dir / "pom.xml"
        if pom_path.exists():
            try:
                content = pom_path.read_text('utf-8')
                for match in re.finditer(r'<dependency>.*?<artifactId>(.*?)</artifactId>', content, re.DOTALL):
                    deps.append(DependencyNode(
                        source=self._normalize_path(pom_path),
                        target=match.group(1).strip(),
                        dependency_type=DependencyType.EXTERNAL,
                        language="java"
                    ))
            except Exception:
                pass
                
        # Internal (Tree-sitter)
        for java_file in self.root_dir.rglob("*.java"):
            norm_path = self._normalize_path(java_file)
            try:
                source = java_file.read_bytes()
                parser = tree_sitter.Parser(self.ts_parser.java_lang)
                tree = parser.parse(source)
                
                def walk(node: tree_sitter.Node):
                    if node.type == "import_declaration":
                        # find the scoped_identifier
                        for child in node.children:
                            if child.type == "scoped_identifier" or child.type == "identifier":
                                tgt = child.text.decode('utf-8')
                                deps.append(DependencyNode(
                                    source=norm_path,
                                    target=tgt,
                                    dependency_type=DependencyType.INTERNAL,
                                    language="java",
                                    source_location={
                                        "line": node.start_point.row + 1,
                                        "column": node.start_point.column
                                    }
                                ))
                    for child in node.children:
                        walk(child)
                        
                walk(tree.root_node)
            except Exception:
                pass
        return deps
