"""
control/action_dispatcher.py
Routes classified gestures (and fusion overrides) to mouse/keyboard actions.
Thread-safe via an internal execution queue.
"""
from __future__ import annotations

import logging
import math
import queue
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

log = logging.getLogger(__name__)

_EXEC_LOG_PATH = None   # set in __init__ from settings


@dataclass
class DispatchRecord:
    """One entry written to the execution log."""
    ts:       float
    gesture:  str
    action:   str
    source:   str   # "gesture" | "fusion"
    success:  bool
    latency_ms: float


class ActionDispatcher:
    """
    Routes gesture results (and fusion overrides) to the correct action.
    Maintains an internal queue so dispatch calls never block the vision loop.
    """

    def __init__(self, settings, mouse, keyboard, features: dict) -> None:
        self._mouse    = mouse
        self._kb       = keyboard
        self._features = features
        self._mode:    str  = "normal"
        self._frozen:  bool = False
        self._fist_held: bool = False

        # Execution log path
        try:
            from pathlib import Path
            log_dir = Path(__file__).resolve().parent.parent / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            self._exec_log = log_dir / "action_log.jsonl"
        except Exception:
            self._exec_log = None

        # Thread-safe execution queue
        self._exec_q: queue.Queue[Callable] = queue.Queue(maxsize=32)
        self._worker = threading.Thread(
            target=self._exec_worker, daemon=True, name="action-dispatcher"
        )
        self._worker.start()

        # Build gesture → handler map
        self._map = self._build_map()

    # ── Primary dispatch ──────────────────────────────────────────────────────

    def dispatch(self, gesture_result, fusion_result=None) -> bool:
        """
        Route a gesture (or fusion override) to the appropriate action.
        Returns True if an action was enqueued.
        """
        t0 = time.perf_counter()

        if gesture_result is None:
            return False

        gesture_name = getattr(gesture_result, "gesture_name", "none")
        cursor_x     = getattr(gesture_result, "cursor_x", 0.0)
        cursor_y     = getattr(gesture_result, "cursor_y", 0.0)
        wrist_angle  = gesture_result.metadata.get("wrist_angle", 0.0) \
                       if hasattr(gesture_result, "metadata") else 0.0

        source = "gesture"
        action_name = gesture_name

        # ── Fusion override ────────────────────────────────────────────────
        if fusion_result is not None and getattr(fusion_result, "should_fire", False):
            action_name = fusion_result.action
            source      = "fusion"
            fn = self._fusion_action(action_name)
            if fn is not None:
                self._enqueue(fn, gesture_name, action_name, source, t0)
                return True

        # ── Standard gesture routing ───────────────────────────────────────
        handler = self._map.get(gesture_name)
        if handler is None:
            return False

        # Pass extra context for gestures that need it
        if gesture_name == "cursor_move":
            fn = lambda: self._mouse.move(cursor_x, cursor_y)
        elif gesture_name in ("scroll_up", "scroll_down"):
            spd = self.wrist_angle_to_speed(wrist_angle)
            direction = "up" if gesture_name == "scroll_up" else "down"
            fn = lambda d=direction, s=spd: self._mouse.scroll(d, s)
        elif gesture_name == "fist":
            fn = self._handle_fist
        else:
            fn = handler

        self._enqueue(fn, gesture_name, action_name, source, t0)
        return True

    # ── Fusion action resolution ──────────────────────────────────────────────

    def _fusion_action(self, action: str) -> Optional[Callable]:
        """Map a fusion action string to a callable."""
        fusion_map: dict[str, Callable] = {
            "open_file_under_cursor": self._kb.open_file_under_cursor,
            "close_active_window":    self._kb.close_window,
            "open_browser_search":    self._kb.open_browser_search,
            "ctrl_s":                 self._kb.ctrl_s,
            "increase_window_size":   self._kb.increase_window_size,
            "ctrl_z":                 self._kb.ctrl_z,
            "take_screenshot":        self._kb.take_screenshot,
            "open_ai_chat":           self._kb.open_ai_chat,
            "media_play_pause":       self._kb.media_play_pause,
            "media_stop":             self._kb.media_stop,
            "media_next_track":       self._kb.media_next,
            "volume_up":              self._kb.volume_up,
            "volume_down":            self._kb.volume_down,
            "new_tab":                self._kb.new_tab,
            "browser_back":           self._kb.browser_back,
            "zoom_in":                self._kb.zoom_in,
            "ctrl_c":                 self._kb.ctrl_c,
            "ctrl_v":                 self._kb.ctrl_v,
            "ctrl_a":                 self._kb.ctrl_a,
            "delete_key":             self._kb.delete_key,
        }
        fn = fusion_map.get(action)
        if fn is None:
            log.debug("No fusion handler for action: %s", action)
        return fn

    # ── Gesture → handler map ─────────────────────────────────────────────────

    def _build_map(self) -> dict[str, Callable]:
        return {
            "cursor_move":   lambda: None,   # replaced in dispatch with coords
            "left_click":    self._mouse.left_click,
            "right_click":   self._mouse.right_click,
            "double_click":  self._mouse.double_click,
            "freeze_cursor": self._handle_freeze,
            "scroll_up":     lambda: None,   # replaced in dispatch with speed
            "scroll_down":   lambda: None,
            "swipe_left":    self._kb.alt_left,
            "swipe_right":   self._kb.alt_right,
            "swipe_up":      self._kb.maximize_window,
            "swipe_down":    self._kb.minimize_window,
            "thumbs_up":     self._kb.volume_up,
            "thumbs_down":   self._kb.volume_down,
            "ok_sign":       self._kb.enter_key,
            "peace_sign":    self._kb.take_screenshot,
            "rock_sign":     self.toggle_mode,
            "fist":          lambda: None,   # handled per-frame
            "none":          lambda: None,
            "drawing_mode":  lambda: None,   # handled by AirDrawingEngine
        }

    # ── Wrist angle → scroll speed ────────────────────────────────────────────

    @staticmethod
    def wrist_angle_to_speed(angle: float) -> int:
        """Map wrist tilt 0–90° → scroll amount 1–10."""
        clamped = max(0.0, min(abs(angle), 90.0))
        return max(1, min(10, int(clamped / 9.0)))

    # ── State handlers ────────────────────────────────────────────────────────

    def _handle_freeze(self) -> None:
        if self._frozen:
            self._mouse.unfreeze()
            self._frozen = False
            log.info("Cursor unfrozen")
        else:
            self._mouse.freeze()
            self._frozen = True
            log.info("Cursor frozen")

    def _handle_fist(self) -> None:
        if not self._fist_held:
            self._mouse.click_and_hold()
            self._fist_held = True
        # Release is triggered when fist is no longer detected
        # (handled externally by checking gesture != fist then calling release)

    def release_fist(self) -> None:
        """Call when fist gesture ends to release mouse button."""
        if self._fist_held:
            self._mouse.release()
            self._fist_held = False

    # ── Mode management ───────────────────────────────────────────────────────

    def toggle_mode(self) -> None:
        modes = ["normal", "precision", "presentation"]
        idx   = modes.index(self._mode)
        self._mode = modes[(idx + 1) % len(modes)]
        self._mouse.set_mode(self._mode)
        log.info("Mode toggled → %s", self._mode)

    # ── Execution queue worker ────────────────────────────────────────────────

    def _enqueue(self, fn: Callable, gesture: str, action: str,
                 source: str, t0: float) -> None:
        """Push callable onto exec queue (drop oldest if full)."""
        try:
            self._exec_q.put_nowait(
                (fn, gesture, action, source, t0)
            )
        except queue.Full:
            try: self._exec_q.get_nowait()
            except queue.Empty: pass
            self._exec_q.put_nowait((fn, gesture, action, source, t0))

    def _exec_worker(self) -> None:
        """Background thread: drain execution queue and run actions."""
        while True:
            try:
                item = self._exec_q.get(timeout=1.0)
                fn, gesture, action, source, t0 = item
                success = True
                try:
                    fn()
                except Exception as exc:
                    log.warning("Action error [%s]: %s", action, exc)
                    success = False
                latency = (time.perf_counter() - t0) * 1000.0
                self.log_dispatch(gesture, action, source, success, latency)
            except queue.Empty:
                continue

    # ── Logging ───────────────────────────────────────────────────────────────

    def log_dispatch(self, gesture: str, action: str, source: str,
                     success: bool, latency_ms: float) -> None:
        if self._exec_log is None:
            return
        import json
        entry = {
            "ts":      round(time.time(), 3),
            "gesture": gesture,
            "action":  action,
            "source":  source,
            "ok":      success,
            "ms":      round(latency_ms, 2),
        }
        try:
            with open(self._exec_log, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as exc:
            log.debug("log_dispatch write error: %s", exc)
