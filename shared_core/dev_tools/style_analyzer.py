import os
from pathlib import Path
import configparser

from shared_core.dev_tools.style_model import CodingStyleModel, StyleEvidence, StyleEvidenceSource

class StyleAnalyzer:
    def __init__(self, workspace_root: str):
        self.workspace_root = Path(workspace_root)

    def analyze(self) -> CodingStyleModel:
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

        return model
