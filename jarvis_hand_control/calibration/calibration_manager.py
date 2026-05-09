"""
calibration/calibration_manager.py
Manages hand calibration data: load, save, apply to thresholds and coordinates.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

CALIBRATION_VERSION = 2


@dataclass
class CalibrationData:
    """All hand calibration parameters persisted as JSON."""
    hand_size_baseline:         float = 0.25    # wrist→middle_tip normalised distance
    closed_compression_ratio:   float = 0.55    # ratio of closed vs open hand size
    corner_mappings: dict = field(default_factory=lambda: {
        "TL": [0.10, 0.10],
        "TR": [0.90, 0.10],
        "BL": [0.10, 0.85],
        "BR": [0.90, 0.85],
    })
    click_distance_threshold:   float = 28.0    # normalised × 1000 ≈ pixels
    calibrated_at:              str   = ""
    calibration_version:        int   = CALIBRATION_VERSION

    def __post_init__(self):
        if not self.calibrated_at:
            self.calibrated_at = datetime.now(timezone.utc).isoformat()


class CalibrationManager:
    """
    Loads and saves CalibrationData to/from a JSON file.
    Provides methods to adjust thresholds and map coordinates
    using bilinear interpolation over 4 calibrated corners.
    """

    def __init__(self, calibration_file_path: str) -> None:
        self._path:           Path = Path(calibration_file_path)
        self._data:           Optional[CalibrationData] = None
        self.needs_calibration: bool = True

        loaded = self.load()
        if loaded is not None:
            self._data         = loaded
            self.needs_calibration = False
            log.info("Calibration loaded from %s", self._path)
        else:
            log.info("No calibration found at %s — calibration required", self._path)

    # ── Persistence ───────────────────────────────────────────────────────────

    def save(self, calibration_data: CalibrationData) -> None:
        """Persist CalibrationData to JSON file."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self._path.open("w", encoding="utf-8") as f:
                json.dump(asdict(calibration_data), f, indent=2)
            self._data           = calibration_data
            self.needs_calibration = False
            log.info("Calibration saved to %s", self._path)
        except Exception as exc:
            log.error("Failed to save calibration: %s", exc)

    def load(self) -> Optional[CalibrationData]:
        """Load CalibrationData from JSON file. Returns None if not found."""
        if not self._path.exists():
            return None
        try:
            with self._path.open(encoding="utf-8") as f:
                raw = json.load(f)
            # Handle older calibration versions
            if raw.get("calibration_version", 1) < CALIBRATION_VERSION:
                log.warning("Calibration file is outdated (v%d) — re-calibration recommended",
                            raw.get("calibration_version", 1))
            return CalibrationData(**{
                k: v for k, v in raw.items()
                if k in CalibrationData.__dataclass_fields__
            })
        except Exception as exc:
            log.error("Failed to load calibration: %s", exc)
            return None

    def is_calibrated(self) -> bool:
        return not self.needs_calibration and self._data is not None

    def reset(self) -> None:
        """Delete the calibration file and reset to uncalibrated state."""
        try:
            if self._path.exists():
                self._path.unlink()
                log.info("Calibration file deleted: %s", self._path)
        except Exception as exc:
            log.error("Failed to delete calibration file: %s", exc)
        self._data             = None
        self.needs_calibration = True

    def get_data(self) -> Optional[CalibrationData]:
        return self._data

    # ── Threshold adjustment ──────────────────────────────────────────────────

    def get_adjusted_threshold(self, base_threshold: float) -> float:
        """
        Scale base_threshold based on hand size ratio relative to baseline.
        Larger hand → higher threshold (fingertips are farther apart in pixels).
        Smaller hand → lower threshold.
        Returns adjusted threshold.
        """
        if self._data is None:
            return base_threshold
        baseline = max(self._data.hand_size_baseline, 1e-6)
        # Default normalised hand size at calibration (used as divisor)
        # We scale linearly: threshold ∝ hand_size
        scale = self._data.hand_size_baseline / 0.25   # 0.25 = "average" baseline
        return round(base_threshold * scale, 2)

    # ── Coordinate mapping ────────────────────────────────────────────────────

    def get_mapped_position(self, landmark_x: float,
                             landmark_y: float,
                             screen_w: int = 1920,
                             screen_h: int = 1080) -> tuple[int, int]:
        """
        Map normalised landmark position to screen pixels using bilinear
        interpolation between the 4 calibrated corner positions.

        If not calibrated, falls back to linear mapping with 10% edge crop.
        """
        if self._data is None or self.needs_calibration:
            sx = int((landmark_x - 0.10) / 0.80 * screen_w)
            sy = int((landmark_y - 0.10) / 0.75 * screen_h)
            return (
                max(0, min(sx, screen_w - 1)),
                max(0, min(sy, screen_h - 1)),
            )

        cm = self._data.corner_mappings
        tl = cm.get("TL", [0.10, 0.10])
        tr = cm.get("TR", [0.90, 0.10])
        bl = cm.get("BL", [0.10, 0.85])
        br = cm.get("BR", [0.90, 0.85])

        # Bilinear interpolation in normalised space
        # First normalise landmark within calibrated bounding region
        x_lo = (tl[0] + bl[0]) / 2.0
        x_hi = (tr[0] + br[0]) / 2.0
        y_lo = (tl[1] + tr[1]) / 2.0
        y_hi = (bl[1] + br[1]) / 2.0

        tx = (landmark_x - x_lo) / max(x_hi - x_lo, 1e-6)
        ty = (landmark_y - y_lo) / max(y_hi - y_lo, 1e-6)

        tx = max(0.0, min(tx, 1.0))
        ty = max(0.0, min(ty, 1.0))

        sx = int(tx * screen_w)
        sy = int(ty * screen_h)
        return max(0, min(sx, screen_w - 1)), max(0, min(sy, screen_h - 1))
