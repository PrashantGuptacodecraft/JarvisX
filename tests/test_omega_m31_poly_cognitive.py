"""test_omega_m31_poly_cognitive.py - Focused tests for Milestone 31."""
import time
import pytest
from typing import Dict
from omega_core.cognition.poly_models import (
    CognitiveRole, PolyRoundStatus, CognitiveRoleRequest, 
    CognitiveModelResponse, CancellationToken, CognitiveModelRouter
)
from omega_core.cognition.poly_engine import PolyCognitiveEngine
from omega_core.cognition.models import CognitionTrace, CognitionStatus


class MockRouter(CognitiveModelRouter):
    def __init__(self, failure_roles=None, sleep_roles=None):
        self.failure_roles = failure_roles or set()
        self.sleep_roles = sleep_roles or set()
        
    def generate_role_response(
        self,
        request: CognitiveRoleRequest,
        *,
        timeout_seconds: float,
        cancellation_token: CancellationToken,
    ) -> CognitiveModelResponse:
        
        if cancellation_token.is_cancelled:
            raise Exception("Cancelled")
            
        if request.role in self.sleep_roles:
            time.sleep(timeout_seconds + 2.0)
            
        if request.role in self.failure_roles:
            raise RuntimeError(f"Simulated failure for {request.role}")
            
        return CognitiveModelResponse(
            role=request.role,
            hypothesis_or_critique=f"Response from {request.role}",
            confidence=0.9,
            computation_time_ms=10.0
        )


@pytest.fixture
def dummy_trace():
    return CognitionTrace(
        schema_version=1,
        trace_id="tr_123",
        session_id="sess_1",
        parent_trace_id=None,
        sequence_number=1,
        goal_id="g1",
        problem_summary="Test problem",
        evidence=(),
        decision=None,
        status=CognitionStatus.REASONING,
        outcome_summary=None,
        created_at=time.time(),
        updated_at=time.time()
    )


def test_poly_engine_complete(dummy_trace):
    engine = PolyCognitiveEngine(MockRouter())
    ct = CancellationToken()
    
    result = engine.execute_round(dummy_trace, timeout_seconds=1.0, cancellation_token=ct)
    
    assert result.status == PolyRoundStatus.COMPLETE
    assert result.is_eligible_for_synthesis is True
    assert len(result.role_results) == 5
    assert all(r.response is not None for r in result.role_results)
    
    # Ensure canonical order
    roles = [r.role for r in result.role_results]
    assert roles == [
        CognitiveRole.INTUITION,
        CognitiveRole.LOGIC,
        CognitiveRole.CREATIVITY,
        CognitiveRole.SKEPTICISM,
        CognitiveRole.ABSTRACTION
    ]


def test_poly_engine_partial_eligible(dummy_trace):
    # Intuition fails, but Logic and Skepticism succeed
    engine = PolyCognitiveEngine(MockRouter(failure_roles={CognitiveRole.INTUITION}))
    ct = CancellationToken()
    
    result = engine.execute_round(dummy_trace, timeout_seconds=1.0, cancellation_token=ct)
    
    assert result.status == PolyRoundStatus.PARTIAL
    assert result.is_eligible_for_synthesis is True
    assert result.role_results[0].role == CognitiveRole.INTUITION
    assert result.role_results[0].response is None
    assert result.role_results[0].error == "Simulated failure for CognitiveRole.INTUITION"


def test_poly_engine_partial_ineligible_logic(dummy_trace):
    # Logic fails
    engine = PolyCognitiveEngine(MockRouter(failure_roles={CognitiveRole.LOGIC}))
    ct = CancellationToken()
    
    result = engine.execute_round(dummy_trace, timeout_seconds=1.0, cancellation_token=ct)
    
    assert result.status == PolyRoundStatus.PARTIAL
    assert result.is_eligible_for_synthesis is False


def test_poly_engine_partial_ineligible_skepticism(dummy_trace):
    # Skepticism fails
    engine = PolyCognitiveEngine(MockRouter(failure_roles={CognitiveRole.SKEPTICISM}))
    ct = CancellationToken()
    
    result = engine.execute_round(dummy_trace, timeout_seconds=1.0, cancellation_token=ct)
    
    assert result.status == PolyRoundStatus.PARTIAL
    assert result.is_eligible_for_synthesis is False


def test_poly_engine_blocked(dummy_trace):
    # All fail
    engine = PolyCognitiveEngine(MockRouter(failure_roles={
        CognitiveRole.INTUITION, CognitiveRole.LOGIC, CognitiveRole.CREATIVITY,
        CognitiveRole.SKEPTICISM, CognitiveRole.ABSTRACTION
    }))
    ct = CancellationToken()
    
    result = engine.execute_round(dummy_trace, timeout_seconds=1.0, cancellation_token=ct)
    
    assert result.status == PolyRoundStatus.BLOCKED
    assert result.is_eligible_for_synthesis is False


def test_poly_engine_timeout(dummy_trace):
    # Abstraction times out
    engine = PolyCognitiveEngine(MockRouter(sleep_roles={CognitiveRole.ABSTRACTION}))
    ct = CancellationToken()
    
    # Fast timeout to test
    result = engine.execute_round(dummy_trace, timeout_seconds=0.1, cancellation_token=ct)
    
    assert result.status == PolyRoundStatus.PARTIAL
    assert result.is_eligible_for_synthesis is True  # Logic and Skepticism still succeeded
    assert result.role_results[4].role == CognitiveRole.ABSTRACTION
    assert result.role_results[4].is_timeout is True
    assert result.role_results[4].response is None


def test_poly_engine_cancelled_before_any_complete(dummy_trace):
    engine = PolyCognitiveEngine(MockRouter())
    ct = CancellationToken()
    ct.cancel() # Cancel before starting
    
    result = engine.execute_round(dummy_trace, timeout_seconds=1.0, cancellation_token=ct)
    
    assert result.status == PolyRoundStatus.CANCELLED
    assert result.is_eligible_for_synthesis is False
    assert result.cancellation_requested is True
    assert len(result.role_results) == 0

def test_poly_engine_cancelled_after_partial_complete(dummy_trace, monkeypatch):
    # We want to mock CancellationToken to become cancelled during the router wait.
    # We can do this by using a side effect in MockRouter.
    ct = CancellationToken()
    
    class CancelRouter(MockRouter):
        def generate_role_response(self, request, *, timeout_seconds, cancellation_token):
            if request.role == CognitiveRole.ABSTRACTION:
                # Cancel the token during this specific role
                cancellation_token.cancel()
                time.sleep(0.5)
                raise Exception("Cancelled")
            return super().generate_role_response(
                request, timeout_seconds=timeout_seconds, cancellation_token=cancellation_token
            )

    engine = PolyCognitiveEngine(CancelRouter())
    
    result = engine.execute_round(dummy_trace, timeout_seconds=2.0, cancellation_token=ct)
    
    assert result.status == PolyRoundStatus.PARTIAL
    assert result.cancellation_requested is True
    # Logic and Skepticism still succeeded, so eligible is True
    assert result.is_eligible_for_synthesis is True
    assert len(result.role_results) == 5


def test_cognitive_model_response_bounds():
    with pytest.raises(ValueError, match="exceeds 2048"):
        CognitiveModelResponse(
            role=CognitiveRole.LOGIC,
            hypothesis_or_critique="A" * 2049,
            confidence=0.5,
            computation_time_ms=10.0
        )
        
    with pytest.raises(ValueError, match="confidence must be between"):
        CognitiveModelResponse(
            role=CognitiveRole.LOGIC,
            hypothesis_or_critique="Test",
            confidence=1.5,
            computation_time_ms=10.0
        )
