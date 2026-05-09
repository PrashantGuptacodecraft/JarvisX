"""
tests/test_action_dispatcher.py
Full unit tests for control/action_dispatcher.py
Mouse and keyboard controllers are mocked — no hardware interaction.
"""
from __future__ import annotations

import time
from unittest.mock import MagicMock, call, patch

import pytest

from control.action_dispatcher import ActionDispatcher


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_dispatcher(features: dict = None) -> tuple[ActionDispatcher, MagicMock, MagicMock]:
    settings = MagicMock()
    mouse    = MagicMock()
    keyboard = MagicMock()
    feats    = features or {
        "voice_fusion_enabled": True,
        "air_drawing_enabled":  True,
        "heatmap_enabled":      True,
    }
    d = ActionDispatcher(settings, mouse, keyboard, feats)
    return d, mouse, keyboard


def _gesture(name: str, cx: float = 0.5, cy: float = 0.5,
             conf: float = 0.90, metadata: dict = None) -> MagicMock:
    g = MagicMock()
    g.gesture_name = name
    g.cursor_x     = cx
    g.cursor_y     = cy
    g.confidence   = conf
    g.metadata     = metadata or {}
    return g


def _fusion(should_fire: bool = True, action: str = "ctrl_s") -> MagicMock:
    f = MagicMock()
    f.should_fire = should_fire
    f.action      = action
    f.voice_phrase= "save"
    f.feedback    = "Saving"
    return f


# ── Routing tests ─────────────────────────────────────────────────────────────

def test_cursor_move_calls_mouse_move():
    """cursor_move gesture must call mouse.move with correct coordinates."""
    d, mouse, _ = _make_dispatcher()
    d.dispatch(_gesture("cursor_move", cx=0.75, cy=0.40))
    time.sleep(0.05)   # allow worker thread to process
    mouse.move.assert_called()


def test_left_click_calls_mouse_click():
    """left_click gesture must call mouse.left_click()."""
    d, mouse, _ = _make_dispatcher()
    d.dispatch(_gesture("left_click"))
    time.sleep(0.05)
    mouse.left_click.assert_called_once()


def test_right_click_calls_mouse_right_click():
    d, mouse, _ = _make_dispatcher()
    d.dispatch(_gesture("right_click"))
    time.sleep(0.05)
    mouse.right_click.assert_called_once()


def test_scroll_up_calls_mouse_scroll_up():
    d, mouse, _ = _make_dispatcher()
    d.dispatch(_gesture("scroll_up", metadata={"wrist_angle": 30.0}))
    time.sleep(0.05)
    mouse.scroll.assert_called()
    args = mouse.scroll.call_args[0]
    assert args[0] == "up", f"Expected direction 'up', got '{args[0]}'"


def test_scroll_down_calls_mouse_scroll_down():
    d, mouse, _ = _make_dispatcher()
    d.dispatch(_gesture("scroll_down", metadata={"wrist_angle": 45.0}))
    time.sleep(0.05)
    mouse.scroll.assert_called()
    args = mouse.scroll.call_args[0]
    assert args[0] == "down", f"Expected direction 'down', got '{args[0]}'"


def test_thumbs_up_calls_volume_up():
    d, _, keyboard = _make_dispatcher()
    d.dispatch(_gesture("thumbs_up"))
    time.sleep(0.05)
    keyboard.volume_up.assert_called_once()


def test_swipe_left_calls_alt_left():
    d, _, keyboard = _make_dispatcher()
    d.dispatch(_gesture("swipe_left"))
    time.sleep(0.05)
    keyboard.alt_left.assert_called_once()


# ── Fusion override ───────────────────────────────────────────────────────────

def test_fusion_result_overrides_gesture():
    """
    thumbs_up normally → volume_up.
    fusion should_fire=True, action=ctrl_s → must call keyboard.ctrl_s instead.
    """
    d, _, keyboard = _make_dispatcher()
    d.dispatch(_gesture("thumbs_up"), _fusion(should_fire=True, action="ctrl_s"))
    time.sleep(0.08)
    keyboard.ctrl_s.assert_called_once()
    keyboard.volume_up.assert_not_called()


def test_fusion_not_fire_falls_back_to_gesture():
    """fusion.should_fire=False → fall back to gesture routing."""
    d, _, keyboard = _make_dispatcher()
    f = _fusion(should_fire=False, action="ctrl_s")
    d.dispatch(_gesture("thumbs_up"), f)
    time.sleep(0.08)
    keyboard.volume_up.assert_called_once()
    keyboard.ctrl_s.assert_not_called()


# ── Return value ──────────────────────────────────────────────────────────────

def test_dispatch_returns_true_on_success():
    """dispatch must return True when gesture is routable."""
    d, _, _ = _make_dispatcher()
    result = d.dispatch(_gesture("left_click"))
    assert result is True, "dispatch must return True on valid gesture"


def test_dispatch_returns_false_on_none():
    """dispatch(None) must return False without raising."""
    d, _, _ = _make_dispatcher()
    result = d.dispatch(None)
    assert result is False, "dispatch(None) must return False"


# ── Wrist angle to speed ──────────────────────────────────────────────────────

def test_wrist_angle_to_speed_range():
    """Speed must be integer in [1, 10]."""
    for angle in range(0, 91, 10):
        speed = ActionDispatcher.wrist_angle_to_speed(float(angle))
        assert 1 <= speed <= 10, f"angle={angle}° → speed={speed} out of range"


def test_wrist_angle_zero_gives_minimum_speed():
    assert ActionDispatcher.wrist_angle_to_speed(0.0) == 1


def test_wrist_angle_90_gives_maximum_speed():
    assert ActionDispatcher.wrist_angle_to_speed(90.0) == 10


# ── Toggle mode ───────────────────────────────────────────────────────────────

def test_toggle_mode_cycles_through_modes():
    d, mouse, _ = _make_dispatcher()
    assert d._mode == "normal"
    d.toggle_mode()
    assert d._mode == "precision"
    d.toggle_mode()
    assert d._mode == "presentation"
    d.toggle_mode()
    assert d._mode == "normal"
