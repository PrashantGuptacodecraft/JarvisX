"""
tests/test_mouse_controller.py
Full unit tests for control/mouse_controller.py
All pyautogui calls are mocked — no screen interaction.
"""
from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest

# Patch pyautogui at import time so MouseController loads cleanly
_pag_mock = MagicMock()
_pag_mock.size.return_value = (1920, 1080)

import sys
sys.modules.setdefault("pyautogui", _pag_mock)

from control.mouse_controller import MouseController, _MUL_SLOW, _MUL_FAST, _EDGE_MULT


@pytest.fixture(autouse=True)
def reset_pag():
    """Reset pyautogui mock between tests."""
    _pag_mock.reset_mock()
    _pag_mock.size.return_value = (1920, 1080)
    yield


@pytest.fixture
def mouse() -> MouseController:
    m = MouseController()
    m._sw = 1920
    m._sh = 1080
    return m


# ── Slow movement ─────────────────────────────────────────────────────────────

def test_slow_movement_precision_sensitivity(mouse):
    """
    Cursor moves 2 normalised-px (very slow) → sensitivity multiplier ≤ _MUL_SLOW.
    The resulting screen coordinate should NOT overshoot linearly.
    """
    # Seed position at screen center
    mouse._prev_sx = 960.0
    mouse._prev_sy = 540.0

    # Small move: landmark at 0.501 (was 0.500) in X
    mouse.move(0.501, 0.500, frame_w=1280, frame_h=720)
    assert _pag_mock.moveTo.called, "moveTo must be called"
    args = _pag_mock.moveTo.call_args[0]
    x_result = args[0]
    # With small velocity, multiplier is 0.55 — result should be near center
    assert 900 < x_result < 1020, \
        f"Slow move: x={x_result} not in expected precision range (900–1020)"


# ── Fast movement ─────────────────────────────────────────────────────────────

def test_fast_movement_high_sensitivity(mouse):
    """Fast move: velocity above 0.15 → multiplier = 2.2."""
    mouse._prev_sx = 960.0
    mouse._prev_sy = 540.0
    # Large move: 0.20 normalised = 256px on 1280-wide frame
    mouse.move(0.70, 0.50, frame_w=1280, frame_h=720)
    assert _pag_mock.moveTo.called
    args = _pag_mock.moveTo.call_args[0]
    x_result = args[0]
    # Movement amplified — result should be well past center
    assert x_result > 960, \
        f"Fast move: x={x_result} should be > screen center 960"


# ── Edge magnetism ────────────────────────────────────────────────────────────

def test_edge_magnetism_near_left_edge(mouse):
    """Within 40px of left edge → x-axis slowed, y-axis unaffected."""
    mouse._prev_sx = 35.0    # already near left edge
    mouse._prev_sy = 540.0
    # Small move that would bring cursor further left
    mouse.move(0.12, 0.50, frame_w=1280, frame_h=720)
    assert _pag_mock.moveTo.called
    args = _pag_mock.moveTo.call_args[0]
    x_result = args[0]
    # With edge magnetism the cursor should stay clamped near/at edge, not negative
    assert x_result >= 0, "Edge magnetism must prevent negative x"
    assert x_result <= 100, \
        f"Edge magnetism: x={x_result} should stay near left edge, not jump far"


# ── Boundary clamping ─────────────────────────────────────────────────────────

def test_boundary_clamp_prevents_negative(mouse):
    """Landmark mapping to x=-50 screen must be clamped to 0."""
    mouse._prev_sx = 10.0
    mouse._prev_sy = 540.0
    # Landmark at extreme left (outside crop zone)
    mouse.move(0.00, 0.50, frame_w=1280, frame_h=720)
    assert _pag_mock.moveTo.called
    x = _pag_mock.moveTo.call_args[0][0]
    assert x >= 0, f"x={x} must not be negative"


def test_boundary_clamp_prevents_overflow(mouse):
    """Landmark at extreme right must not produce x > screen_w."""
    mouse._prev_sx = 1910.0
    mouse._prev_sy = 540.0
    mouse.move(1.00, 0.50, frame_w=1280, frame_h=720)
    assert _pag_mock.moveTo.called
    x = _pag_mock.moveTo.call_args[0][0]
    assert x <= 1920, f"x={x} must not exceed screen_w=1920"


# ── Mode sensitivity ──────────────────────────────────────────────────────────

def test_mode_switch_changes_sensitivity(mouse):
    """Presentation mode should produce larger movement than precision mode."""
    mouse._prev_sx = 960.0
    mouse._prev_sy = 540.0
    mouse.set_mode("precision")
    mouse.move(0.55, 0.50, frame_w=1280, frame_h=720)
    x_precision = _pag_mock.moveTo.call_args[0][0]

    _pag_mock.reset_mock()
    mouse._prev_sx = 960.0
    mouse._prev_sy = 540.0
    mouse.set_mode("presentation")
    mouse.move(0.55, 0.50, frame_w=1280, frame_h=720)
    x_presentation = _pag_mock.moveTo.call_args[0][0]

    assert x_presentation >= x_precision, \
        f"Presentation ({x_presentation}) should move further than precision ({x_precision})"


# ── Click methods ─────────────────────────────────────────────────────────────

def test_left_click_calls_pyautogui(mouse):
    mouse.left_click()
    _pag_mock.click.assert_called_once()


def test_right_click_calls_pyautogui(mouse):
    mouse.right_click()
    _pag_mock.rightClick.assert_called_once()


def test_double_click_calls_pyautogui(mouse):
    mouse.double_click()
    _pag_mock.doubleClick.assert_called_once()


# ── Freeze ────────────────────────────────────────────────────────────────────

def test_freeze_stops_movement(mouse):
    """When frozen, move() must not call moveTo."""
    mouse.freeze()
    mouse.move(0.60, 0.50)
    _pag_mock.moveTo.assert_not_called()


def test_unfreeze_restores_movement(mouse):
    """After unfreeze(), move() calls moveTo again."""
    mouse.freeze()
    mouse.unfreeze()
    mouse.move(0.60, 0.50)
    _pag_mock.moveTo.assert_called()
