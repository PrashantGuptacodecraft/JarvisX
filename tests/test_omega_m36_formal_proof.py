"""test_omega_m36_formal_proof.py - M36 tests."""
import pytest
from omega_core.formal_proof.models import SymbolicTheorem, ProofResult, ProofOutcome
from omega_core.formal_proof.bridge import FormalProofBridge

def test_formal_proof_modus_ponens():
    bridge = FormalProofBridge()
    theorem = SymbolicTheorem(
        theorem_id="mp-1",
        assumptions=("P", "Implies(P, Q)"),
        conclusion="Q"
    )
    result = bridge.verify_theorem(theorem)
    assert result.outcome == ProofOutcome.PROVED
    assert result.model_dump is None

def test_formal_proof_disproved_counterexample():
    bridge = FormalProofBridge()
    theorem = SymbolicTheorem(
        theorem_id="inv-1",
        assumptions=("P", "Implies(P, Q)"),
        conclusion="Not(Q)" 
    )
    result = bridge.verify_theorem(theorem)
    assert result.outcome == ProofOutcome.DISPROVED
    assert "P = True" in result.model_dump or "True" in str(result.model_dump)

def test_formal_proof_unsupported_ast():
    bridge = FormalProofBridge()
    theorem = SymbolicTheorem(
        theorem_id="unsup",
        assumptions=("__import__('os').system('echo 1')",),
        conclusion="Q"
    )
    result = bridge.verify_theorem(theorem)
    assert result.outcome == ProofOutcome.UNSUPPORTED
    assert "Invalid" in result.model_dump or "Unsupported" in result.model_dump

def test_bounds_enforced():
    with pytest.raises(ValueError):
        SymbolicTheorem("id", ("A" * 300,), "B")
    with pytest.raises(ValueError):
        SymbolicTheorem("id", ("A",) * 25, "B")
