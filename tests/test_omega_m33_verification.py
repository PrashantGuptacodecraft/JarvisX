"""test_omega_m33_verification.py - Focused tests for Milestone 33 Truth Verification."""
import pytest

from omega_core.cognition.synthesis_models import CognitionSynthesis, SynthesisStatus
from omega_core.cognition.verification_models import TruthVerificationResult, AdversarialResult, AdversarialRouter
from omega_core.cognition.verification import AdversarialVerifierPool, TruthVerificationCore

class MockAdversarialRouter(AdversarialRouter):
    def __init__(self, should_pass: bool, argument: str = "Mock argument", confidence: float = 0.9):
        self.should_pass = should_pass
        self.argument = argument
        self.confidence = confidence
        self.call_count = 0
        
    def probe(self, synthesis: CognitionSynthesis, strategy: str) -> AdversarialResult:
        self.call_count += 1
        return AdversarialResult(passed=self.should_pass, argument=f"{strategy}: {self.argument}", confidence=self.confidence)

def make_synthesis(status: SynthesisStatus = SynthesisStatus.SUCCESS, conf: float = 0.8) -> CognitionSynthesis:
    return CognitionSynthesis(
        trace_id="tr_123",
        status=status,
        agreements=("Agreement 1",),
        contradictions=(),
        complementary_proposals=(),
        evidence_gaps=(),
        safety_objections=(),
        unresolved_questions=(),
        selected_strategy="Test Strategy",
        final_decision="Test Decision",
        supporting_roles=(),
        deterministic_confidence=conf
    )

def test_verification_core_rejects_non_success():
    synthesis = make_synthesis(status=SynthesisStatus.INSUFFICIENT_EVIDENCE)
    router = MockAdversarialRouter(should_pass=True)
    pool = AdversarialVerifierPool(router)
    core = TruthVerificationCore(pool)
    
    result = core.verify(synthesis)
    
    assert not result.verified_true
    assert result.verification_confidence == 0.0
    assert "Rejected" in result.falsification_report
    assert router.call_count == 0

def test_verification_core_success():
    synthesis = make_synthesis()
    router = MockAdversarialRouter(should_pass=True)
    pool = AdversarialVerifierPool(router)
    core = TruthVerificationCore(pool)
    
    result = core.verify(synthesis)
    
    assert result.verified_true
    assert result.verification_confidence == 0.8  # 0.8 * (5/5)
    assert router.call_count == 5
    assert result.trace_id == "tr_123"

def test_verification_core_falsified():
    synthesis = make_synthesis()
    router = MockAdversarialRouter(should_pass=False, argument="Strong falsification", confidence=0.95)
    pool = AdversarialVerifierPool(router)
    core = TruthVerificationCore(pool)
    
    result = core.verify(synthesis)
    
    assert not result.verified_true
    assert result.verification_confidence == 0.0 # 0.8 * (0/3)
    assert "FALSIFIED" in result.falsification_report
    assert "Strong falsification" in result.falsification_report

def test_verification_model_bounds():
    with pytest.raises(ValueError, match="exceeds 1024"):
        TruthVerificationResult(
            trace_id="tr_123",
            verified_true=False,
            falsification_report="A" * 1025,
            verification_confidence=0.5
        )

    with pytest.raises(ValueError, match="between 0.0 and 1.0"):
        TruthVerificationResult(
            trace_id="tr_123",
            verified_true=True,
            falsification_report="Ok",
            verification_confidence=1.5
        )
