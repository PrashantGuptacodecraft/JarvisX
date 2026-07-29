import os
from pathlib import Path
import configparser

from shared_core.dev_tools.style_model import CodingStyleModel, StyleEvidence, StyleEvidenceSource
from .event_models import DevEventEnvelope
from shared_core.event_bus.topics import PERCEPTION_DEV_CODING_STYLE_GENERATED
from shared_core.event_bus.bus import EventBus
import time
import datetime
from typing import Optional

class StyleAnalyzer:
    def __init__(self, workspace_root: str, event_bus: Optional[EventBus] = None):
        self.workspace_root = Path(workspace_root)
        self.event_bus = event_bus

    def analyze(self) -> CodingStyleModel:
        start_time = time.time()
        model = CodingStyleModel()
        
        # Check for .editorconfig
        editorconfig_path = self.workspace_root / ".editorconfig"
        if editorconfig_path.exists():
            try:
                config = configparser.ConfigParser()
                config.read(editorconfig_path)
                if "*" in config or "*.py" in config:
                    section = config["*.py"] if "*.py" in config else config["*"]
                    if "indent_style" in section:
                        model.indent_style = section["indent_style"]
                        model.evidences.append(StyleEvidence(
                            source=StyleEvidenceSource.CONFIG,
                            description=".editorconfig specified indent_style",
                            weight=1.0
                        ))
                    if "indent_size" in section:
                        model.indent_size = int(section["indent_size"])
                        model.evidences.append(StyleEvidence(
                            source=StyleEvidenceSource.CONFIG,
                            description=".editorconfig specified indent_size",
                            weight=1.0
                        ))
                    if "max_line_length" in section:
                        val = section["max_line_length"]
                        if val.isdigit():
                            model.max_line_length = int(val)
                            model.evidences.append(StyleEvidence(
                                source=StyleEvidenceSource.CONFIG,
                                description=".editorconfig specified max_line_length",
                                weight=1.0
                            ))
            except Exception:
                pass
                
        # Check pyproject.toml (e.g. for ruff/black line length)
        pyproject_path = self.workspace_root / "pyproject.toml"
        if pyproject_path.exists():
            content = pyproject_path.read_text(encoding="utf-8")
            if "line-length = " in content or "line_length = " in content:
                for line in content.splitlines():
                    if "line-length" in line or "line_length" in line:
                        try:
                            val = line.split("=")[1].strip()
                            model.max_line_length = int(val)
                            model.evidences.append(StyleEvidence(
                                source=StyleEvidenceSource.CONFIG,
                                description="pyproject.toml specified line length",
                                weight=1.0
                            ))
                            break
                        except Exception:
                            pass

        if self.event_bus:
            duration_ms = (time.time() - start_time) * 1000
            env = DevEventEnvelope(
                schema_version=1,
                event_type=PERCEPTION_DEV_CODING_STYLE_GENERATED,
                event_id=f"evt_{int(time.time()*1000)}",
                operation="coding_style_analysis",
                request_id=None,
                repository_id=None,
                occurred_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                duration_ms=duration_ms,
                status="success",
                summary={
                    "indent_style": model.indent_style,
                    "indent_size": model.indent_size,
                    "max_line_length": model.max_line_length,
                    "evidences": len(model.evidences)
                }
            )
            self.event_bus.publish(PERCEPTION_DEV_CODING_STYLE_GENERATED, env.to_dict())

        return model
