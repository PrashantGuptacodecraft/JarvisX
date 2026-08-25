"""bridge.py - Isolated Symbolic Proof Backend using Z3."""
import time
import ast
from typing import Any
import z3
from .models import SymbolicTheorem, ProofResult, ProofOutcome

class SafeZ3Parser:
    """Safely parses a restricted propositional logic subset into Z3 booleans.
    Supports: And(), Or(), Not(), Implies(), Equiv(), and variables.
    NO arbitrary execution."""
    
    def __init__(self):
        self.vars = {}

    def parse(self, expr_str: str) -> Any:
        try:
            tree = ast.parse(expr_str, mode='eval')
            return self._visit(tree.body)
        except Exception:
            raise ValueError(f"Invalid symbolic expression: {expr_str}")

    def _visit(self, node: ast.AST) -> Any:
        if isinstance(node, ast.Name):
            var_name = node.id
            if var_name not in self.vars:
                self.vars[var_name] = z3.Bool(var_name)
            return self.vars[var_name]
        
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise ValueError("Unsupported function call")
            func_name = node.func.id
            args = [self._visit(a) for a in node.args]
            
            if func_name == "And": return z3.And(*args)
            if func_name == "Or": return z3.Or(*args)
            if func_name == "Not": 
                if len(args) != 1: raise ValueError("Not requires 1 argument")
                return z3.Not(args[0])
            if func_name == "Implies":
                if len(args) != 2: raise ValueError("Implies requires 2 arguments")
                return z3.Implies(args[0], args[1])
            if func_name == "Equiv":
                if len(args) != 2: raise ValueError("Equiv requires 2 arguments")
                return args[0] == args[1]
                
            raise ValueError(f"Unsupported operator: {func_name}")
            
        raise ValueError(f"Unsupported AST node: {type(node)}")

class FormalProofBridge:
    """Isolated M36 bridge to the formal prover."""
    
    def verify_theorem(self, theorem: SymbolicTheorem, timeout_ms: int = 1000) -> ProofResult:
        t0 = time.time()
        
        # Z3 solver configuration
        solver = z3.Solver()
        solver.set("timeout", timeout_ms)
        
        parser = SafeZ3Parser()
        
        try:
            # Parse assumptions
            for assumption in theorem.assumptions:
                z3_expr = parser.parse(assumption)
                solver.add(z3_expr)
                
            # Parse conclusion
            z3_conclusion = parser.parse(theorem.conclusion)
            
            # To prove a conclusion C from assumptions A, we check if A ^ Not(C) is UNSAT
            solver.add(z3.Not(z3_conclusion))
            
            res = solver.check()
            
            if res == z3.unsat:
                outcome = ProofOutcome.PROVED
                model_dump = None
            elif res == z3.sat:
                outcome = ProofOutcome.DISPROVED
                # Extract counter-example safely
                model = solver.model()
                model_dump = str(model).replace('\n', ' ')
            else:
                outcome = ProofOutcome.UNKNOWN
                model_dump = str(solver.reason_unknown())
                
        except ValueError as e:
            # Parse error (unsupported DSL)
            outcome = ProofOutcome.UNSUPPORTED
            model_dump = str(e)
        except Exception as e:
            outcome = ProofOutcome.UNKNOWN
            model_dump = f"Solver crashed: {str(e)[:100]}"
            
        duration_ms = (time.time() - t0) * 1000.0
        
        return ProofResult(
            theorem_id=theorem.theorem_id,
            outcome=outcome,
            model_dump=model_dump,
            execution_time_ms=duration_ms
        )
