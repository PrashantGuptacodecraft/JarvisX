import time
import hashlib
from typing import List, Optional, Any, Callable
from pathlib import Path
from datetime import datetime, timezone

from shared_core.event_bus import EventBus
from .pre_run_model import (
    ExecutionRequest, PreRunAssessment, PreRunFinding, PreRunSummary, 
    PredictorResult, AssessmentDiagnosticsInfo, PreRunDecision
)
from .pre_run_predictor import PreRunPredictor, PreRunContext
from .diagnostics_evidence import DiagnosticsEvidenceStore

class ExecutionGateway:
    def __init__(self, workspace_root: Path, event_bus: EventBus, evidence_store: DiagnosticsEvidenceStore, predictors: List[PreRunPredictor]):
        self.workspace_root = workspace_root
        self.event_bus = event_bus
        self.evidence_store = evidence_store
        self.predictors = predictors

    def execute(self, request: ExecutionRequest, executor_callback: Callable[[], Any]) -> Any:
        # 1. Normalize and hash inline code
        if request.inline_code:
            request.target.inline_code_sha256 = hashlib.sha256(request.inline_code.encode("utf-8")).hexdigest()
            
        started_at = datetime.now(timezone.utc)
        
        # 2. Run predictors synchronously
        context = PreRunContext(self.workspace_root, self.evidence_store)
        
        all_findings = []
        predictor_results = []
        
        for p in self.predictors:
            start_p = time.time()
            try:
                findings, status, err_msg = p.analyze(request, context)
            except Exception as e:
                findings = []
                status = "failed"
                err_msg = str(e)[:200]
                
            dur_ms = int((time.time() - start_p) * 1000)
            all_findings.extend(findings)
            predictor_results.append(PredictorResult(
                name=p.name, status=status, duration_ms=dur_ms, error_message=err_msg
            ))
            
        # 3. Decision aggregation
        decision = PreRunDecision.NOT_ANALYZED.value
        
        blocks = any(f.blocks_execution for f in all_findings)
        warnings = any(f.severity == "warning" and not f.blocks_execution for f in all_findings)
        
        completed_predictors = [p for p in predictor_results if p.status == "completed"]
        
        if blocks:
            decision = PreRunDecision.BLOCK.value
        elif warnings:
            decision = PreRunDecision.WARN.value
        elif completed_predictors:
            decision = PreRunDecision.ALLOW.value
            
        execution_permitted = decision != PreRunDecision.BLOCK.value
        
        # Diagnostics snapshot info for the payload
        tp = request.target.path
        if tp:
            avail, snap_at, diags, is_current = self.evidence_store.get_evidence_for_path(tp)
            stale_count = len(diags) if not is_current else 0
            curr_count = len(diags) if is_current else 0
            diag_info = AssessmentDiagnosticsInfo(
                snapshot_available=avail,
                snapshot_completed_at=snap_at,
                matching_count=len(diags),
                current_matching_count=curr_count,
                stale_matching_count=stale_count
            )
        else:
            diag_info = AssessmentDiagnosticsInfo(
                snapshot_available=False,
                snapshot_completed_at=None,
                matching_count=0,
                current_matching_count=0,
                stale_matching_count=0
            )
            
        # Summary
        summary = PreRunSummary(
            blocking_count=sum(1 for f in all_findings if f.blocks_execution),
            warning_count=sum(1 for f in all_findings if f.severity == "warning"),
            information_count=sum(1 for f in all_findings if f.severity == "information"),
            total_count=len(all_findings)
        )
        
        # Sort findings
        def sort_key(f: PreRunFinding):
            return (
                0 if f.blocks_execution else 1,
                0 if f.severity == "error" else (1 if f.severity == "warning" else 2),
                f.path or "",
                f.range.start.line if f.range else float('inf'),
                f.range.start.character if f.range else float('inf'),
                f.predictor,
                f.code,
                f.message
            )
        all_findings.sort(key=sort_key)
        
        # Deduplicate exactly
        deduped = []
        seen = set()
        for f in all_findings:
            rng_tuple = None
            if f.range:
                rng_tuple = (f.range.start.line, f.range.start.character, f.range.end.line, f.range.end.character)
            sig = (f.predictor, f.category, f.severity, f.code, f.message, f.path, rng_tuple, f.blocks_execution)
            if sig not in seen:
                seen.add(sig)
                deduped.append(f)
                
        completed_at = datetime.now(timezone.utc)
        duration_ms = int((completed_at - started_at).total_seconds() * 1000)
        
        # 4. Construct immutable assessment
        assessment = PreRunAssessment(
            schema_version=1,
            request_id=request.request_id,
            execution_kind=request.execution_kind,
            target=request.target,
            started_at=started_at.isoformat(),
            completed_at=completed_at.isoformat(),
            duration_ms=duration_ms,
            decision=decision,
            execution_permitted=execution_permitted,
            findings=deduped,
            diagnostics=diag_info,
            summary=summary,
            predictors=predictor_results
        )
        
        # Emit
        self.event_bus.publish("perception.dev.pre_run_assessment", assessment.to_dict())
        
        # 5. Route
        if not execution_permitted:
            return {
                "status": "blocked",
                "request_id": request.request_id,
                "findings": [f.to_dict() for f in deduped if f.blocks_execution]
            }
            
        # 6. Invoke executor
        return executor_callback()
