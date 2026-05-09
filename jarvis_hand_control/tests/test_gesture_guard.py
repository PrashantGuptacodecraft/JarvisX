"""
tests/test_gesture_guard.py
Full unit tests for core/gesture_guard.py using unittest.mock for time.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from core.gesture_guard import GestureGuard, COOLDOWNS, HOLD_DURATIONS


@pytest.fixture
def guard() -> GestureGuard:
    return GestureGuard()


# ── Cooldown tests ────────────────────────────────────────────────────────────

def test_cooldown_prevents_immediate_refire(guard):
    """can_fire → True; record_fired; can_fire → False immediately."""
    assert guard.can_fire("left_click") is True, "Should be fireable on first call"
    guard.record_fired("left_click")
    assert guard.can_fire("left_click") is False, \
        "Should be blocked immediately after firing"


def test_cooldown_allows_after_expiry(guard):
    """After cooldown expires (mocked time), can_fire → True."""
    cd_ms = COOLDOWNS["left_click"]   # 350ms
    t0    = 1000.0

    with patch("core.gesture_guard.time.perf_counter", return_value=t0):
        guard.record_fired("left_click")

    # Advance time beyond cooldown
    t1 = t0 + (cd_ms + 10) / 1000.0
    with patch("core.gesture_guard.time.perf_counter", return_value=t1):
        assert guard.can_fire("left_click") is True, \
            f"Should fire after {cd_ms}ms cooldown"


def test_cooldown_blocked_just_before_expiry(guard):
    """Just before cooldown expires, can_fire should still return False."""
    cd_ms = COOLDOWNS["left_click"]
    t0    = 1000.0

    with patch("core.gesture_guard.time.perf_counter", return_value=t0):
        guard.record_fired("left_click")

    # Advance to 10ms before expiry
    t_almost = t0 + (cd_ms - 10) / 1000.0
    with patch("core.gesture_guard.time.perf_counter", return_value=t_almost):
        assert guard.can_fire("left_click") is False, \
            "Should still be blocked 10ms before cooldown expires"


def test_different_gestures_independent_cooldowns(guard):
    """Firing left_click should not block right_click."""
    guard.record_fired("left_click")
    assert guard.can_fire("right_click") is True, \
        "right_click timer must be independent from left_click"


def test_unknown_gesture_uses_default_cooldown(guard):
    """Unknown gesture falls back to 300ms default (or value in COOLDOWNS)."""
    assert guard.can_fire("totally_fake_gesture") is True


# ── Hold duration tests ───────────────────────────────────────────────────────

def test_hold_duration_not_met_returns_false(guard):
    """200ms hold, but drawing_mode requires 450ms → not complete."""
    t0 = 2000.0
    with patch("core.gesture_guard.time.perf_counter", return_value=t0):
        guard.start_hold("drawing_mode")

    t1 = t0 + 0.200   # 200ms elapsed
    with patch("core.gesture_guard.time.perf_counter", return_value=t1):
        result = guard.check_hold_complete("drawing_mode")
    assert result is False, "200ms is not enough for drawing_mode (needs 450ms)"


def test_hold_duration_met_returns_true(guard):
    """500ms hold exceeds 450ms requirement → complete."""
    t0 = 2000.0
    with patch("core.gesture_guard.time.perf_counter", return_value=t0):
        guard.start_hold("drawing_mode")

    t1 = t0 + 0.500   # 500ms elapsed
    with patch("core.gesture_guard.time.perf_counter", return_value=t1):
        result = guard.check_hold_complete("drawing_mode")
    assert result is True, "500ms should satisfy 450ms drawing_mode hold"


def test_hold_duration_no_requirement_immediate(guard):
    """Gestures without a HOLD_DURATIONS entry fire immediately."""
    guard.start_hold("scroll_up")
    assert guard.check_hold_complete("scroll_up") is True, \
        "scroll_up has no hold duration — should return True immediately"


def test_hold_stays_true_after_met(guard):
    """Once hold is complete it must remain True without re-checking time."""
    t0 = 3000.0
    with patch("core.gesture_guard.time.perf_counter", return_value=t0):
        guard.start_hold("fist")

    with patch("core.gesture_guard.time.perf_counter", return_value=t0 + 0.3):
        assert guard.check_hold_complete("fist") is True

    # Don't patch time — should still be True (cached)
    assert guard.check_hold_complete("fist") is True


# ── Reset tests ───────────────────────────────────────────────────────────────

def test_reset_all_clears_timers(guard):
    """After reset_all(), all gestures must be fireable again."""
    gestures = ["left_click", "right_click", "scroll_up", "swipe_left"]
    for g in gestures:
        guard.record_fired(g)
    guard.reset_all()
    for g in gestures:
        assert guard.can_fire(g) is True, \
            f"{g} should be fireable after reset_all()"


# ── Status dict tests ─────────────────────────────────────────────────────────

def test_get_status_dict_structure(guard):
    """Status dict must have correct shape for every tracked gesture."""
    guard.record_fired("left_click")
    status = guard.get_status_dict()

    assert isinstance(status, dict), "get_status_dict must return dict"
    assert "left_click" in status, "left_click must be in status dict"

    entry = status["left_click"]
    assert "remaining_ms"  in entry, "Entry must have remaining_ms"
    assert "ready"         in entry, "Entry must have ready bool"
    assert "last_fired_ms" in entry, "Entry must have last_fired_ms"
    assert isinstance(entry["ready"], bool)
    assert entry["remaining_ms"] >= 0
    assert entry["remaining_ms"] <= COOLDOWNS.get("left_click", 1000)


def test_get_time_since_last_never_fired(guard):
    """get_time_since_last for an unfired gesture should return infinity."""
    assert guard.get_time_since_last("peace_sign") == float("inf")
