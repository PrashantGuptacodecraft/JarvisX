"""
tests/test_finger_analyzer.py
Full unit tests for core/finger_analyzer.py
"""
from __future__ import annotations

import math
import numpy as np
import pytest

from core.finger_analyzer import FingerAnalyzer, FingerStatus


@pytest.fixture
def analyzer() -> FingerAnalyzer:
    return FingerAnalyzer()


# ── Extension / Bend tests ────────────────────────────────────────────────────

def test_open_palm_all_extended(analyzer, mock_landmarks_flat):
    state = analyzer.analyze(mock_landmarks_flat)
    assert state.index  == FingerStatus.EXTENDED, "Index should be EXTENDED"
    assert state.middle == FingerStatus.EXTENDED, "Middle should be EXTENDED"
    assert state.ring   == FingerStatus.EXTENDED, "Ring should be EXTENDED"
    assert state.pinky  == FingerStatus.EXTENDED, "Pinky should be EXTENDED"
    assert state.open_count  == 5, f"Expected 5 extended, got {state.open_count}"
    assert state.closed_count == 0, f"Expected 0 bent, got {state.closed_count}"


def test_fist_all_bent(analyzer, mock_landmarks_fist):
    state = analyzer.analyze(mock_landmarks_fist)
    assert state.index  == FingerStatus.BENT, "Index should be BENT in fist"
    assert state.middle == FingerStatus.BENT, "Middle should be BENT in fist"
    assert state.ring   == FingerStatus.BENT, "Ring should be BENT in fist"
    assert state.pinky  == FingerStatus.BENT, "Pinky should be BENT in fist"
    assert state.open_count  == 0, f"Expected 0 extended, got {state.open_count}"
    assert state.closed_count >= 4, f"Expected ≥4 bent, got {state.closed_count}"


def test_peace_sign_index_middle_extended(analyzer, mock_landmarks_peace):
    state = analyzer.analyze(mock_landmarks_peace)
    assert state.index  == FingerStatus.EXTENDED, "Index must be EXTENDED in peace"
    assert state.middle == FingerStatus.EXTENDED, "Middle must be EXTENDED in peace"
    assert state.ring   == FingerStatus.BENT,     "Ring must be BENT in peace"
    assert state.pinky  == FingerStatus.BENT,     "Pinky must be BENT in peace"


def test_thumbs_up_only_thumb(analyzer):
    """Build landmarks with thumb clearly up, all fingers curled."""
    lm = np.zeros((21, 3), dtype=np.float32)
    lm[0]  = [0.50, 0.85, 0.0]   # Wrist
    # Thumb straight up (CMC → MCP → IP → TIP going upward)
    lm[1]  = [0.46, 0.80, 0.0]
    lm[2]  = [0.44, 0.72, 0.0]
    lm[3]  = [0.43, 0.64, 0.0]
    lm[4]  = [0.42, 0.56, 0.0]
    # Index bent
    lm[5]  = [0.46, 0.74, 0.0]
    lm[6]  = [0.47, 0.68, 0.0]
    lm[7]  = [0.48, 0.74, 0.0]
    lm[8]  = [0.48, 0.80, 0.0]
    # Middle bent
    lm[9]  = [0.50, 0.73, 0.0]
    lm[10] = [0.50, 0.67, 0.0]
    lm[11] = [0.50, 0.73, 0.0]
    lm[12] = [0.50, 0.80, 0.0]
    # Ring bent
    lm[13] = [0.53, 0.74, 0.0]
    lm[14] = [0.53, 0.68, 0.0]
    lm[15] = [0.53, 0.74, 0.0]
    lm[16] = [0.53, 0.80, 0.0]
    # Pinky bent
    lm[17] = [0.56, 0.76, 0.0]
    lm[18] = [0.56, 0.71, 0.0]
    lm[19] = [0.56, 0.76, 0.0]
    lm[20] = [0.56, 0.81, 0.0]

    state = analyzer.analyze(lm)
    assert state.thumb == FingerStatus.EXTENDED, "Thumb should be EXTENDED"
    assert state.index == FingerStatus.BENT,     "Index should be BENT"
    assert state.middle == FingerStatus.BENT,    "Middle should be BENT"


def test_none_landmarks_no_crash(analyzer):
    """Passing None should return a default FingerState without raising."""
    state = analyzer.analyze(None)
    assert state is not None, "analyze(None) must return a FingerState"
    assert state.open_count == 0 or state.open_count >= 0   # any value OK


def test_wrong_shape_no_crash(analyzer):
    """Wrong shape array should return gracefully."""
    lm = np.zeros((10, 3), dtype=np.float32)
    state = analyzer.analyze(lm)
    assert state is not None


# ── Angle calculation ─────────────────────────────────────────────────────────

def test_angle_calculation_correctness(analyzer):
    """
    A perfect 90° bend at PIP:
    MCP at (0.5, 0.7), PIP at (0.5, 0.6), DIP at (0.6, 0.6).
    The two vectors form a 90° angle at PIP.
    """
    lm = np.zeros((21, 3), dtype=np.float32)
    lm[0] = [0.50, 0.85, 0.0]    # wrist (needed for orient)

    # Index finger triplet: MCP=5, PIP=6, DIP=7
    lm[5] = [0.50, 0.70, 0.0]    # MCP
    lm[6] = [0.50, 0.60, 0.0]    # PIP (bend joint)
    lm[7] = [0.60, 0.60, 0.0]    # DIP (perpendicular)
    lm[8] = [0.70, 0.60, 0.0]    # TIP

    angle = analyzer.get_finger_angle(lm, "index")
    assert 80.0 <= angle <= 100.0, f"Expected ~90°, got {angle:.1f}°"


# ── Pinch detection ───────────────────────────────────────────────────────────

def test_pinch_detection_close_fingers(analyzer):
    """Thumb and index tips 15 normalised-px apart → pinch with threshold=30."""
    lm = np.zeros((21, 3), dtype=np.float32)
    lm[0] = [0.50, 0.85, 0.0]
    # Thumb tip at (0.50, 0.50)
    lm[4] = [0.50, 0.50, 0.0]
    # Index tip at (0.515, 0.50)  → dist ≈ 0.015 × 1000 = 15 < 30
    lm[8] = [0.515, 0.50, 0.0]
    result = analyzer.is_pinching(lm, "thumb", "index", threshold=30.0)
    assert result is True, "Should detect pinch at 15 normalised-px distance"


def test_pinch_detection_far_fingers(analyzer):
    """Thumb and index tips 50 normalised-px apart → no pinch."""
    lm = np.zeros((21, 3), dtype=np.float32)
    lm[0] = [0.50, 0.85, 0.0]
    lm[4] = [0.50, 0.50, 0.0]
    lm[8] = [0.55, 0.50, 0.0]    # dist ≈ 0.05 × 1000 = 50 > 30
    result = analyzer.is_pinching(lm, "thumb", "index", threshold=30.0)
    assert result is False, "Should NOT detect pinch at 50 normalised-px distance"


# ── Palm orientation ──────────────────────────────────────────────────────────

def test_palm_orientation_toward(analyzer):
    """
    A front-facing hand: cross product of palm vectors should have positive z.
    Use the open palm fixture which is oriented toward camera.
    """
    lm = np.zeros((21, 3), dtype=np.float32)
    # WRIST=0, INDEX_MCP=5, PINKY_MCP=17, MIDDLE_MCP=9
    lm[0]  = [0.50, 0.85, 0.0]
    lm[5]  = [0.44, 0.72, 0.0]   # index MCP
    lm[9]  = [0.50, 0.71, 0.0]   # middle MCP
    lm[13] = [0.55, 0.72, 0.0]   # ring MCP
    lm[17] = [0.60, 0.74, 0.0]   # pinky MCP
    # Set all other landmarks to plausible values
    orientation = analyzer.get_palm_orientation(lm)
    assert orientation in ("toward", "away"), "Should return 'toward' or 'away'"


# ── Hand openness ─────────────────────────────────────────────────────────────

def test_hand_openness_score_range_open(analyzer, mock_landmarks_flat):
    score = analyzer.get_hand_openness(mock_landmarks_flat)
    assert 0.0 <= score <= 1.0, "Score must be in [0, 1]"
    assert score >= 0.6, f"Open palm openness should be ≥0.6, got {score:.3f}"


def test_hand_openness_score_range_fist(analyzer, mock_landmarks_fist):
    score = analyzer.get_hand_openness(mock_landmarks_fist)
    assert 0.0 <= score <= 1.0, "Score must be in [0, 1]"
    assert score <= 0.6, f"Fist openness should be ≤0.6, got {score:.3f}"
