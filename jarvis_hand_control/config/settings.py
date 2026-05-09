"""
config/settings.py
Central typed settings dataclass for JARVIS Hand Gesture Control.
Loads all values from .env via python-dotenv with typed coercion.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# Load .env from the project root (parent of this config/ dir)
_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env", override=False)

log = logging.getLogger(__name__)


def _int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, default))
    except (ValueError, TypeError):
        return default


def _float(key: str, default: float) -> float:
    try:
        return float(os.environ.get(key, default))
    except (ValueError, TypeError):
        return default


def _bool(key: str, default: bool) -> bool:
    val = os.environ.get(key, str(default)).strip().lower()
    return val in ("1", "true", "yes", "on")


def _str(key: str, default: str) -> str:
    return os.environ.get(key, default)


@dataclass
class Settings:
    # ── Camera ────────────────────────────────────────────────────────────────
    CAMERA_INDEX: int = field(default_factory=lambda: _int("CAMERA_INDEX", 0))
    FRAME_WIDTH: int  = field(default_factory=lambda: _int("FRAME_WIDTH", 1280))
    FRAME_HEIGHT: int = field(default_factory=lambda: _int("FRAME_HEIGHT", 720))
    FPS_TARGET: int   = field(default_factory=lambda: _int("FPS_TARGET", 30))

    # ── Screen ────────────────────────────────────────────────────────────────
    SCREEN_WIDTH: int  = field(default_factory=lambda: _int("SCREEN_WIDTH", 1920))
    SCREEN_HEIGHT: int = field(default_factory=lambda: _int("SCREEN_HEIGHT", 1080))

    # ── Gesture Fusion ────────────────────────────────────────────────────────
    FUSION_THRESHOLD: float        = field(default_factory=lambda: _float("FUSION_THRESHOLD", 0.72))
    FUSION_TIME_WINDOW_MS: int     = field(default_factory=lambda: _int("FUSION_TIME_WINDOW_MS", 1200))

    # ── Voice ─────────────────────────────────────────────────────────────────
    WHISPER_MODEL: str = field(default_factory=lambda: _str("WHISPER_MODEL", "tiny"))

    # ── Dashboard ─────────────────────────────────────────────────────────────
    DASHBOARD_PORT: int       = field(default_factory=lambda: _int("DASHBOARD_PORT", 5050))
    DASHBOARD_AUTO_OPEN: bool = field(default_factory=lambda: _bool("DASHBOARD_AUTO_OPEN", True))

    # ── Virtual Camera ────────────────────────────────────────────────────────
    VIRTUAL_CAMERA_BACKEND: str = field(default_factory=lambda: _str("VIRTUAL_CAMERA_BACKEND", "auto"))

    # ── Debug / Logging ───────────────────────────────────────────────────────
    DEBUG_MODE: bool = field(default_factory=lambda: _bool("DEBUG_MODE", False))
    LOG_LEVEL: str   = field(default_factory=lambda: _str("LOG_LEVEL", "INFO"))

    # ── Cursor ────────────────────────────────────────────────────────────────
    DEAD_ZONE_PX: int        = field(default_factory=lambda: _int("DEAD_ZONE_PX", 10))
    SMOOTHING_ALPHA: float   = field(default_factory=lambda: _float("SMOOTHING_ALPHA", 0.35))
    SWIPE_THRESHOLD: float   = field(default_factory=lambda: _float("SWIPE_THRESHOLD", 0.13))
    PRECISION_SENSITIVITY: float     = field(default_factory=lambda: _float("PRECISION_SENSITIVITY", 0.55))
    PRESENTATION_SENSITIVITY: float  = field(default_factory=lambda: _float("PRESENTATION_SENSITIVITY", 1.9))

    # ── Paths ─────────────────────────────────────────────────────────────────
    CALIBRATION_FILE: str  = field(default_factory=lambda: _str("CALIBRATION_FILE", "config/hand_calibration.json"))
    DRAWING_SAVE_PATH: str = field(default_factory=lambda: _str("DRAWING_SAVE_PATH", "drawings/"))
    DB_PATH: str           = field(default_factory=lambda: _str("DB_PATH", "data/gesture_analytics.db"))
    FEATURES_FILE: str     = field(default_factory=lambda: _str("FEATURES_FILE", "config/features.json"))

    def __post_init__(self) -> None:
        # Apply log level immediately
        logging.getLogger().setLevel(getattr(logging, self.LOG_LEVEL, logging.INFO))
        # Ensure required directories exist
        for path_attr in ("DRAWING_SAVE_PATH",):
            p = Path(_ROOT / getattr(self, path_attr))
            p.mkdir(parents=True, exist_ok=True)
        db_dir = Path(_ROOT / self.DB_PATH).parent
        db_dir.mkdir(parents=True, exist_ok=True)

    def load_features(self) -> dict[str, Any]:
        """Read and return config/features.json as a dict."""
        features_path = _ROOT / self.FEATURES_FILE
        try:
            with features_path.open(encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            log.warning("features.json not found at %s — returning empty dict", features_path)
            return {}
        except json.JSONDecodeError as exc:
            log.error("features.json is malformed: %s", exc)
            return {}

    def is_feature_enabled(self, feature_key: str) -> bool:
        """Convenience: check a single feature flag."""
        return self.load_features().get(feature_key, False)

    def as_dict(self) -> dict[str, Any]:
        """Return all settings as a plain dict (useful for logging/debug)."""
        import dataclasses
        return dataclasses.asdict(self)


# ── Global singleton — import `cfg` everywhere ────────────────────────────────
cfg = Settings()
