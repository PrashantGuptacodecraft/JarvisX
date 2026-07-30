"""poly_engine.py - OMEGA Poly-Cognitive Engine implementation.

Concurrently dispatches structured cognition requests to isolated role engines.
"""
import time
import concurrent.futures
from typing import Dict, List, Tuple

from .poly_models import (
    CognitiveRole, PolyRoundStatus, CognitiveRoleRequest, 
    CognitiveModelResponse, RoleExecutionResult, PolyCognitionResult,
    CognitiveModelRouter, CancellationToken
)
from .models import CognitionTrace


class PolyCognitiveEngine:
    def __init__(self, router: CognitiveModelRouter):
        self._router = router

    def execute_round(
        self, 
        trace: CognitionTrace, 
        timeout_seconds: float, 
        cancellation_token: CancellationToken
    ) -> PolyCognitionResult:
        
        start_time = time.time()
        
        if cancellation_token.is_cancelled:
            return PolyCognitionResult(
                trace_id=trace.trace_id,
                status=PolyRoundStatus.CANCELLED,
                role_results=(),
                is_eligible_for_synthesis=False,
                cancellation_requested=True,
                total_time_ms=0.0
            )

        # Build requests for all 5 roles
        roles = [
            CognitiveRole.INTUITION,
            CognitiveRole.LOGIC,
            CognitiveRole.CREATIVITY,
            CognitiveRole.SKEPTICISM,
            CognitiveRole.ABSTRACTION
        ]
        
        evidence_summaries = tuple(
            f"{e.source_type}: {e.excerpt}" for e in trace.evidence
        )
        
        futures: Dict[concurrent.futures.Future, CognitiveRole] = {}
        
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                for role in roles:
                    request = CognitiveRoleRequest(
                        session_id=trace.session_id,
                        trace_id=trace.trace_id,
                        role=role,
                        problem_summary=trace.problem_summary,
                        evidence_summaries=evidence_summaries
                    )
                    
                    future = executor.submit(
                        self._router.generate_role_response,
                        request,
                        timeout_seconds=timeout_seconds,
                        cancellation_token=cancellation_token
                    )
                    futures[future] = role
                    
                results: List[RoleExecutionResult] = []
                
                # Wait for all futures with bounded timeout + buffer
                wait_timeout = timeout_seconds + 1.0
                done, not_done = concurrent.futures.wait(
                    futures.keys(), 
                    timeout=wait_timeout, 
                    return_when=concurrent.futures.ALL_COMPLETED
                )
                
                # Process completed
                for future in done:
                    role = futures[future]
                    try:
                        response = future.result()
                        # Validate that the response role matches
                        if response.role != role:
                            results.append(RoleExecutionResult(
                                role=role, response=None, error="Role mismatch in response", is_timeout=False
                            ))
                        else:
                            results.append(RoleExecutionResult(
                                role=role, response=response, error=None, is_timeout=False
                            ))
                    except Exception as e:
                        results.append(RoleExecutionResult(
                            role=role, response=None, error=str(e), is_timeout=False
                        ))
                        
                # Process timeouts
                for future in not_done:
                    role = futures[future]
                    results.append(RoleExecutionResult(
                        role=role, response=None, error="Timeout exceeded", is_timeout=True
                    ))
                    
        except Exception as e:
            # Orchestration failed completely
            return PolyCognitionResult(
                trace_id=trace.trace_id,
                status=PolyRoundStatus.FAILED,
                role_results=(),
                is_eligible_for_synthesis=False,
                cancellation_requested=cancellation_token.is_cancelled,
                total_time_ms=(time.time() - start_time) * 1000.0
            )
            
        # Sort results into canonical role order
        results.sort(key=lambda x: roles.index(x.role))
        
        valid_count = sum(1 for r in results if r.response is not None)
        logic_success = any(r.role == CognitiveRole.LOGIC and r.response is not None for r in results)
        skepticism_success = any(r.role == CognitiveRole.SKEPTICISM and r.response is not None for r in results)
        
        cancellation_requested = cancellation_token.is_cancelled
        
        if cancellation_requested:
            if valid_count > 0:
                status = PolyRoundStatus.PARTIAL
                eligible = logic_success and skepticism_success
            else:
                status = PolyRoundStatus.CANCELLED
                eligible = False
        else:
            if valid_count == 5:
                status = PolyRoundStatus.COMPLETE
                eligible = True
            elif valid_count > 0:
                status = PolyRoundStatus.PARTIAL
                eligible = logic_success and skepticism_success
            else:
                status = PolyRoundStatus.BLOCKED
                eligible = False
                
        return PolyCognitionResult(
            trace_id=trace.trace_id,
            status=status,
            role_results=tuple(results),
            is_eligible_for_synthesis=eligible,
            cancellation_requested=cancellation_requested,
            total_time_ms=(time.time() - start_time) * 1000.0
        )
