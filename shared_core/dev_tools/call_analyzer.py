import ast
from pathlib import Path
from typing import List, Dict, Optional
import tree_sitter
from collections import defaultdict
import time
import datetime

from .call_model import CallNode, CodeRelationPredicate
from .symbol_model import SymbolNode, SymbolType
from .ast_parser import PythonASTParser
from .tree_sitter_parser import TreeSitterParser
from .event_models import DevEventEnvelope
from shared_core.event_bus.topics import PERCEPTION_DEV_CALL_GRAPH_GENERATED
from shared_core.event_bus.bus import EventBus

class CallAnalyzer:
    def __init__(self, root_dir: Path, event_bus: Optional[EventBus] = None):
        self.root_dir = root_dir.resolve()
        self.ts_parser = TreeSitterParser(self.root_dir)
        self.py_parser = PythonASTParser(self.root_dir)
        self.symbols_by_name = defaultdict(list)
        self.symbols_by_qname = {}
        self.event_bus = event_bus
        
    def _build_symbol_index(self):
        symbols = []
        symbols.extend(self.py_parser.parse_directory(self.root_dir))
        symbols.extend(self.ts_parser.parse_directory(self.root_dir))
        
        for sym in symbols:
            if sym.symbol_type == SymbolType.FUNCTION:
                self.symbols_by_name[sym.name].append(sym)
                self.symbols_by_qname[sym.qualified_name] = sym
                
    def analyze(self) -> List[CallNode]:
        start_time = time.time()
        self._build_symbol_index()
        calls = []
        calls.extend(self._analyze_python_calls())
        calls.extend(self._analyze_ts_calls())
        calls.extend(self._analyze_java_calls())
        
        if self.event_bus:
            duration_ms = (time.time() - start_time) * 1000
            env = DevEventEnvelope(
                schema_version=1,
                event_type=PERCEPTION_DEV_CALL_GRAPH_GENERATED,
                event_id=f"evt_{int(time.time()*1000)}",
                operation="call_analysis",
                request_id=None,
                repository_id=None,
                occurred_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                duration_ms=duration_ms,
                status="success",
                summary={"calls_count": len(calls)}
            )
            self.event_bus.publish(PERCEPTION_DEV_CALL_GRAPH_GENERATED, env.to_dict())
            
        return calls

    def _resolve_call(self, func_name: str, caller_qname: str, lang: str, line: int, col: int, calls: List[CallNode]):
        candidates = [s.qualified_name for s in self.symbols_by_name.get(func_name, [])]
        
        # Exact uniqueness check
        if len(candidates) == 1:
            callee_qname = candidates[0]
            resolved = True
        else:
            # Check if there is a match in the same class (e.g. self.foo)
            class_scope = ".".join(caller_qname.split(".")[:-1])
            if class_scope:
                potential_qname = f"{class_scope}.{func_name}"
                if potential_qname in self.symbols_by_qname:
                    callee_qname = potential_qname
                    resolved = True
                    candidates = [potential_qname]
                else:
                    callee_qname = func_name
                    resolved = False
            else:
                callee_qname = func_name
                resolved = False
                
        calls.append(CallNode(
            caller=caller_qname,
            callee=callee_qname,
            resolved=resolved,
            candidates=candidates,
            source_location={"line": line, "column": col},
            language=lang
        ))

    def _analyze_python_calls(self) -> List[CallNode]:
        calls = []
        for py_file in self.root_dir.rglob("*.py"):
            try:
                content = py_file.read_text('utf-8')
                tree = ast.parse(content)
                
                class CallVisitor(ast.NodeVisitor):
                    def __init__(self, analyzer, current_scope):
                        self.analyzer = analyzer
                        self.scope_stack = current_scope
                        
                    def visit_FunctionDef(self, node):
                        self.scope_stack.append(node.name)
                        self.generic_visit(node)
                        self.scope_stack.pop()
                        
                    def visit_AsyncFunctionDef(self, node):
                        self.scope_stack.append(node.name)
                        self.generic_visit(node)
                        self.scope_stack.pop()
                        
                    def visit_ClassDef(self, node):
                        self.scope_stack.append(node.name)
                        self.generic_visit(node)
                        self.scope_stack.pop()
                        
                    def visit_Call(self, node):
                        func_name = None
                        if isinstance(node.func, ast.Name):
                            func_name = node.func.id
                        elif isinstance(node.func, ast.Attribute):
                            func_name = node.func.attr
                        
                        if func_name and self.scope_stack:
                            caller_qname = ".".join(self.scope_stack)
                            self.analyzer._resolve_call(func_name, caller_qname, "python", node.lineno, node.col_offset, calls)
                            
                        self.generic_visit(node)
                        
                CallVisitor(self, []).visit(tree)
            except Exception:
                pass
        return calls

    def _walk_ts_tree(self, node: tree_sitter.Node, scope_stack: List[str], calls: List[CallNode], lang: str):
        added_scope = False
        if node.type in ("function_declaration", "method_definition", "arrow_function", "class_declaration"):
            name_node = node.child_by_field_name("name")
            if name_node:
                scope_stack.append(name_node.text.decode('utf-8'))
                added_scope = True
                
        if node.type == "call_expression":
            func_node = node.child_by_field_name("function")
            if func_node:
                func_name = None
                if func_node.type == "identifier":
                    func_name = func_node.text.decode('utf-8')
                elif func_node.type == "member_expression":
                    prop_node = func_node.child_by_field_name("property")
                    if prop_node:
                        func_name = prop_node.text.decode('utf-8')
                        
                if func_name and scope_stack:
                    caller_qname = ".".join(scope_stack)
                    self._resolve_call(func_name, caller_qname, lang, node.start_point.row + 1, node.start_point.column, calls)
                    
        for child in node.children:
            self._walk_ts_tree(child, scope_stack, calls, lang)
            
        if added_scope:
            scope_stack.pop()

    def _analyze_ts_calls(self) -> List[CallNode]:
        calls = []
        for ext in ("*.ts", "*.tsx"):
            for ts_file in self.root_dir.rglob(ext):
                try:
                    source = ts_file.read_bytes()
                    lang_name = "typescript"
                    lang = self.ts_parser.tsx_lang if ext == "*.tsx" else self.ts_parser.ts_lang
                    parser = tree_sitter.Parser(lang)
                    tree = parser.parse(source)
                    self._walk_ts_tree(tree.root_node, [], calls, lang_name)
                except Exception:
                    pass
        return calls

    def _walk_java_tree(self, node: tree_sitter.Node, scope_stack: List[str], calls: List[CallNode], lang: str):
        added_scope = False
        if node.type in ("class_declaration", "method_declaration", "constructor_declaration"):
            name_node = node.child_by_field_name("name")
            if name_node:
                scope_stack.append(name_node.text.decode('utf-8'))
                added_scope = True
                
        if node.type == "method_invocation":
            name_node = node.child_by_field_name("name")
            if name_node:
                func_name = name_node.text.decode('utf-8')
                if func_name and scope_stack:
                    caller_qname = ".".join(scope_stack)
                    self._resolve_call(func_name, caller_qname, lang, node.start_point.row + 1, node.start_point.column, calls)
                    
        for child in node.children:
            self._walk_java_tree(child, scope_stack, calls, lang)
            
        if added_scope:
            scope_stack.pop()

    def _analyze_java_calls(self) -> List[CallNode]:
        calls = []
        for java_file in self.root_dir.rglob("*.java"):
            try:
                source = java_file.read_bytes()
                parser = tree_sitter.Parser(self.ts_parser.java_lang)
                tree = parser.parse(source)
                self._walk_java_tree(tree.root_node, [], calls, "java")
            except Exception:
                pass
        return calls

    def store_in_kg(self, memory_manager, calls: List[CallNode]):
        for call in calls:
            if call.resolved:
                memory_manager.upsert_triple(
                    subject=call.caller,
                    predicate=CodeRelationPredicate.CALLS.value,
                    object=call.callee
                )
