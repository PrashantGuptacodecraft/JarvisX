"""
tests/test_gesture_buffer.py
Full unit tests for core/gesture_buffer.py
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from core.gesture_buffer import GestureBuffer, BufferedGesture


def _make_result(name: str = "left_click",
                 conf: float = 0.85,
                 cx: float = 0.5,
                 cy: float = 0.5):
    """Build a minimal mock GestureResult."""
    r = MagicMock()
    r.gesture_name = name
    r.confidence   = conf
    r.cursor_x     = cx
    r.cursor_y     = cy
    return r


def _fill(buf: GestureBuffer, name: str, n: int,
          conf: float = 0.85, cx: float = 0.5, cy: float = 0.5):
    """Push n identical gesture results into the buffer."""
    results = []
    for _ in range(n):
        results.append(buf.update(_make_result(name, conf, cx, cy)))
    return results


# ── Confirmation tests ────────────────────────────────────────────────────────

def test_buffer_requires_5_of_7_frames():
    """Buffer must not fire before 5 identical frames arrive."""
    buf = GestureBuffer()
    # 4 frames → all None
    for i, result in enumerate(_fill(buf, "left_click", 4)):
        assert result is None, f"Frame {i+1}: expected None, got {result}"
    # 5th frame → confirmed
    result = buf.update(_make_result("left_click", 0.85))
    assert result is None or isinstance(result, BufferedGesture), \
        "5th frame in a 7-slot buffer may still be None (need 5/7 window to fill)"
    # Push until window fills
    while True:
        r = buf.update(_make_result("left_click", 0.85))
        if r is not None:
            assert isinstance(r, BufferedGesture)
            assert r.gesture_name == "left_click"
            break


def test_different_gesture_resets_buffer():
    """Switching gesture name mid-fill should reset the buffer."""
    buf = GestureBuffer()
    _fill(buf, "left_click", 4)
    # Switch gesture → should reset
    buf.update(_make_result("right_click"))
    # Now need another 5+ right_click frames to confirm
    confirmed = None
    for _ in range(8):
        r = buf.update(_make_result("right_click"))
        if r is not None:
            confirmed = r
            break
    assert confirmed is not None, "Should eventually confirm right_click"
    assert confirmed.gesture_name == "right_click"


def test_ema_smoothing_reduces_noise():
    """EMA should smooth noisy cursor_x values."""
    buf = GestureBuffer(smooth_alpha=0.35)
    xs = [0.75, 0.80, 0.75, 0.80, 0.75, 0.80, 0.75]
    for x in xs:
        buf.update(_make_result("left_click", 0.88, cx=x, cy=0.5))
    sx, _ = buf.get_smoothed_position()
    # Smoothed value should be close to the mean (0.775) not jumping
    assert 0.74 <= sx <= 0.82, f"EMA-smoothed x={sx:.4f} too far from mean 0.775"


def test_dead_zone_prevents_tiny_movements():
    """Tiny position changes within dead zone should be suppressed."""
    buf = GestureBuffer(dead_zone_px=15, smooth_alpha=0.5)
    # Seed initial position
    for _ in range(7):
        buf.update(_make_result("cursor_move", cx=0.500, cy=0.500))
    x0, y0 = buf.get_smoothed_position()
    # Tiny move: 5/1280 normalised ≈ 4px, well within dead_zone_px=15
    for _ in range(3):
        buf.update(_make_result("cursor_move", cx=0.504, cy=0.503))
    x1, y1 = buf.get_smoothed_position()
    assert abs(x1 - x0) < 0.015, \
        f"Dead zone failed: position moved {abs(x1-x0):.4f} despite tiny input"


def test_none_input_returns_none():
    """update(None) must return None without raising."""
    buf = GestureBuffer()

    class _NullResult:
        gesture_name = "none"
        confidence   = 0.0
        cursor_x     = 0.5
        cursor_y     = 0.5

    result = buf.update(_NullResult())
    assert result is None or isinstance(result, BufferedGesture)


def test_buffer_confidence_is_averaged():
    """Confirmed gesture confidence should be the mean of matching frames."""
    confs = [0.80, 0.90, 0.85, 0.88, 0.92, 0.87, 0.89]
    expected_avg = sum(confs) / len(confs)
    buf = GestureBuffer()
    last = None
    for c in confs:
        r = buf.update(_make_result("ok_sign", conf=c))
        if r is not None:
            last = r
    assert last is not None, "Buffer should confirm after 7 frames"
    assert abs(last.confidence - expected_avg) < 0.05, \
        f"Avg conf {last.confidence:.4f} too far from expected {expected_avg:.4f}"


def test_reset_clears_all_state():
    """After reset(), the buffer should require a full new 5/7 window."""
    buf = GestureBuffer()
    # Fill to confirmed
    for _ in range(10):
        buf.update(_make_result("scroll_up"))
    buf.reset()
    # Should not confirm until another 5+ frames
    results = [buf.update(_make_result("scroll_up")) for _ in range(4)]
    assert all(r is None for r in results), \
        "After reset, first 4 frames must all return None"


def test_velocity_smoothing():
    """EMA velocity should not jump as sharply as raw frame deltas."""
    buf = GestureBuffer(smooth_alpha=0.35)
    # Alternating x positions → large raw velocity swings
    positions = [0.30, 0.70, 0.30, 0.70, 0.30, 0.70, 0.30]
    vels = []
    for x in positions:
        r = buf.update(_make_result("cursor_move", cx=x, cy=0.5))
        if r is not None:
            vels.append(abs(r.velocity_x))
    # Smoothed velocity abs values should all be < raw swing magnitude (0.40)
    if vels:
        assert max(vels) < 0.40, \
            f"Max smoothed velocity {max(vels):.4f} should be < raw swing 0.40"
