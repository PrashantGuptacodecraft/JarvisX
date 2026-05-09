"""
tests/conftest.py
Shared pytest fixtures for the JARVIS gesture control test suite.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock

import numpy as np
import pytest

# ── Landmark helpers ──────────────────────────────────────────────────────────

def _make_lm(x: float, y: float, z: float = 0.0) -> MagicMock:
    lm = MagicMock()
    lm.x = x; lm.y = y; lm.z = z
    return lm


def _landmarks_array_to_list(arr: np.ndarray) -> list:
    """Convert (21, 3) numpy array to list of mock landmark objects."""
    return [_make_lm(arr[i, 0], arr[i, 1], arr[i, 2]) for i in range(21)]


# ── Open palm (all 5 fingers extended) ───────────────────────────────────────

@pytest.fixture
def mock_landmarks_flat() -> np.ndarray:
    """
    (21, 3) array representing an open palm with all fingers extended.
    Wrist at bottom-center; fingertips fanned out above.
    Angles at PIP/DIP joints are straight (<35°).
    """
    lm = np.zeros((21, 3), dtype=np.float32)

    # Wrist
    lm[0]  = [0.50, 0.85, 0.0]
    # Thumb (angled out to the right)
    lm[1]  = [0.42, 0.78, 0.0]   # CMC
    lm[2]  = [0.38, 0.72, 0.0]   # MCP
    lm[3]  = [0.34, 0.66, 0.0]   # IP
    lm[4]  = [0.30, 0.60, 0.0]   # TIP
    # Index (straight up)
    lm[5]  = [0.45, 0.72, 0.0]   # MCP
    lm[6]  = [0.45, 0.62, 0.0]   # PIP
    lm[7]  = [0.45, 0.52, 0.0]   # DIP
    lm[8]  = [0.45, 0.42, 0.0]   # TIP
    # Middle
    lm[9]  = [0.50, 0.71, 0.0]
    lm[10] = [0.50, 0.60, 0.0]
    lm[11] = [0.50, 0.50, 0.0]
    lm[12] = [0.50, 0.40, 0.0]
    # Ring
    lm[13] = [0.55, 0.72, 0.0]
    lm[14] = [0.55, 0.62, 0.0]
    lm[15] = [0.55, 0.52, 0.0]
    lm[16] = [0.55, 0.42, 0.0]
    # Pinky
    lm[17] = [0.60, 0.74, 0.0]
    lm[18] = [0.60, 0.65, 0.0]
    lm[19] = [0.60, 0.57, 0.0]
    lm[20] = [0.60, 0.49, 0.0]

    return lm


# ── Fist (all fingers bent) ───────────────────────────────────────────────────

@pytest.fixture
def mock_landmarks_fist() -> np.ndarray:
    """
    (21, 3) array representing a closed fist.
    All finger tips curl back toward the palm.
    Angles at PIP joints are large (>65°).
    """
    lm = np.zeros((21, 3), dtype=np.float32)

    lm[0]  = [0.50, 0.85, 0.0]   # Wrist
    # Thumb (bent inward)
    lm[1]  = [0.45, 0.80, 0.0]
    lm[2]  = [0.43, 0.76, 0.0]
    lm[3]  = [0.46, 0.74, 0.0]
    lm[4]  = [0.49, 0.72, 0.0]   # tip curls back
    # Index bent — MCP up, PIP curls, tip near palm
    lm[5]  = [0.46, 0.74, 0.0]   # MCP
    lm[6]  = [0.47, 0.68, 0.0]   # PIP (bends)
    lm[7]  = [0.48, 0.74, 0.0]   # DIP curls back down
    lm[8]  = [0.48, 0.80, 0.0]   # TIP at palm level
    # Middle
    lm[9]  = [0.50, 0.73, 0.0]
    lm[10] = [0.50, 0.67, 0.0]
    lm[11] = [0.50, 0.74, 0.0]
    lm[12] = [0.50, 0.80, 0.0]
    # Ring
    lm[13] = [0.53, 0.74, 0.0]
    lm[14] = [0.53, 0.68, 0.0]
    lm[15] = [0.53, 0.74, 0.0]
    lm[16] = [0.53, 0.80, 0.0]
    # Pinky
    lm[17] = [0.56, 0.76, 0.0]
    lm[18] = [0.56, 0.71, 0.0]
    lm[19] = [0.56, 0.76, 0.0]
    lm[20] = [0.56, 0.81, 0.0]

    return lm


# ── Peace sign (index + middle extended, tips 70px apart) ─────────────────────

@pytest.fixture
def mock_landmarks_peace() -> np.ndarray:
    """
    Peace sign: index + middle extended, ring + pinky bent.
    Index and middle tips are ~70 normalised-px apart (~0.055 normalised).
    """
    lm = np.zeros((21, 3), dtype=np.float32)

    lm[0]  = [0.50, 0.85, 0.0]
    # Thumb (partial)
    lm[1]  = [0.44, 0.80, 0.0]
    lm[2]  = [0.41, 0.76, 0.0]
    lm[3]  = [0.43, 0.73, 0.0]
    lm[4]  = [0.45, 0.70, 0.0]
    # Index — extended, slanted left
    lm[5]  = [0.46, 0.72, 0.0]
    lm[6]  = [0.44, 0.62, 0.0]
    lm[7]  = [0.42, 0.52, 0.0]
    lm[8]  = [0.40, 0.42, 0.0]   # TIP
    # Middle — extended, slanted right
    lm[9]  = [0.52, 0.71, 0.0]
    lm[10] = [0.54, 0.61, 0.0]
    lm[11] = [0.56, 0.51, 0.0]
    lm[12] = [0.58, 0.41, 0.0]   # TIP  (spread ~0.055 from index tip → ≈70px@1280)
    # Ring — bent
    lm[13] = [0.55, 0.73, 0.0]
    lm[14] = [0.55, 0.67, 0.0]
    lm[15] = [0.55, 0.73, 0.0]
    lm[16] = [0.55, 0.79, 0.0]
    # Pinky — bent
    lm[17] = [0.58, 0.76, 0.0]
    lm[18] = [0.58, 0.71, 0.0]
    lm[19] = [0.58, 0.76, 0.0]
    lm[20] = [0.58, 0.81, 0.0]

    return lm


# ── Misc fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture
def mock_frame() -> np.ndarray:
    """Black 720p frame."""
    return np.zeros((720, 1280, 3), dtype=np.uint8)


@pytest.fixture
def mock_settings():
    s = MagicMock()
    s.SCREEN_WIDTH   = 1920
    s.SCREEN_HEIGHT  = 1080
    s.DEAD_ZONE_PX   = 10
    s.SMOOTHING_ALPHA = 0.35
    s.SWIPE_THRESHOLD = 0.13
    s.FUSION_THRESHOLD = 0.72
    s.FUSION_TIME_WINDOW_MS = 1200
    s.WHISPER_MODEL  = "tiny"
    s.CAMERA_INDEX   = 0
    s.load_features  = MagicMock(return_value={
        "voice_fusion_enabled": True,
        "air_drawing_enabled":  True,
        "heatmap_enabled":      True,
        "ar_overlay_enabled":   False,
        "dual_hand_enabled":    True,
    })
    return s


@pytest.fixture
def mock_gesture_result():
    from core.gesture_classifier import GestureResult
    return GestureResult(
        gesture_name = "left_click",
        confidence   = 0.92,
        cursor_x     = 960.0,
        cursor_y     = 540.0,
        hand_label   = "Right",
        metadata     = {},
    )


@pytest.fixture
def mock_fusion_result():
    from core.voice_gesture_fusion import FusionResult
    return FusionResult(
        should_fire       = True,
        fusion_score      = 0.81,
        gesture_name      = "ok_sign",
        voice_phrase      = "save",
        action            = "ctrl_s",
        feedback          = "Saving document",
        suppressed_reason = "",
    )


@pytest.fixture
def mock_hand_data(mock_landmarks_flat):
    from core.hand_tracker import HandTrackingResult
    import numpy as np

    # Build list of 21 mock landmark objects from the flat array
    class _LM:
        def __init__(self, x, y, z):
            self.x = x; self.y = y; self.z = z

    lm_list = [_LM(mock_landmarks_flat[i,0],
                    mock_landmarks_flat[i,1],
                    mock_landmarks_flat[i,2]) for i in range(21)]

    return HandTrackingResult(
        landmarks_list     = [lm_list],
        handedness_list    = ["Right"],
        annotated_frame    = np.zeros((720, 1280, 3), dtype=np.uint8),
        hand_count         = 1,
        processing_time_ms = 12.5,
    )
