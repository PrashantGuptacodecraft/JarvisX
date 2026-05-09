"""
core/gesture_guard.py
Per-gesture cooldown and hold-duration enforcement.
Prevents rapid-fire misfires and enforces minimum dwell times.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

log = logging.getLogger(__name__)

# ── Cooldown table (milliseconds) ─────────────────────────────────────────────
COOLDOWNS: dict[str, float] = {
    "left_click":    350.0,
    "right_click":   500.0,
    "double_click":  600.0,
    "screenshot":   2000.0,
    "scroll_up":      60.0,
    "scroll_down":    60.0,
    "swipe_left":    900.0,
    "swipe_right":   900.0,
    "swipe_up":      700.0,
    "swipe_down":    700.0,
    "thumbs_up":     250.0,
    "thumbs_down":   250.0,
    "ok_sign":       400.0,
    "rock_sign":    1000.0,
    "fist":          300.0,
    "freeze_cursor": 100.0,
    "cursor_move":    16.0,
    "drawing_mode":  500.0,
    "peace_sign":    600.0,
    "none":            0.0,
}

# ── Minimum hold duration before gesture fires (milliseconds) ─────────────────
HOLD_DURATIONS: dict[str, float] = {
    "left_click":    80.0,
    "right_click":  100.0,
    "fist":         200.0,
    "freeze_cursor":400.0,
    "drawing_mode": 450.0,
    "rock_sign":    300.0,
}


class GestureGuard:
    """
    Enforces per-gesture cooldowns and minimum hold durations.

    Usage
    -----
    guard = GestureGuard()
    guard.start_hold("left_click")           # called when gesture first appears
    if guard.check_hold_complete("left_click"):   # called every frame
        if guard.can_fire("left_click"):
            guard.record_fired("left_click")
            ... perform action ...
    """

    def __init__(self) -> None:
        # Timestamps of last fire for each gesture
        self._last_fired:  dict[str, float] = {}
        # Timestamps when hold started for each gesture
        self._hold_start:  dict[str, Optional[float]] = {}
        # Track whether hold was already completed (prevent re-triggering)
        self._hold_done:   dict[str, bool] = {}

    # ── Primary API ───────────────────────────────────────────────────────────

    def can_fire(self, gesture_name: str) -> bool:
        """
        Return True if the cooldown for this gesture has expired.
        Does NOT record a fire — call record_fired() separately.
        """
        gesture_name = gesture_name.lower()
        cooldown_ms  = COOLDOWNS.get(gesture_name, 300.0)
        last         = self._last_fired.get(gesture_name, 0.0)
        elapsed_ms   = (time.perf_counter() - last) * 1000.0
        return elapsed_ms >= cooldown_ms

    def start_hold(self, gesture_name: str) -> None:
        """
        Start the hold timer for a gesture.
        Call this on the FIRST frame the gesture appears.
        """
        gesture_name = gesture_name.lower()
        if gesture_name not in self._hold_start or self._hold_start[gesture_name] is None:
            self._hold_start[gesture_name] = time.perf_counter()
            self._hold_done[gesture_name]  = False
            log.debug("Hold started: %s", gesture_name)

    def check_hold_complete(self, gesture_name: str) -> bool:
        """
        Return True if the gesture has been held long enough (HOLD_DURATIONS).
        If no hold duration is required, returns True immediately.
        Once True, stays True until reset_hold() is called.
        """
        gesture_name = gesture_name.lower()

        # If already completed, stay done
        if self._hold_done.get(gesture_name, False):
            return True

        required_ms = HOLD_DURATIONS.get(gesture_name, 0.0)
        if required_ms <= 0.0:
            return True

        start = self._hold_start.get(gesture_name)
        if start is None:
            return False

        elapsed_ms = (time.perf_counter() - start) * 1000.0
        if elapsed_ms >= required_ms:
            self._hold_done[gesture_name] = True
            log.debug("Hold complete: %s (held %.0fms)", gesture_name, elapsed_ms)
            return True
        return False

    def record_fired(self, gesture_name: str) -> None:
        """Record that this gesture just fired. Starts its cooldown."""
        gesture_name = gesture_name.lower()
        self._last_fired[gesture_name] = time.perf_counter()
        log.debug("Fired: %s", gesture_name)

    def reset_hold(self, gesture_name: str) -> None:
        """
        Clear the hold timer for a gesture.
        Call when the gesture is no longer detected.
        """
        gesture_name = gesture_name.lower()
        self._hold_start[gesture_name] = None
        self._hold_done[gesture_name]  = False

    def get_time_since_last(self, gesture_name: str) -> float:
        """Return milliseconds since this gesture last fired. Returns ∞ if never."""
        last = self._last_fired.get(gesture_name.lower(), None)
        if last is None:
            return float("inf")
        return (time.perf_counter() - last) * 1000.0

    def reset_all(self) -> None:
        """Clear all timers and hold states."""
        self._last_fired.clear()
        self._hold_start.clear()
        self._hold_done.clear()
        log.info("GestureGuard: all timers reset")

    def get_status_dict(self) -> dict[str, dict]:
        """
        Return a dict of gesture → cooldown status for HUD display.
        Each entry has:
          'remaining_ms'  : float  (0 if ready to fire)
          'ready'         : bool
          'last_fired_ms' : float  (ms ago, or inf)
        """
        now = time.perf_counter()
        status = {}
        for gesture, cooldown_ms in COOLDOWNS.items():
            last = self._last_fired.get(gesture, 0.0)
            elapsed_ms = (now - last) * 1000.0
            remaining  = max(0.0, cooldown_ms - elapsed_ms)
            status[gesture] = {
                "remaining_ms":  round(remaining, 1),
                "ready":         remaining <= 0.0,
                "last_fired_ms": round(elapsed_ms, 1),
            }
        return status
