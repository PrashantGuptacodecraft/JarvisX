from typing import List, Tuple
from pathlib import Path
from datetime import datetime, timezone

from .diagnostics_model import (
    DiagnosticsConfig, DiagnosticsSnapshot, DiagnosticsSummary, 
    DiagnosticToolResult, CodeDiagnostic, DiagnosticProvider,
    DiagnosticsTrigger, DiagnosticsSnapshotStatus, DiagnosticExecutionStatus,
    DiagnosticSeverity
)

class DiagnosticsAnalyzer:
    def __init__(self, config: DiagnosticsConfig, providers: List[DiagnosticProvider]):
        self.config = config
        self.providers = providers
        self.workspace_root = Path(config.workspace_root).resolve()

    def analyze(self, trigger_kind: str, paths: List[str]) -> DiagnosticsSnapshot:
        started_at = datetime.now(timezone.utc)
        
        all_diagnostics = []
        all_tools = []
        
        for provider in self.providers:
            # We invoke the provider. If it's a file change, we might pass paths or default targets.
            # D7 requires pyright to scan project scope, ruff might accept paths.
            # But the interface just takes targets. If paths is empty, use target_paths.
            targets = tuple(paths) if (paths and trigger_kind == "file_changed") else tuple(self.config.target_paths)
            
            res = provider.collect(self.workspace_root, targets)
            all_diagnostics.extend(res.diagnostics)
            all_tools.append(res.tool_result)
            
        # Deduplicate and sort
        all_diagnostics = self._sort_and_deduplicate(all_diagnostics)
        
        completed_at = datetime.now(timezone.utc)
        duration_ms = int((completed_at - started_at).total_seconds() * 1000)
        
        # Summary
        summary = DiagnosticsSummary(
            error_count=sum(1 for d in all_diagnostics if d.severity == DiagnosticSeverity.ERROR.value),
            warning_count=sum(1 for d in all_diagnostics if d.severity == DiagnosticSeverity.WARNING.value),
            information_count=sum(1 for d in all_diagnostics if d.severity == DiagnosticSeverity.INFORMATION.value),
            hint_count=sum(1 for d in all_diagnostics if d.severity == DiagnosticSeverity.HINT.value),
            total_count=len(all_diagnostics)
        )
        
        # Status
        all_completed = all(t.status == DiagnosticExecutionStatus.COMPLETED.value for t in all_tools)
        any_completed = any(t.status == DiagnosticExecutionStatus.COMPLETED.value for t in all_tools)
        
        if all_completed or not all_tools:
            snap_status = DiagnosticsSnapshotStatus.COMPLETED.value
        elif any_completed:
            snap_status = DiagnosticsSnapshotStatus.PARTIAL.value
        else:
            snap_status = DiagnosticsSnapshotStatus.FAILED.value
            
        # Sort tools
        all_tools.sort(key=lambda t: t.name)
        
        trigger = DiagnosticsTrigger(kind=trigger_kind, paths=sorted(list(set(paths))))
        
        return DiagnosticsSnapshot(
            schema_version=1,
            trigger=trigger,
            started_at=started_at.isoformat(),
            completed_at=completed_at.isoformat(),
            duration_ms=duration_ms,
            status=snap_status,
            diagnostics=all_diagnostics,
            tools=all_tools,
            summary=summary
        )
        
    def _sort_and_deduplicate(self, diagnostics: List[CodeDiagnostic]) -> List[CodeDiagnostic]:
        def sort_key(d: CodeDiagnostic):
            return (
                d.path,
                d.range.start.line if d.range else float('inf'),
                d.range.start.character if d.range else float('inf'),
                d.severity,
                d.source,
                d.code if d.code is not None else "",
                d.message
            )
            
        diagnostics.sort(key=sort_key)
        
        deduped = []
        for d in diagnostics:
            if not deduped:
                deduped.append(d)
                continue
                
            last = deduped[-1]
            if sort_key(d) == sort_key(last):
                # exact duplicate
                # need to check end range too
                if d.range and last.range:
                    if d.range.end.line == last.range.end.line and d.range.end.character == last.range.end.character:
                        continue # Skip
                elif not d.range and not last.range:
                    continue # Skip
            deduped.append(d)
            
        return deduped
