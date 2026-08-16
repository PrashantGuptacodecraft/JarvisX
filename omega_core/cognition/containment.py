"""containment.py - Omega Containment Kernel.

Enforces zero direct world access and strict isolation for OMEGA's cognitive loop.
"""
import threading
from typing import Any, Callable, List

from .poly_engine import PolyCognitiveEngine
from .synthesis_matrix import SynthesisMatrix
from .verification import TruthVerificationCore
from .verification_models import TruthVerificationResult
from .containment_models import (
    ContainmentViolationType,
    ContainmentViolationRecord,
    ContainedOmegaRequest,
    OmegaReleaseState,
    OmegaReleaseEnvelope,
    ContainmentStatus,
    ContainedOmegaResult
)

class ContainmentViolationError(RuntimeError):
    """Raised when OMEGA attempts to breach containment."""
    def __init__(self, record: ContainmentViolationRecord):
        super().__init__(f"Containment Breach: {record.violation_type} - {record.attempted_action}")
        self.record = record

class OmegaSafeSink:
    """A dedicated safe sink for verified cognitive conclusions."""
    def __init__(self):
        self._lock = threading.Lock()
        self._store: List[ContainedOmegaResult] = []
        
    def store(self, result: ContainedOmegaResult) -> None:
        with self._lock:
            self._store.append(result)
            
    def pull_all(self) -> List[ContainedOmegaResult]:
        with self._lock:
            results = list(self._store)
            self._store.clear()
            return results

class OmegaContainmentKernel:
    """Wraps the OMEGA lifecycle and explicitly traps containment breaches."""
    def __init__(
        self,
        poly_engine: PolyCognitiveEngine,
        synthesis_matrix: SynthesisMatrix,
        verification_core: TruthVerificationCore,
        safe_sink: OmegaSafeSink
    ):
        self.poly_engine = poly_engine
        self.synthesis_matrix = synthesis_matrix
        self.verification_core = verification_core
        self.safe_sink = safe_sink
        
        self.event_bus_trap = self._create_trap(ContainmentViolationType.EVENT_BUS_PUBLISH)
        self.tool_execution_trap = self._create_trap(ContainmentViolationType.TOOL_EXECUTION)
        self.network_request_trap = self._create_trap(ContainmentViolationType.NETWORK_REQUEST)
        
    def _create_trap(self, vtype: ContainmentViolationType) -> Callable[..., Any]:
        def trap(*args, **kwargs):
            record = ContainmentViolationRecord(
                violation_type=vtype,
                attempted_action=str(args),
                blocked=True
            )
            raise ContainmentViolationError(record)
        return trap
        
    def run_cognitive_cycle(self, request: ContainedOmegaRequest) -> ContainedOmegaResult:
        """Executes the full M31 -> M32 -> M33 pipeline within containment."""
        try:
            # Construct proper objects for the poly_engine API
            from .models import CognitionTrace, CognitionStatus
            from .poly_models import CancellationToken
            import time as _time
            now = _time.time()
            trace = CognitionTrace(
                schema_version=1,
                trace_id=request.trace_id,
                session_id=f"containment-{request.trace_id}",
                parent_trace_id=None,
                sequence_number=0,
                goal_id=request.trace_id,
                problem_summary=request.objective[:500],
                evidence=(),
                decision=None,
                status=CognitionStatus.CREATED,
                outcome_summary=None,
                created_at=now,
                updated_at=now
            )
            cancellation_token = CancellationToken()
            poly_result = self.poly_engine.execute_round(
                trace=trace,
                timeout_seconds=1.0,
                cancellation_token=cancellation_token
            )
            
            if not poly_result.is_eligible_for_synthesis:
                return ContainedOmegaResult(request.trace_id, ContainmentStatus.SECURE, None)
                
            synthesis_result = self.synthesis_matrix.synthesize(poly_result)
            
            from .synthesis_models import SynthesisStatus
            if synthesis_result.status != SynthesisStatus.SUCCESS:
                return ContainedOmegaResult(request.trace_id, ContainmentStatus.SECURE, None)
                
            verification_result = self.verification_core.verify(synthesis_result)
            
            if not verification_result.verified_true:
                return ContainedOmegaResult(request.trace_id, ContainmentStatus.SECURE, None)
                
            # Prohibited output scanner
            report_text = verification_result.falsification_report.lower()
            prohibited_keys = [
                "chain_of_thought", "scratchpad", "internal_reasoning", "hidden_reasoning",
                "reasoning_tokens", "context_window", "tensor_activations", "raw_model_output",
                "full_prompt", "provider_trace", "complete_conversation", "secret_prompt",
                "credentials", "environment_dump", "executable_command", "tool_call"
            ]
            for key in prohibited_keys:
                if key in report_text:
                    record = ContainmentViolationRecord(
                        ContainmentViolationType.UNSAFE_OUTPUT,
                        attempted_action=f"Contained forbidden term: {key}",
                        blocked=True
                    )
                    raise ContainmentViolationError(record)
            
            envelope = OmegaReleaseEnvelope(
                state=OmegaReleaseState.SEALED,
                verification_result=verification_result,
                breach_records=()
            )
            
            result = ContainedOmegaResult(
                trace_id=request.trace_id,
                status=ContainmentStatus.SECURE,
                envelope=envelope
            )
            self.safe_sink.store(result)
            return result
            
        except ContainmentViolationError as e:
            # Trap the violation, return a breached status
            result = ContainedOmegaResult(
                trace_id=request.trace_id,
                status=ContainmentStatus.BREACH_ATTEMPTED,
                envelope=OmegaReleaseEnvelope(
                    state=OmegaReleaseState.SEALED,
                    verification_result=TruthVerificationResult(
                        trace_id=request.trace_id,
                        verified_true=False,
                        falsification_report=f"BREACH ATTEMPTED: {e.record.violation_type}",
                        verification_confidence=0.0
                    ),
                    breach_records=(e.record,)
                )
            )
            self.safe_sink.store(result)
            return result
