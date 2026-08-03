"""verification.py - Truth Verification Core and Adversarial Verifier Pool."""
import concurrent.futures
from typing import List, Tuple
from .synthesis_models import CognitionSynthesis, SynthesisStatus
from .verification_models import TruthVerificationResult, AdversarialRouter, AdversarialResult, VerificationRole

class AdversarialVerifierPool:
    """Spawns concurrent adversarial verifiers to probe the synthesis."""
    
    def __init__(self, router: AdversarialRouter):
        self._router = router
        self._roles = (
            VerificationRole.LOGICAL_CONSISTENCY,
            VerificationRole.EVIDENCE_AUDITOR,
            VerificationRole.FALSIFICATION,
            VerificationRole.ASSUMPTION_STRESS,
            VerificationRole.REPRODUCIBILITY
        )
        
    def run_pool(self, synthesis: CognitionSynthesis) -> List[AdversarialResult]:
        results: List[AdversarialResult] = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = {
                executor.submit(self._router.probe, synthesis, role): role
                for role in self._roles
            }
            for future in concurrent.futures.as_completed(futures):
                try:
                    result = future.result(timeout=30.0)
                    results.append(result)
                except Exception as e:
                    # If a verifier crashes, it's considered a failure to falsify, 
                    # but we record it safely. We lean towards verifying false on crash?
                    # "evaluate whether the synthesized decision holds against adversarial probing"
                    # If an adversary crashes, it didn't successfully falsify.
                    results.append(AdversarialResult(passed=False, argument=f"Verifier crashed: {str(e)[:100]}", confidence=0.0))
        return results


class TruthVerificationCore:
    """Orchestrates the verification phase."""
    
    def __init__(self, pool: AdversarialVerifierPool):
        self._pool = pool
        
    def verify(self, synthesis: CognitionSynthesis) -> TruthVerificationResult:
        if synthesis.status != SynthesisStatus.SUCCESS:
            return TruthVerificationResult(
                trace_id=synthesis.trace_id,
                verified_true=False,
                falsification_report="Rejected: Input synthesis does not have SUCCESS status.",
                verification_confidence=0.0
            )
            
        # Spawn concurrent adversarial pool
        adversary_results = self._pool.run_pool(synthesis)
        
        # A synthesis holds if no adversary successfully falsified it.
        # Here, `passed=True` means the synthesis passed the test (i.e. was NOT falsified).
        # `passed=False` means the adversary successfully falsified the synthesis.
        failed_tests = [r for r in adversary_results if not r.passed]
        
        verified_true = len(failed_tests) == 0
        
        if verified_true:
            report = "All adversarial probes successfully deflected. Decision holds."
        else:
            # Sort by confidence to find strongest argument
            failed_tests.sort(key=lambda x: x.confidence, reverse=True)
            strongest_argument = failed_tests[0].argument
            report = f"FALSIFIED: {strongest_argument}"
            if len(report) > 1024:
                report = report[:1021] + "..."
                
        # Calculate confidence from consensus
        success_count = len(adversary_results) - len(failed_tests)
        total = len(adversary_results)
        
        # Weighted confidence can incorporate synthesis confidence and verification ratio
        consensus_ratio = success_count / total if total > 0 else 0.0
        final_confidence = synthesis.deterministic_confidence * consensus_ratio
        
        return TruthVerificationResult(
            trace_id=synthesis.trace_id,
            verified_true=verified_true,
            falsification_report=report,
            verification_confidence=final_confidence
        )
