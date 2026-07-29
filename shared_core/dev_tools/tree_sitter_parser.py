import os
from pathlib import Path
from typing import List, Optional

import tree_sitter
import tree_sitter_typescript as ts_ts
import tree_sitter_java as ts_java

from shared_core.dev_tools.symbol_model import SymbolNode, SymbolType, SymbolLocation

class TreeSitterParser:
    """Parses Java and TypeScript files using tree-sitter into SymbolNode."""

    def __init__(self, root_dir: Optional[Path] = None):
        self.root_dir = root_dir
        self.ts_lang = tree_sitter.Language(ts_ts.language_typescript())
        self.tsx_lang = tree_sitter.Language(ts_ts.language_tsx())
        self.java_lang = tree_sitter.Language(ts_java.language())

    def _normalize_path(self, file_path: Path) -> str:
        if self.root_dir:
            try:
                return file_path.relative_to(self.root_dir).as_posix()
            except ValueError:
                pass
        return file_path.as_posix()

    def parse_file(self, file_path: Path) -> List[SymbolNode]:
        if not file_path.exists():
            return []

        ext = file_path.suffix.lower()
        if ext == '.ts':
            lang = self.ts_lang
        elif ext == '.tsx':
            lang = self.tsx_lang
        elif ext == '.java':
            lang = self.java_lang
        else:
            return []

        try:
            source = file_path.read_bytes()
        except OSError:
            return []

        parser = tree_sitter.Parser(lang)
        tree = parser.parse(source)
        
        norm_path = self._normalize_path(file_path)
        
        if ext in ('.ts', '.tsx'):
            return self._extract_ts_symbols(tree.root_node, norm_path, source)
        else:
            return self._extract_java_symbols(tree.root_node, norm_path, source)

    def parse_directory(self, dir_path: Path) -> List[SymbolNode]:
        symbols = []
        if not dir_path.is_dir():
            return symbols

        if not self.root_dir:
            self.root_dir = dir_path

        for ext in ("*.ts", "*.tsx", "*.java"):
            for path in dir_path.rglob(ext):
                symbols.extend(self.parse_file(path))

        return symbols
        
    def _get_location(self, node: tree_sitter.Node) -> SymbolLocation:
        return SymbolLocation(
            line=node.start_point.row + 1,
            column=node.start_point.column,
            end_line=node.end_point.row + 1,
            end_column=node.end_point.column
        )

    # -- TypeScript Extraction --
    def _extract_ts_symbols(self, root_node: tree_sitter.Node, file_path: str, source: bytes) -> List[SymbolNode]:
        symbols = []
        
        def walk(node: tree_sitter.Node, scope_stack: List[str]):
            # Classes
            if node.type in ("class_declaration", "interface_declaration", "enum_declaration"):
                name_node = node.child_by_field_name("name")
                if name_node:
                    name = name_node.text.decode('utf-8')
                    qname = ".".join(scope_stack + [name])
                    parent = scope_stack[-1] if scope_stack else None
                    symbols.append(SymbolNode(
                        name=name, qualified_name=qname, symbol_type=SymbolType.CLASS,
                        location=self._get_location(node), file_path=file_path, language="typescript", parent_scope=parent
                    ))
                    scope_stack.append(name)
                    for child in node.children:
                        walk(child, scope_stack)
                    scope_stack.pop()
                    return

            # Functions / Methods
            elif node.type in ("function_declaration", "method_definition", "arrow_function"):
                name = None
                is_async = False
                
                # Check for async modifier
                for child in node.children:
                    if child.type == "async":
                        is_async = True
                        break
                        
                name_node = node.child_by_field_name("name")
                if name_node:
                    name = name_node.text.decode('utf-8')
                elif node.type == "arrow_function":
                    # Arrow functions might be assigned to a variable, the variable name is captured elsewhere.
                    # We can skip naming anonymous arrows unless we want to try to infer.
                    pass
                
                if name:
                    qname = ".".join(scope_stack + [name])
                    parent = scope_stack[-1] if scope_stack else None
                    symbols.append(SymbolNode(
                        name=name, qualified_name=qname, symbol_type=SymbolType.FUNCTION,
                        location=self._get_location(node), file_path=file_path, language="typescript", parent_scope=parent, is_async=is_async
                    ))
                    scope_stack.append(name)
                
                # Parameters
                params_node = node.child_by_field_name("parameters")
                if params_node:
                    for child in params_node.children:
                        if child.type in ("required_parameter", "optional_parameter"):
                            pat = child.child_by_field_name("pattern")
                            if pat and pat.type == "identifier":
                                p_name = pat.text.decode('utf-8')
                                pqname = ".".join(scope_stack + [p_name])
                                parent = scope_stack[-1] if scope_stack else None
                                symbols.append(SymbolNode(
                                    name=p_name, qualified_name=pqname, symbol_type=SymbolType.VARIABLE,
                                    location=self._get_location(child), file_path=file_path, language="typescript", parent_scope=parent
                                ))
                
                for child in node.children:
                    if child.type == "statement_block":
                        walk(child, scope_stack)
                        
                if name:
                    scope_stack.pop()
                return

            # Variables
            elif node.type in ("lexical_declaration", "variable_declaration"):
                for child in node.children:
                    if child.type == "variable_declarator":
                        name_node = child.child_by_field_name("name")
                        if name_node and name_node.type == "identifier":
                            name = name_node.text.decode('utf-8')
                            qname = ".".join(scope_stack + [name])
                            parent = scope_stack[-1] if scope_stack else None
                            symbols.append(SymbolNode(
                                name=name, qualified_name=qname, symbol_type=SymbolType.VARIABLE,
                                location=self._get_location(name_node), file_path=file_path, language="typescript", parent_scope=parent
                            ))
                        elif name_node and name_node.type in ("object_pattern", "array_pattern"):
                            # Simple destructuring support could go here
                            pass

            for child in node.children:
                walk(child, scope_stack)

        walk(root_node, [])
        return symbols

    # -- Java Extraction --
    def _extract_java_symbols(self, root_node: tree_sitter.Node, file_path: str, source: bytes) -> List[SymbolNode]:
        symbols = []
        
        def walk(node: tree_sitter.Node, scope_stack: List[str]):
            # Classes
            if node.type in ("class_declaration", "interface_declaration", "enum_declaration"):
                name_node = node.child_by_field_name("name")
                if name_node:
                    name = name_node.text.decode('utf-8')
                    qname = ".".join(scope_stack + [name])
                    parent = scope_stack[-1] if scope_stack else None
                    symbols.append(SymbolNode(
                        name=name, qualified_name=qname, symbol_type=SymbolType.CLASS,
                        location=self._get_location(node), file_path=file_path, language="java", parent_scope=parent
                    ))
                    scope_stack.append(name)
                    for child in node.children:
                        walk(child, scope_stack)
                    scope_stack.pop()
                    return

            # Functions / Methods
            elif node.type in ("method_declaration", "constructor_declaration"):
                name_node = node.child_by_field_name("name")
                if name_node:
                    name = name_node.text.decode('utf-8')
                    qname = ".".join(scope_stack + [name])
                    parent = scope_stack[-1] if scope_stack else None
                    symbols.append(SymbolNode(
                        name=name, qualified_name=qname, symbol_type=SymbolType.FUNCTION,
                        location=self._get_location(node), file_path=file_path, language="java", parent_scope=parent
                    ))
                    scope_stack.append(name)
                    
                    # Parameters
                    params_node = node.child_by_field_name("parameters")
                    if params_node:
                        for child in params_node.children:
                            if child.type == "formal_parameter":
                                p_name_node = child.child_by_field_name("name")
                                if p_name_node:
                                    p_name = p_name_node.text.decode('utf-8')
                                    pqname = ".".join(scope_stack + [p_name])
                                    symbols.append(SymbolNode(
                                        name=p_name, qualified_name=pqname, symbol_type=SymbolType.VARIABLE,
                                        location=self._get_location(p_name_node), file_path=file_path, language="java", parent_scope=name
                                    ))
                                    
                    for child in node.children:
                        walk(child, scope_stack)
                    scope_stack.pop()
                    return

            # Variables
            elif node.type in ("local_variable_declaration", "field_declaration"):
                for child in node.children:
                    if child.type == "variable_declarator":
                        name_node = child.child_by_field_name("name")
                        if name_node:
                            name = name_node.text.decode('utf-8')
                            qname = ".".join(scope_stack + [name])
                            parent = scope_stack[-1] if scope_stack else None
                            symbols.append(SymbolNode(
                                name=name, qualified_name=qname, symbol_type=SymbolType.VARIABLE,
                                location=self._get_location(name_node), file_path=file_path, language="java", parent_scope=parent
                            ))

            for child in node.children:
                walk(child, scope_stack)

        walk(root_node, [])
        return symbols
