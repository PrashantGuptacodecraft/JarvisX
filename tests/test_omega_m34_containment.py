"""test_omega_m34_containment.py - Focused tests for Milestone 34 Containment Kernel."""
import pytest
from unittest.mock import Mock
from dataclasses import replace

from omega_core.cognition.containment import (
    OmegaContainmentKernel,
    OmegaSafeSink,
    ContainmentViolationError
)
from omega_core.cognition.containment_models import (
    ContainedOmegaRequest,
    OmegaCapabilityPolicy,
    OmegaCapability,
    ContainmentViolationType,
    OmegaReleaseState,
    ContainmentStatus,
    ContainedOmegaResult,
    OmegaReleaseEnvelope
)
from omega_core.cognition.poly_engine import PolyCognitiveEngine
from omega_core.cognition.poly_models import PolyCognitionResult, PolyRoundStatus
from omega_core.cognition.synthesis_matrix import SynthesisMatrix
from omega_core.cognition.synthesis_models import CognitionSynthesis, SynthesisStatus
from omega_core.cognition.verification import TruthVerificationCore
from omega_core.cognition.verification_models import TruthVerificationResult

# --- Public Contract & Immutability ---
def test_containment_public_contract():
    # Only one release state
    assert len(OmegaReleaseState) == 1
    assert OmegaReleaseState.SEALED == "sealed"
    
    # Immutable bounds
    policy = OmegaCapabilityPolicy(allowed_capabilities=(OmegaCapability.SYNTHESIZE,))
    req = ContainedOmegaRequest(trace_id="t1", objective="o1", policy=policy)
    
    with pytest.raises(Exception): # Frozen dataclass
        req.trace_id = "t2"
        
    with pytest.raises(Exception):
        policy.allowed_capabilities = ()

# --- Default-deny & Policy ---
def test_default_deny_policy():
    with pytest.raises(ValueError, match="Duplicate"):
        OmegaCapabilityPolicy(allowed_capabilities=(OmegaCapability.SYNTHESIZE, OmegaCapability.SYNTHESIZE))
    
    with pytest.raises(ValueError, match="Wildcard"):
        OmegaCapabilityPolicy(allowed_capabilities=("*",)) # type: ignore

# --- Fake Components for Gating ---
class FakePolyEngine(PolyCognitiveEngine):
    def __init__(self, result_status):
        self.call_count = 0
        self.result_status = result_status
    def execute_round(self, trace, timeout_seconds=1.0, cancellation_token=None):
        self.call_count += 1
        return PolyCognitionResult(
            trace_id=trace.trace_id, status=self.result_status, role_results=(),
            is_eligible_for_synthesis=(self.result_status == PolyRoundStatus.COMPLETE),
            cancellation_requested=False, total_time_ms=10.0
        )

class FakeSynthesisMatrix(SynthesisMatrix):
    def __init__(self, result_status):
        self.call_count = 0
        self.result_status = result_status
    def synthesize(self, result):
        self.call_count += 1
        return CognitionSynthesis(
            trace_id=result.trace_id, status=self.result_status, agreements=(), contradictions=(),
            complementary_proposals=(), evidence_gaps=(), safety_objections=(), unresolved_questions=(),
            selected_strategy="ok", final_decision="ok", supporting_roles=(), deterministic_confidence=1.0
        )

class FakeVerificationCore(TruthVerificationCore):
    def __init__(self, verified_true, report="Report"):
        self.call_count = 0
        self.verified_true = verified_true
        self.report = report
    def verify(self, synthesis):
        self.call_count += 1
        return TruthVerificationResult(
            trace_id=synthesis.trace_id, verified_true=self.verified_true,
            falsification_report=self.report, verification_confidence=1.0
        )

# --- Pipeline Gating ---
@pytest.mark.parametrize("poly_status, synth_status, verif_true, expect_env", [
    (PolyRoundStatus.COMPLETE, SynthesisStatus.SUCCESS, True, True),
    (PolyRoundStatus.FAILED, SynthesisStatus.SUCCESS, True, False),
    (PolyRoundStatus.COMPLETE, SynthesisStatus.INSUFFICIENT_EVIDENCE, True, False),
    (PolyRoundStatus.COMPLETE, SynthesisStatus.SUCCESS, False, False),
])
def test_pipeline_gating(poly_status, synth_status, verif_true, expect_env):
    poly = FakePolyEngine(poly_status)
    synth = FakeSynthesisMatrix(synth_status)
    verif = FakeVerificationCore(verif_true)
    sink = OmegaSafeSink()
    kernel = OmegaContainmentKernel(poly, synth, verif, sink)
    
    req = ContainedOmegaRequest(trace_id="tr", objective="obj", policy=OmegaCapabilityPolicy(()))
    res = kernel.run_cognitive_cycle(req)
    
    assert poly.call_count == 1
    assert synth.call_count == (1 if poly_status == PolyRoundStatus.COMPLETE else 0)
    assert verif.call_count == (1 if poly_status == PolyRoundStatus.COMPLETE and synth_status == SynthesisStatus.SUCCESS else 0)
    
    if expect_env:
        assert res.envelope is not None
        assert res.envelope.state == OmegaReleaseState.SEALED
    else:
        assert res.envelope is None or res.envelope.verification_result.verified_true == False

# --- Prohibited Output ---
@pytest.mark.parametrize("prohibited_key", [
    "chain_of_thought", "scratchpad", "internal_reasoning", "hidden_reasoning",
    "reasoning_tokens", "context_window", "tensor_activations", "raw_model_output",
    "full_prompt", "provider_trace", "complete_conversation", "secret_prompt",
    "credentials", "environment_dump", "executable_command", "tool_call"
])
def test_prohibited_output(prohibited_key):
    poly = FakePolyEngine(PolyRoundStatus.COMPLETE)
    synth = FakeSynthesisMatrix(SynthesisStatus.SUCCESS)
    verif = FakeVerificationCore(True, report=f"{{{prohibited_key}: 'bad'}}")
    sink = OmegaSafeSink()
    kernel = OmegaContainmentKernel(poly, synth, verif, sink)
    
    req = ContainedOmegaRequest(trace_id="tr", objective="obj", policy=OmegaCapabilityPolicy(()))
    res = kernel.run_cognitive_cycle(req)
    
    assert res.status == ContainmentStatus.BREACH_ATTEMPTED
    assert res.envelope.verification_result.verified_true == False
    assert "UNSAFE_OUTPUT" in str(res.envelope.breach_records)

# --- Containment Violations ---
@pytest.mark.parametrize("violation_type, trap_method, args", [
    (ContainmentViolationType.EVENT_BUS_PUBLISH, "event_bus_trap", ({"event": "x"},)),
    (ContainmentViolationType.TOOL_EXECUTION, "tool_execution_trap", ("tool",)),
    (ContainmentViolationType.NETWORK_REQUEST, "network_request_trap", ("url",)),
])
def test_containment_traps(violation_type, trap_method, args):
    poly = FakePolyEngine(PolyRoundStatus.COMPLETE)
    synth = FakeSynthesisMatrix(SynthesisStatus.SUCCESS)
    verif = FakeVerificationCore(True)
    sink = OmegaSafeSink()
    kernel = OmegaContainmentKernel(poly, synth, verif, sink)
    
    trap = getattr(kernel, trap_method)
    with pytest.raises(ContainmentViolationError) as exc_info:
        trap(*args)
    assert exc_info.value.record.violation_type == violation_type
