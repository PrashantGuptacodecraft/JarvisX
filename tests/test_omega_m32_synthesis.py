"""test_omega_m32_synthesis.py - Focused tests for Milestone 32 Synthesis."""
import pytest
from typing import Tuple

from omega_core.cognition.poly_models import (
    PolyCognitionResult, PolyRoundStatus, CognitiveRole, 
    RoleExecutionResult, CognitiveModelResponse
)
from omega_core.cognition.synthesis_models import (
    CognitionSynthesis, SynthesisStatus, DebateMatrix, 
    SynthesisRouterResponse, CognitiveSynthesisRouter
)
from omega_core.cognition.synthesis_matrix import SynthesisMatrix

class MockSynthesisRouter(CognitiveSynthesisRouter):
    def synthesize(self, matrix: DebateMatrix) -> SynthesisRouterResponse:
        has_skepticism = any(r[0] == CognitiveRole.SKEPTICISM for r in matrix.role_summaries)
        return SynthesisRouterResponse(
            agreements=("Agree 1",),
            contradictions=("Contradict 1",),
            complementary_proposals=(),
            evidence_gaps=(),
            safety_objections=("Objection 1",) if has_skepticism else (),
            unresolved_questions=(),
            selected_strategy="Test Strategy",
            final_decision="Test Decision",
            supporting_roles=(CognitiveRole.LOGIC, CognitiveRole.INTUITION)
        )

def make_result(status: PolyRoundStatus, eligible: bool, roles: list) -> PolyCognitionResult:
    results = []
    for role, content, conf in roles:
        if content is None:
            results.append(RoleExecutionResult(
                role=role, response=None, error="Failed", is_timeout=False
            ))
        else:
            results.append(RoleExecutionResult(
                role=role, 
                response=CognitiveModelResponse(
                    role=role, hypothesis_or_critique=content, confidence=conf, computation_time_ms=10.0
                ), 
                error=None, is_timeout=False
            ))
            
    return PolyCognitionResult(
        trace_id="tr_123",
        status=status,
        role_results=tuple(results),
        is_eligible_for_synthesis=eligible,
        cancellation_requested=False,
        total_time_ms=100.0
    )


def test_synthesis_matrix_success():
    result = make_result(
        status=PolyRoundStatus.COMPLETE,
        eligible=True,
        roles=[
            (CognitiveRole.LOGIC, "logic content", 0.8),
            (CognitiveRole.SKEPTICISM, "skepticism content", 0.6),
            (CognitiveRole.INTUITION, "intuition content", 0.9),
            (CognitiveRole.CREATIVITY, "creativity content", 0.7),
            (CognitiveRole.ABSTRACTION, "abstraction content", 0.5),
        ]
    )
    
    matrix = SynthesisMatrix(MockSynthesisRouter())
    synthesis = matrix.synthesize(result)
    
    assert synthesis.status == SynthesisStatus.SUCCESS
    assert synthesis.selected_strategy == "Test Strategy"
    # Expected weighted conf:
    # LOGIC (0.8 * 0.30) = 0.24
    # SKEPTICISM (0.6 * 0.30) = 0.18
    # INTUITION (0.9 * 0.15) = 0.135
    # CREATIVITY (0.7 * 0.10) = 0.07
    # ABSTRACTION (0.5 * 0.15) = 0.075
    # Sum = 0.70
    # Penalties:
    # 1 contradiction = -0.15
    # 1 safety objection = -0.10
    # Final = 0.70 - 0.25 = 0.45
    assert abs(synthesis.deterministic_confidence - 0.45) < 0.001


def test_synthesis_matrix_ineligible_status():
    result = make_result(
        status=PolyRoundStatus.BLOCKED,
        eligible=False,
        roles=[]
    )
    matrix = SynthesisMatrix(MockSynthesisRouter())
    synthesis = matrix.synthesize(result)
    assert synthesis.status == SynthesisStatus.INELIGIBLE


def test_synthesis_matrix_ineligible_flag():
    result = make_result(
        status=PolyRoundStatus.PARTIAL,
        eligible=False, # E.g., failed Logic
        roles=[
            (CognitiveRole.LOGIC, None, 0.0),
            (CognitiveRole.SKEPTICISM, "ok", 0.8),
            (CognitiveRole.INTUITION, "ok", 0.9),
        ]
    )
    matrix = SynthesisMatrix(MockSynthesisRouter())
    synthesis = matrix.synthesize(result)
    assert synthesis.status == SynthesisStatus.INELIGIBLE


def test_synthesis_matrix_missing_logic():
    result = make_result(
        status=PolyRoundStatus.PARTIAL,
        eligible=True, # Malformed input technically
        roles=[
            (CognitiveRole.SKEPTICISM, "ok", 0.8),
            (CognitiveRole.INTUITION, "ok", 0.9),
            (CognitiveRole.CREATIVITY, "ok", 0.7),
        ]
    )
    matrix = SynthesisMatrix(MockSynthesisRouter())
    synthesis = matrix.synthesize(result)
    assert synthesis.status == SynthesisStatus.INELIGIBLE


def test_synthesis_matrix_insufficient_evidence_less_than_3():
    result = make_result(
        status=PolyRoundStatus.PARTIAL,
        eligible=True,
        roles=[
            (CognitiveRole.LOGIC, "ok", 0.8),
            (CognitiveRole.SKEPTICISM, "ok", 0.9),
        ]
    )
    matrix = SynthesisMatrix(MockSynthesisRouter())
    synthesis = matrix.synthesize(result)
    assert synthesis.status == SynthesisStatus.INSUFFICIENT_EVIDENCE


def test_synthesis_matrix_insufficient_evidence_no_third_role():
    # Has 3 valid responses, but the 3rd is duplicate or invalid type
    # (Though we can't have duplicate enum values easily here, let's test empty content)
    result = make_result(
        status=PolyRoundStatus.COMPLETE,
        eligible=True,
        roles=[
            (CognitiveRole.LOGIC, "ok", 0.8),
            (CognitiveRole.SKEPTICISM, "ok", 0.9),
            (CognitiveRole.INTUITION, None, 0.0),
            (CognitiveRole.CREATIVITY, None, 0.0),
            (CognitiveRole.ABSTRACTION, None, 0.0),
        ]
    )
    matrix = SynthesisMatrix(MockSynthesisRouter())
    synthesis = matrix.synthesize(result)
    assert synthesis.status == SynthesisStatus.INSUFFICIENT_EVIDENCE


def test_synthesis_model_bounds():
    with pytest.raises(ValueError, match="selected_strategy exceeds"):
        CognitionSynthesis(
            trace_id="tr", status=SynthesisStatus.SUCCESS,
            agreements=(), contradictions=(), complementary_proposals=(),
            evidence_gaps=(), safety_objections=(), unresolved_questions=(),
            selected_strategy="A" * 257, final_decision="ok", supporting_roles=(),
            deterministic_confidence=1.0
        )
