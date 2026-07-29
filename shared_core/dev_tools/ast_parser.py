import ast
import os
from pathlib import Path
from typing import List, Optional, Tuple, Any

from shared_core.dev_tools.symbol_model import SymbolType, SymbolLocation, SymbolNode

class PythonASTParser:
    """Parses Python files to extract symbol indexes (classes, functions, variables)."""
    
    def __init__(self, root_dir: Optional[Path] = None):
        self.root_dir = root_dir

    def _normalize_path(self, file_path: Path) -> str:
        if self.root_dir:
            try:
                return file_path.relative_to(self.root_dir).as_posix()
            except ValueError:
                pass
        return file_path.as_posix()
        
    def parse_file(self, file_path: Path) -> List[SymbolNode]:
        """Parse a single Python file and return its symbols."""
        if not file_path.exists() or file_path.suffix != '.py':
            return []
            
        try:
            source = file_path.read_text(encoding='utf-8')
            tree = ast.parse(source, filename=str(file_path))
        except (SyntaxError, UnicodeDecodeError):
            return []
            
        norm_path = self._normalize_path(file_path)
        return self._extract_symbols(tree, norm_path)

    def parse_directory(self, dir_path: Path) -> List[SymbolNode]:
        """Recursively parse a directory of Python files."""
        symbols = []
        if not dir_path.is_dir():
            return symbols
            
        if not self.root_dir:
            self.root_dir = dir_path
            
        for path in dir_path.rglob("*.py"):
            symbols.extend(self.parse_file(path))
            
        return symbols

    def _extract_symbols(self, tree: ast.AST, norm_path: str) -> List[SymbolNode]:
        symbols = []
        
        class SymbolVisitor(ast.NodeVisitor):
            def __init__(self):
                self.scope_stack: List[str] = []

            def _get_location(self, node: ast.AST) -> SymbolLocation:
                return SymbolLocation(
                    line=getattr(node, 'lineno', 1),
                    column=getattr(node, 'col_offset', 0),
                    end_line=getattr(node, 'end_lineno', None),
                    end_column=getattr(node, 'end_col_offset', None)
                )

            def _get_parent_scope(self) -> Optional[str]:
                return self.scope_stack[-1] if self.scope_stack else None

            def _get_qualified_name(self, name: str) -> str:
                return ".".join(self.scope_stack + [name])

            def _add_symbol(self, name: str, symbol_type: SymbolType, node: ast.AST, is_async: bool = False):
                symbols.append(SymbolNode(
                    name=name,
                    qualified_name=self._get_qualified_name(name),
                    symbol_type=symbol_type,
                    location=self._get_location(node),
                    file_path=norm_path,
                    language="python",
                    parent_scope=self._get_parent_scope(),
                    is_async=is_async
                ))

            def visit_ClassDef(self, node: ast.ClassDef):
                self._add_symbol(node.name, SymbolType.CLASS, node)
                self.scope_stack.append(node.name)
                self.generic_visit(node)
                self.scope_stack.pop()

            def visit_FunctionDef(self, node: ast.FunctionDef):
                self._add_symbol(node.name, SymbolType.FUNCTION, node, is_async=False)
                
                # Parameters
                self._visit_arguments(node.args)
                
                self.scope_stack.append(node.name)
                for stmt in node.body:
                    self.visit(stmt)
                self.scope_stack.pop()

            def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
                self._add_symbol(node.name, SymbolType.FUNCTION, node, is_async=True)
                
                # Parameters
                self._visit_arguments(node.args)
                
                self.scope_stack.append(node.name)
                for stmt in node.body:
                    self.visit(stmt)
                self.scope_stack.pop()
                
            def _visit_arguments(self, args: ast.arguments):
                def extract_arg(arg: ast.arg):
                    self._add_symbol(arg.arg, SymbolType.VARIABLE, arg)
                
                for a in args.posonlyargs: extract_arg(a)
                for a in args.args: extract_arg(a)
                for a in args.kwonlyargs: extract_arg(a)
                if args.vararg: extract_arg(args.vararg)
                if args.kwarg: extract_arg(args.kwarg)

            def _extract_targets(self, target: ast.AST):
                if isinstance(target, ast.Name):
                    self._add_symbol(target.id, SymbolType.VARIABLE, target)
                elif isinstance(target, (ast.Tuple, ast.List)):
                    for elt in target.elts:
                        self._extract_targets(elt)
                elif isinstance(target, ast.Starred):
                    self._extract_targets(target.value)
                # Ignore ast.Attribute, ast.Subscript etc (e.g. self.value = 10)

            def visit_Assign(self, node: ast.Assign):
                for target in node.targets:
                    self._extract_targets(target)
                self.generic_visit(node.value)

            def visit_AnnAssign(self, node: ast.AnnAssign):
                self._extract_targets(node.target)
                if node.value:
                    self.generic_visit(node.value)

            def visit_AugAssign(self, node: ast.AugAssign):
                # AugAssign e.g. x += 1
                self._extract_targets(node.target)
                self.generic_visit(node.value)

            def visit_NamedExpr(self, node: ast.NamedExpr):
                # Walrus operator e.g. (x := 1)
                self._extract_targets(node.target)
                self.generic_visit(node.value)
                
            def visit_For(self, node: ast.For):
                self._extract_targets(node.target)
                self.generic_visit(node)
                
            def visit_AsyncFor(self, node: ast.AsyncFor):
                self._extract_targets(node.target)
                self.generic_visit(node)

            def visit_With(self, node: ast.With):
                for item in node.items:
                    if item.optional_vars:
                        self._extract_targets(item.optional_vars)
                self.generic_visit(node)

            def visit_AsyncWith(self, node: ast.AsyncWith):
                for item in node.items:
                    if item.optional_vars:
                        self._extract_targets(item.optional_vars)
                self.generic_visit(node)

        visitor = SymbolVisitor()
        visitor.visit(tree)
        return symbols
