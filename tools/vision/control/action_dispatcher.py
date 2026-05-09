"""
control/action_dispatcher.py
Routes confirmed gestures to OS actions.
Includes GestureGuard cooldowns, multi-hand roles, pinch-zoom, structured logging.
"""
from __future__ import annotations
import logging
import time
import math
from collections import deque
from typing import Optional, Callable

from tools.vision.core.gesture_classifier import (
    GestureResult,
    G_CURSOR, G_CLICK, G_RCLICK, G_DCLICK, G_SCROLL_U, G_SCROLL_D,
    G_VOL_UP, G_VOL_DN, G_SWIPE_L, G_SWIPE_R, G_SWIPE_U, G_SWIPE_D,
    G_WAKE, G_SHOT, G_PRECISION, G_ZOOM, G_NONE,
)

log = logging.getLogger("action_dispatcher")


# ── Per-gesture cooldowns (seconds) ──────────────────────────────────────────
COOLDOWNS: dict[str, float] = {
    G_CLICK:    0.350,
    G_RCLICK:   0.500,
    G_DCLICK:   0.600,
    G_SHOT:     2.000,
    G_SCROLL_U: 0.060,
    G_SCROLL_D: 0.060,
    G_SWIPE_L:  0.900,
    G_SWIPE_R:  0.900,
    G_SWIPE_U:  0.900,
    G_SWIPE_D:  0.900,
    G_VOL_UP:   0.250,
    G_VOL_DN:   0.250,
    G_WAKE:     1.500,
    G_PRECISION:0.700,
    G_ZOOM:     0.100,
}

# Minimum hold duration (seconds) before gesture fires
HOLD_REQUIRED: dict[str, float] = {
    G_CLICK:    0.080,
    G_RCLICK:   0.100,
    G_DCLICK:   0.080,
    G_SWIPE_L:  0.120,
    G_SWIPE_R:  0.120,
    G_SWIPE_U:  0.120,
    G_SWIPE_D:  0.120,
    G_WAKE:     0.200,
    G_PRECISION:0.400,
}


class GestureGuard:
    """Enforces per-gesture cooldowns and minimum hold durations."""

    def __init__(self) -> None:
        self._last_fire: dict[str, float] = {}
        self._gesture_start: dict[str, float] = {}

    def can_fire(self, name: str) -> bool:
        now = time.time()
        # Cooldown check
        last = self._last_fire.get(name, 0.0)
        if now - last < COOLDOWNS.get(name, 0.0):
            return False
        # Hold duration check
        start = self._gesture_start.get(name, now)
        hold_needed = HOLD_REQUIRED.get(name, 0.0)
        if now - start < hold_needed:
            return False
        return True

    def record_start(self, name: str) -> None:
        if name not in self._gesture_start:
            self._gesture_start[name] = time.time()

    def record_fire(self, name: str) -> None:
        self._last_fire[name] = time.time()
        self._gesture_start.pop(name, None)

    def reset_start(self, name: str) -> None:
        self._gesture_start.pop(name, None)


class ActionDispatcher:
    """
    Routes GestureResult objects to OS/JARVIS actions.
    Right hand: cursor + clicks. Left hand: scroll + volume + window.
    """

    def __init__(self, mouse_ctrl, command_queue=None,
                 on_mode_change: Optional[Callable] = None) -> None:
        self._mouse = mouse_ctrl
        self._cq = command_queue
        self._on_mode_change = on_mode_change
        self._guard = GestureGuard()
        self._precision_mode = True
        # Pinch-zoom state (both hands)
        self._zoom_history: deque[float] = deque(maxlen=3)
        # Gesture history for HUD
        self.gesture_history: deque[tuple[str, float]] = deque(maxlen=6)
        self._last_gesture_name: Optional[str] = None

    def dispatch(self, result: GestureResult, cursor_x: int, cursor_y: int,
                 latency_ms: float = 0.0) -> None:
        """Route a confirmed gesture to the appropriate action."""
        name = result.name
        hand = result.hand

        # Track hold start
        self._guard.record_start(name)

        if name in (G_NONE, G_CURSOR):
            if name == G_CURSOR:
                self._mouse.move(cursor_x, cursor_y)
            # Reset hold for previous gesture if gesture changed
            if name != self._last_gesture_name and self._last_gesture_name:
                self._guard.reset_start(self._last_gesture_name)
            self._last_gesture_name = name
            return

        if not self._guard.can_fire(name):
            return

        self._guard.record_fire(name)
        self._last_gesture_name = name
        self.gesture_history.append((name, time.time()))

        # Structured log
        log.info("GESTURE fired=%-16s conf=%.2f hand=%-5s latency=%.1fms action=%s",
                 name, result.confidence, hand, latency_ms, name)

        # ── Right hand actions ────────────────────────────────────────────────
        if hand == "right":
            self._right_hand_action(name, cursor_x, cursor_y)
        # ── Left hand actions ─────────────────────────────────────────────────
        else:
            self._left_hand_action(name)

    def handle_zoom(self, right_lm, left_lm) -> None:
        """Detect pinch-zoom when both hands visible."""
        if right_lm is None or left_lm is None:
            self._zoom_history.clear()
            return
        dist = math.hypot(right_lm[8].x - left_lm[8].x,
                          right_lm[8].y - left_lm[8].y)
        if len(self._zoom_history) > 0:
            delta = dist - self._zoom_history[-1]
            if abs(delta) > 0.015 and self._guard.can_fire(G_ZOOM):
                self._guard.record_fire(G_ZOOM)
                try:
                    import pyautogui
                    scroll_amt = 3 if delta > 0 else -3
                    pyautogui.hotkey("ctrl", "=" if delta > 0 else "-")
                except Exception:
                    pass
        self._zoom_history.append(dist)

    def set_precision_mode(self, on: bool) -> None:
        self._precision_mode = on
        self._mouse.set_precision_mode(on)
        if self._on_mode_change:
            self._on_mode_change("PRECISION" if on else "PRESENTATION")

    # ── Private ───────────────────────────────────────────────────────────────

    def _right_hand_action(self, name: str, cx: int, cy: int) -> None:
        actions = {
            G_CLICK:    self._mouse.left_click,
            G_RCLICK:   self._mouse.right_click,
            G_DCLICK:   self._mouse.double_click,
            G_SHOT:     self._screenshot,
            G_WAKE:     self._wake_jarvis,
            G_PRECISION:self._toggle_mode,
            G_SWIPE_L:  lambda: self._send_command("swipe_left"),
            G_SWIPE_R:  lambda: self._send_command("swipe_right"),
            G_SWIPE_U:  lambda: self._send_command("swipe_up"),
            G_SWIPE_D:  lambda: self._send_command("swipe_down"),
        }
        fn = actions.get(name)
        if fn:
            fn()

    def _left_hand_action(self, name: str) -> None:
        actions = {
            G_SCROLL_U: lambda: self._mouse.scroll(3),
            G_SCROLL_D: lambda: self._mouse.scroll(-3),
            G_VOL_UP:   lambda: self._hotkey("volumeup"),
            G_VOL_DN:   lambda: self._hotkey("volumedown"),
            G_SWIPE_L:  lambda: self._hotkey("alt", "left"),
            G_SWIPE_R:  lambda: self._hotkey("alt", "right"),
            G_SWIPE_U:  lambda: self._hotkey("win", "up"),
            G_SWIPE_D:  lambda: self._hotkey("win", "down"),
        }
        fn = actions.get(name)
        if fn:
            fn()

    def _screenshot(self) -> None:
        try:
            import pyautogui
            pyautogui.hotkey("win", "shift", "s")
        except Exception:
            pass

    def _wake_jarvis(self) -> None:
        if self._cq:
            try:
                self._cq.put_nowait("hello jarvis")
            except Exception:
                pass

    def _toggle_mode(self) -> None:
        self._precision_mode = not self._precision_mode
        self.set_precision_mode(self._precision_mode)

    def _hotkey(self, *keys: str) -> None:
        try:
            import pyautogui
            pyautogui.hotkey(*keys)
        except Exception:
            pass

    def _send_command(self, cmd: str) -> None:
        if self._cq:
            try:
                self._cq.put_nowait(cmd)
            except Exception:
                pass
