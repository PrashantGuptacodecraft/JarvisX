import ast
import time
from pathlib import Path
from typing import Tuple, List, Optional, Protocol

from .pre_run_model import (
    ExecutionRequest, PreRunFinding, FindingEvidence, ExecutionKind,
    PreRunSeverity, PredictionConfidence, PredictorStatus, DiagnosticRange
)
from .diagnostics_evidence import DiagnosticsEvidenceStore
from .diagnostics_model import DiagnosticPosition

class PreRunContext:
    def __init__(self, workspace_root: Path, evidence_store: DiagnosticsEvidenceStore):
        self.workspace_root = workspace_root
        self.evidence_store = evidence_store

class PreRunPredictor(Protocol):
    @property
    def name(self) -> str:
        ...

    def analyze(self, request: ExecutionRequest, context: PreRunContext) -> Tuple[List[PreRunFinding], PredictorStatus, str]:
        ...

class ExecutionStructurePredictor(PreRunPredictor):
    @property
    def name(self) -> str:
        return "execution_structure"

    def analyze(self, request: ExecutionRequest, context: PreRunContext) -> Tuple[List[PreRunFinding], PredictorStatus, str]:
        findings = []
        
        # Working directory
        wd = request.target.working_directory
        if wd:
            p = context.workspace_root / wd
            if not p.exists() or not p.is_dir():
                findings.append(PreRunFinding(
                    predictor=self.name,
                    category="invalid_working_directory",
                    severity=PreRunSeverity.ERROR.value,
                    confidence=PredictionConfidence.HIGH.value,
                    code="WORKING_DIRECTORY_NOT_FOUND",
                    message=f"Working directory '{wd}' does not exist.",
                    path=wd,
                    range=None,
                    blocks_execution=True,
                    evidence=FindingEvidence(source="execution_structure")
                ))

        # Target Path
        tp = request.target.path
        if tp:
            p = context.workspace_root / tp
            try:
                p.resolve().relative_to(context.workspace_root.resolve())
            except ValueError:
                findings.append(PreRunFinding(
                    predictor=self.name,
                    category="workspace_violation",
                    severity=PreRunSeverity.ERROR.value,
                    confidence=PredictionConfidence.HIGH.value,
                    code="TARGET_OUTSIDE_WORKSPACE",
                    message=f"Target path '{tp}' escapes workspace.",
                    path=tp,
                    range=None,
                    blocks_execution=True,
                    evidence=FindingEvidence(source="execution_structure")
                ))
            else:
                if not p.exists():
                    findings.append(PreRunFinding(
                        predictor=self.name,
                        category="missing_target",
                        severity=PreRunSeverity.ERROR.value,
                        confidence=PredictionConfidence.HIGH.value,
                        code="EXECUTION_TARGET_NOT_FOUND",
                        message=f"Target path '{tp}' does not exist.",
                        path=tp,
                        range=None,
                        blocks_execution=True,
                        evidence=FindingEvidence(source="execution_structure")
                    ))
                
        # Empty argv
        if request.execution_kind == ExecutionKind.TERMINAL.value and request.argv is not None:
            if not request.argv and not request.raw_shell:
                findings.append(PreRunFinding(
                    predictor=self.name,
                    category="invalid_request",
                    severity=PreRunSeverity.ERROR.value,
                    confidence=PredictionConfidence.HIGH.value,
                    code="INVALID_EXECUTION_REQUEST",
                    message="Empty executable argument vector.",
                    path=None,
                    range=None,
                    blocks_execution=True,
                    evidence=FindingEvidence(source="execution_structure")
                ))
                
        # Unsupported language
        if request.execution_kind == ExecutionKind.CODE_SANDBOX.value and request.target.language and request.target.language.lower() != "python":
            findings.append(PreRunFinding(
                predictor=self.name,
                category="unsupported_language",
                severity=PreRunSeverity.INFORMATION.value,
                confidence=PredictionConfidence.HIGH.value,
                code="LANGUAGE_NOT_ANALYZED",
                message=f"Language '{request.target.language}' is not supported for deep analysis.",
                path=tp,
                range=None,
                blocks_execution=False, # Must not block!
                evidence=FindingEvidence(source="execution_structure")
            ))

        return findings, PredictorStatus.COMPLETED.value, ""

class PythonSyntaxPredictor(PreRunPredictor):
    @property
    def name(self) -> str:
        return "python_syntax"
        
    def _is_python_invocation(self, request: ExecutionRequest) -> bool:
        if request.execution_kind == ExecutionKind.CODE_SANDBOX.value:
            return request.target.language and request.target.language.lower() == "python"
            
        if request.execution_kind == ExecutionKind.TERMINAL.value:
            # File
            tp = request.target.path
            if tp and tp.endswith(".py"):
                return True
                
            # inline python -c
            if request.argv and len(request.argv) >= 2 and request.argv[0] in ("python", "python3") and request.argv[1] == "-c":
                return True
                
        return False

    def analyze(self, request: ExecutionRequest, context: PreRunContext) -> Tuple[List[PreRunFinding], PredictorStatus, str]:
        if not self._is_python_invocation(request):
            return [], PredictorStatus.NOT_APPLICABLE.value, ""
            
        code_to_parse = ""
        path_to_report = request.target.path
        
        # Determine code to parse
        if request.execution_kind == ExecutionKind.CODE_SANDBOX.value:
            if request.inline_code:
                code_to_parse = request.inline_code
            elif request.target.path:
                p = context.workspace_root / request.target.path
                if p.exists():
                    try:
                        code_to_parse = p.read_text(encoding="utf-8")
                    except Exception:
                        return [], PredictorStatus.DEGRADED.value, "Could not read target source"
                        
        elif request.execution_kind == ExecutionKind.TERMINAL.value:
            if request.argv and len(request.argv) >= 3 and request.argv[1] == "-c":
                code_to_parse = request.argv[2]
            elif request.target.path:
                p = context.workspace_root / request.target.path
                if p.exists():
                    try:
                        code_to_parse = p.read_text(encoding="utf-8")
                    except Exception:
                        return [], PredictorStatus.DEGRADED.value, "Could not read target source"
                        
        if not code_to_parse:
            return [], PredictorStatus.NOT_APPLICABLE.value, ""
            
        if len(code_to_parse.encode("utf-8")) > 10 * 1024 * 1024:
            return [], PredictorStatus.DEGRADED.value, "Source file exceeds 10MB limit for analysis"
            
        try:
            ast.parse(code_to_parse, filename=path_to_report or "<string>")
            return [], PredictorStatus.COMPLETED.value, ""
        except SyntaxError as e:
            cat = "indentation_error" if "indent" in str(e).lower() else "syntax_error"
            code_enum = "PYTHON_INDENTATION_ERROR" if cat == "indentation_error" else "PYTHON_SYNTAX_ERROR"
            
            line = getattr(e, "lineno", 1) or 1
            offset = getattr(e, "offset", 1) or 1
            
            # End points
            end_line = getattr(e, "end_lineno", line) or line
            end_offset = getattr(e, "end_offset", offset + 1) or (offset + 1)
            
            # To 0-based
            rng = DiagnosticRange(
                start=DiagnosticPosition(line=max(0, line - 1), character=max(0, offset - 1)),
                end=DiagnosticPosition(line=max(0, end_line - 1), character=max(0, end_offset - 1))
            )
            
            finding = PreRunFinding(
                predictor=self.name,
                category=cat,
                severity=PreRunSeverity.ERROR.value,
                confidence=PredictionConfidence.HIGH.value,
                code=code_enum,
                message=str(e.msg),
                path=path_to_report,
                range=rng,
                blocks_execution=True,
                evidence=FindingEvidence(source="python_parser")
            )
            return [finding], PredictorStatus.COMPLETED.value, ""
        except Exception as e:
            return [], PredictorStatus.FAILED.value, f"Parser error: {e}"
            
class D7DiagnosticsPredictor(PreRunPredictor):
    @property
    def name(self) -> str:
        return "d7_diagnostics"

    def analyze(self, request: ExecutionRequest, context: PreRunContext) -> Tuple[List[PreRunFinding], PredictorStatus, str]:
        tp = request.target.path
        if not tp:
            return [], PredictorStatus.NOT_APPLICABLE.value, ""
            
        avail, snap_at, diags, is_current = context.evidence_store.get_evidence_for_path(tp)
        if not avail:
            return [], PredictorStatus.NOT_APPLICABLE.value, ""
            
        findings = []
        for d in diags:
            if not is_current:
                # Stale diagnostics -> informational evidence only
                findings.append(PreRunFinding(
                    predictor=self.name,
                    category="stale_diagnostic",
                    severity=PreRunSeverity.INFORMATION.value,
                    confidence=PredictionConfidence.LOW.value,
                    code="D7_DIAGNOSTICS_STALE",
                    message=d.message,
                    path=tp,
                    range=d.range if isinstance(d.range, DiagnosticRange) else None, # Needs to be parsed properly from dict if needed, but evidence store uses raw dict, let's parse it
                    blocks_execution=False,
                    evidence=FindingEvidence(source="d7", diagnostics_snapshot_completed_at=snap_at, diagnostics_current=False)
                ))
            else:
                if d.severity == "error":
                    sev = PreRunSeverity.WARNING.value # D7 errors don't automatically block!
                    blocks = False # "D7 errors must not automatically block execution"
                elif d.severity == "warning":
                    sev = PreRunSeverity.WARNING.value
                    blocks = False
                else:
                    sev = PreRunSeverity.INFORMATION.value
                    blocks = False
                    
                rng_obj = None
                if d.range and isinstance(d.range, dict):
                    try:
                        s = d.range.get("start", {})
                        e = d.range.get("end", {})
                        rng_obj = DiagnosticRange(
                            start=DiagnosticPosition(line=s.get("line", 0), character=s.get("character", 0)),
                            end=DiagnosticPosition(line=e.get("line", 0), character=e.get("character", 0))
                        )
                    except:
                        pass
                        
                findings.append(PreRunFinding(
                    predictor=self.name,
                    category="static_diagnostic",
                    severity=sev,
                    confidence=PredictionConfidence.MEDIUM.value,
                    code="D7_STATIC_DIAGNOSTIC",
                    message=d.message,
                    path=tp,
                    range=rng_obj,
                    blocks_execution=blocks,
                    evidence=FindingEvidence(source="d7", diagnostics_snapshot_completed_at=snap_at, diagnostics_current=True)
                ))
                
        return findings, PredictorStatus.COMPLETED.value, ""
