import json
import subprocess
import time
from pathlib import Path
from typing import List, Tuple

from .diagnostics_model import (
    DiagnosticProvider, DiagnosticProviderResult, CodeDiagnostic,
    DiagnosticToolResult, DiagnosticRange, DiagnosticPosition, DiagnosticFix,
    DiagnosticExecutionStatus, DiagnosticSeverity
)

class BaseSubprocessProvider:
    def __init__(self, executable_args: List[str], timeout_seconds: float, max_output_bytes: int):
        self.executable_args = executable_args
        self.timeout_seconds = timeout_seconds
        self.max_output_bytes = max_output_bytes

    def _run_subprocess(self, cwd: Path, targets: Tuple[str, ...]) -> Tuple[str, int, str, float]:
        args = self.executable_args + list(targets)
        start_time = time.time()
        
        try:
            # We don't want to capture strictly bounded via subprocess.run easily without a custom loop, 
            # but for D7 we can just use communicate with timeout and enforce length later,
            # or for safety, we could use Popen and read up to max_bytes.
            # We will use run and truncate for simplicity as per common practice,
            # unless the payload is extremely massive.
            proc = subprocess.run(
                args,
                cwd=str(cwd),
                shell=False,
                capture_output=True,
                timeout=self.timeout_seconds,
                text=True,
                encoding='utf-8',
                errors='replace'
            )
            duration_ms = int((time.time() - start_time) * 1000)
            
            out = proc.stdout
            if len(out) > self.max_output_bytes:
                out = out[:self.max_output_bytes]
                
            return DiagnosticExecutionStatus.COMPLETED.value, proc.returncode, out, duration_ms
            
        except subprocess.TimeoutExpired:
            duration_ms = int((time.time() - start_time) * 1000)
            return DiagnosticExecutionStatus.TIMED_OUT.value, -1, "", duration_ms
        except FileNotFoundError:
            duration_ms = int((time.time() - start_time) * 1000)
            return DiagnosticExecutionStatus.UNAVAILABLE.value, -1, "", duration_ms
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            return DiagnosticExecutionStatus.EXECUTION_FAILED.value, -1, str(e)[:200], duration_ms

    def _normalize_path(self, raw_path: str, cwd: Path) -> str:
        # Convert path to workspace-relative POSIX
        p = Path(raw_path)
        if not p.is_absolute():
            p = (cwd / p)
        p = p.resolve()
        
        try:
            rel = p.relative_to(cwd.resolve())
            return rel.as_posix()
        except ValueError:
            # Outside workspace
            return ""

class RuffDiagnosticProvider(BaseSubprocessProvider, DiagnosticProvider):
    @property
    def name(self) -> str:
        return "ruff"

    def collect(self, workspace_root: Path, targets: Tuple[str, ...]) -> DiagnosticProviderResult:
        status, exit_code, stdout, duration = self._run_subprocess(workspace_root, targets)
        
        if status != DiagnosticExecutionStatus.COMPLETED.value:
            return DiagnosticProviderResult(
                diagnostics=[],
                tool_result=DiagnosticToolResult(
                    name=self.name, version="unknown", status=status, exit_code=exit_code, 
                    duration_ms=duration, diagnostic_count=0, error_message=stdout if status == DiagnosticExecutionStatus.EXECUTION_FAILED.value else None
                )
            )
            
        try:
            if not stdout.strip():
                data = []
            else:
                data = json.loads(stdout)
                
            if not isinstance(data, list):
                raise ValueError("Expected list")
        except Exception:
            return DiagnosticProviderResult(
                diagnostics=[],
                tool_result=DiagnosticToolResult(
                    name=self.name, version="unknown", status=DiagnosticExecutionStatus.INVALID_OUTPUT.value,
                    exit_code=exit_code, duration_ms=duration, diagnostic_count=0, error_message="Malformed JSON"
                )
            )

        diagnostics = []
        for item in data:
            path = self._normalize_path(item.get("filename", ""), workspace_root)
            if not path:
                continue # Skip outside workspace
                
            # Ruff 1-based, we want 0-based
            loc = item.get("location", {})
            end_loc = item.get("end_location", {})
            
            rng = None
            if loc and end_loc:
                # LSP coordinates
                # Ruff row is 1-based, col is 1-based (depending on ruff version, but JSON is 1-based)
                start = DiagnosticPosition(line=max(0, int(loc.get("row", 1)) - 1), character=max(0, int(loc.get("column", 1)) - 1))
                end = DiagnosticPosition(line=max(0, int(end_loc.get("row", 1)) - 1), character=max(0, int(end_loc.get("column", 1)) - 1))
                rng = DiagnosticRange(start=start, end=end)

            fix_avail = item.get("fix") is not None
            fix = DiagnosticFix(available=fix_avail, applicability="safe" if fix_avail else None)
            
            # Ruff doesn't emit native severity in standard json sometimes, default warning
            # But we check for "severity" if ruff adds it in newer versions
            sev = item.get("severity", "").lower()
            if sev not in [s.value for s in DiagnosticSeverity]:
                sev = DiagnosticSeverity.WARNING.value
                
            diagnostics.append(CodeDiagnostic(
                path=path,
                source=self.name,
                severity=sev,
                code=item.get("code"),
                message=item.get("message", ""),
                range=rng,
                fix=fix
            ))

        return DiagnosticProviderResult(
            diagnostics=diagnostics,
            tool_result=DiagnosticToolResult(
                name=self.name, version="unknown", status=DiagnosticExecutionStatus.COMPLETED.value,
                exit_code=exit_code, duration_ms=duration, diagnostic_count=len(diagnostics), error_message=None
            )
        )

class PyrightDiagnosticProvider(BaseSubprocessProvider, DiagnosticProvider):
    @property
    def name(self) -> str:
        return "pyright"

    def collect(self, workspace_root: Path, targets: Tuple[str, ...]) -> DiagnosticProviderResult:
        status, exit_code, stdout, duration = self._run_subprocess(workspace_root, targets)
        
        if status != DiagnosticExecutionStatus.COMPLETED.value:
            return DiagnosticProviderResult(
                diagnostics=[],
                tool_result=DiagnosticToolResult(
                    name=self.name, version="unknown", status=status, exit_code=exit_code, 
                    duration_ms=duration, diagnostic_count=0, error_message=stdout if status == DiagnosticExecutionStatus.EXECUTION_FAILED.value else None
                )
            )

        try:
            # Pyright JSON is an object with "generalDiagnostics"
            if not stdout.strip():
                raise ValueError("Empty output")
            data = json.loads(stdout)
            raw_diags = data.get("generalDiagnostics", [])
            version = data.get("version", "unknown")
        except Exception:
            return DiagnosticProviderResult(
                diagnostics=[],
                tool_result=DiagnosticToolResult(
                    name=self.name, version="unknown", status=DiagnosticExecutionStatus.INVALID_OUTPUT.value,
                    exit_code=exit_code, duration_ms=duration, diagnostic_count=0, error_message="Malformed JSON"
                )
            )

        diagnostics = []
        for item in raw_diags:
            path = self._normalize_path(item.get("file", ""), workspace_root)
            if not path:
                continue
                
            rng_data = item.get("range", {})
            start_data = rng_data.get("start", {})
            end_data = rng_data.get("end", {})
            
            rng = None
            if start_data and end_data:
                # pyright JSON uses 0-based for both line and character natively!
                start = DiagnosticPosition(line=int(start_data.get("line", 0)), character=int(start_data.get("character", 0)))
                end = DiagnosticPosition(line=int(end_data.get("line", 0)), character=int(end_data.get("character", 0)))
                rng = DiagnosticRange(start=start, end=end)
                
            sev_raw = item.get("severity", "information").lower()
            if sev_raw not in [s.value for s in DiagnosticSeverity]:
                sev_raw = DiagnosticSeverity.INFORMATION.value
                
            diagnostics.append(CodeDiagnostic(
                path=path,
                source=self.name,
                severity=sev_raw,
                code=item.get("rule"),
                message=item.get("message", ""),
                range=rng,
                fix=DiagnosticFix(available=False, applicability=None)
            ))

        return DiagnosticProviderResult(
            diagnostics=diagnostics,
            tool_result=DiagnosticToolResult(
                name=self.name, version=version, status=DiagnosticExecutionStatus.COMPLETED.value,
                exit_code=exit_code, duration_ms=duration, diagnostic_count=len(diagnostics), error_message=None
            )
        )
