"""synthesis_matrix.py - OMEGA Phase 7, Milestone 32 Synthesis Matrix.

Evaluates divergent role outputs, checks eligibility, and orchestrates convergence.
"""
from typing import Dict, List
from .poly_models import (
    PolyCognitionResult, PolyRoundStatus, CognitiveRole, RoleExecutionResult
)
from .synthesis_models import (
    CognitionSynthesis, SynthesisStatus, DebateMatrix, CognitiveSynthesisRouter
)

class SynthesisMatrix:
    def __init__(self, router: CognitiveSynthesisRouter):
        self._router = router

    def _validate_eligibility(self, result: PolyCognitionResult) -> SynthesisStatus:
        if result.status not in (PolyRoundStatus.COMPLETE, PolyRoundStatus.PARTIAL):
            return SynthesisStatus.INELIGIBLE
            
        if not result.is_eligible_for_synthesis:
            return SynthesisStatus.INELIGIBLE
            
        if not result.trace_id or not result.trace_id.strip():
            return SynthesisStatus.INELIGIBLE
            
        # Extract successful roles
        successful_roles: Dict[CognitiveRole, RoleExecutionResult] = {}
        for r in result.role_results:
            if r.response is not None:
                if r.role in successful_roles:
                    return SynthesisStatus.INELIGIBLE # Duplicate role
                successful_roles[r.role] = r
                
        if len(successful_roles) < 3:
            return SynthesisStatus.INSUFFICIENT_EVIDENCE
            
        if CognitiveRole.LOGIC not in successful_roles:
            return SynthesisStatus.INELIGIBLE
            
        if CognitiveRole.SKEPTICISM not in successful_roles:
            return SynthesisStatus.INELIGIBLE
            
        has_third = any(
            role in successful_roles for role in (
                CognitiveRole.INTUITION, CognitiveRole.CREATIVITY, CognitiveRole.ABSTRACTION
            )
        )
        if not has_third:
            return SynthesisStatus.INSUFFICIENT_EVIDENCE
            
        # Validate structurally
        has_substantive = False
        for r in successful_roles.values():
            text = r.response.hypothesis_or_critique.strip()
            if text:
                has_substantive = True
            if len(text) > 2048:
                return SynthesisStatus.INELIGIBLE
                
        if not has_substantive:
            return SynthesisStatus.INSUFFICIENT_EVIDENCE
            
        return SynthesisStatus.SUCCESS

    def synthesize(self, result: PolyCognitionResult) -> CognitionSynthesis:
        status = self._validate_eligibility(result)
        if status != SynthesisStatus.SUCCESS:
            return CognitionSynthesis(
                trace_id=result.trace_id,
                status=status,
                agreements=(),
                contradictions=(),
                complementary_proposals=(),
                evidence_gaps=(),
                safety_objections=(),
                unresolved_questions=(),
                selected_strategy=None,
                final_decision=None,
                supporting_roles=(),
                deterministic_confidence=0.0
            )

        # 1. Build deterministic debate matrix
        summaries = []
        
        role_weights = {
            CognitiveRole.LOGIC: 0.30,
            CognitiveRole.SKEPTICISM: 0.30,
            CognitiveRole.INTUITION: 0.15,
            CognitiveRole.CREATIVITY: 0.10,
            CognitiveRole.ABSTRACTION: 0.15,
        }
        
        weighted_conf_sum = 0.0
        total_weight = 0.0
        
        for r in result.role_results:
            if r.response is not None:
                summaries.append((r.role, r.response.hypothesis_or_critique))
                weight = role_weights.get(r.role, 0.0)
                weighted_conf_sum += r.response.confidence * weight
                total_weight += weight
                
        debate_matrix = DebateMatrix(
            trace_id=result.trace_id,
            role_summaries=tuple(summaries)
        )

        # 2. Bounded convergence step
        try:
            router_response = self._router.synthesize(debate_matrix)
        except Exception:
            return CognitionSynthesis(
                trace_id=result.trace_id,
                status=SynthesisStatus.INSUFFICIENT_EVIDENCE,
                agreements=(),
                contradictions=(),
                complementary_proposals=(),
                evidence_gaps=(),
                safety_objections=(),
                unresolved_questions=(),
                selected_strategy=None,
                final_decision=None,
                supporting_roles=(),
                deterministic_confidence=0.0
            )
            
        # Calculate deterministic confidence
        avg_confidence = weighted_conf_sum / total_weight if total_weight > 0 else 0.0
        
        missing_roles_count = 5 - len(summaries)
        penalty_missing = missing_roles_count * 0.05
        penalty_contradictions = min(len(router_response.contradictions) * 0.15, 0.30)
        penalty_evidence = min(len(router_response.evidence_gaps) * 0.05, 0.20)
        penalty_risks = min(len(router_response.safety_objections) * 0.10, 0.20)
        penalty_unsupported = 0.20 if len(router_response.supporting_roles) == 0 else 0.0
        
        final_confidence = avg_confidence - penalty_missing - penalty_contradictions - penalty_evidence - penalty_risks - penalty_unsupported
        final_confidence = max(0.0, min(1.0, final_confidence))
        return CognitionSynthesis(
            trace_id=result.trace_id,
            status=SynthesisStatus.SUCCESS,
            agreements=router_response.agreements,
            contradictions=router_response.contradictions,
            complementary_proposals=router_response.complementary_proposals,
            evidence_gaps=router_response.evidence_gaps,
            safety_objections=router_response.safety_objections,
            unresolved_questions=router_response.unresolved_questions,
            selected_strategy=router_response.selected_strategy,
            final_decision=router_response.final_decision,
            supporting_roles=router_response.supporting_roles,
            deterministic_confidence=final_confidence
        )
