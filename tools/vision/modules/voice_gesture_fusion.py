"""
tools/vision/modules/voice_gesture_fusion.py
Voice + Gesture Fusion Module.

Listens for queued voice tokens from JARVIS and combines them with
the current gesture to produce fused high-confidence commands.

Examples:
  Voice: "open"  + Gesture: LEFT_CLICK     → "open_click"  (click to open)
  Voice: "draw"  + Gesture: CURSOR_MOVE    → activates air drawing
  Voice: "close" + any gesture             → sends Alt+F4

update() returns Optional[str] fused_command — the ModuleManager passes
this back to the engine's action_callback.
"""
from __future__ import annotations
import logging
import time
from collections import deque
from typing import Optional

log = logging.getLogger("voice_gesture_fusion")

# ── Fusion rules: (voice_token, gesture) → fused_action ─────────────────────
# Voice tokens are lowercase keywords extracted from JARVIS speech.
_FUSION_RULES: dict[tuple[str, str], str] = {
    ("click",  "CURSOR_MOVE"):    "LEFT_CLICK",
    ("open",   "LEFT_CLICK"):     "open_selected",
    ("close",  "LEFT_CLICK"):     "close_window",
    ("close",  "NONE"):           "close_window",
    ("scroll",  "SCROLL_UP"):     "scroll_up_fast",
    ("scroll",  "SCROLL_DOWN"):   "scroll_down_fast",
    ("draw",   "CURSOR_MOVE"):    "start_drawing",
    ("stop",   "CURSOR_MOVE"):    "stop_drawing",
    ("save",   "SCREENSHOT"):     "save_screenshot",
    ("volume", "VOLUME_UP"):      "volume_up_x3",
    ("volume", "VOLUME_DOWN"):    "volume_down_x3",
    ("select", "CURSOR_MOVE"):    "left_click_select",
    ("right",  "LEFT_CLICK"):     "RIGHT_CLICK",
    ("double", "LEFT_CLICK"):     "DOUBLE_CLICK",
    ("undo",   "NONE"):           "ctrl_z",
    ("copy",   "LEFT_CLICK"):     "ctrl_c",
    ("paste",  "NONE"):           "ctrl_v",
    ("zoom",   "SCROLL_UP"):      "ctrl_scroll_up",
    ("zoom",   "SCROLL_DOWN"):    "ctrl_scroll_down",
}

# How long a voice token stays "active" after being spoken (seconds)
TOKEN_TTL = 3.0


class VoiceGestureFusion:
    """
    Fuses pending voice tokens with detected gesture to produce commands.
    update() returns fused_action string or None.
    """

    def __init__(self, token_queue=None) -> None:
        """
        token_queue: Optional[queue.Queue] — JARVIS pushes voice tokens here.
        If None, tokens can be injected via push_token().
        """
        self._queue = token_queue
        self._active_tokens: deque[tuple[str, float]] = deque(maxlen=5)
        self._last_fused: Optional[str] = None
        self._last_fused_time = 0.0
        self._fuse_cooldown   = 0.8  # seconds between same fused action
        log.info("VoiceGestureFusion module initialized")

    def push_token(self, token: str) -> None:
        """Push a voice keyword token (called by JARVIS speech handler)."""
        token = token.strip().lower()
        if token:
            self._active_tokens.append((token, time.time()))
            log.info("VGF token received: '%s'", token)

    def update(self, frame, hand_data: dict, gesture_result: dict) -> Optional[str]:
        """
        Try to fuse pending voice tokens with current gesture.
        Returns fused action string or None.
        """
        # Drain external queue if provided
        if self._queue is not None:
            while True:
                try:
                    tok = self._queue.get_nowait()
                    self._active_tokens.append((tok.lower(), time.time()))
                except Exception:
                    break

        gesture = gesture_result.get("name", "NONE")
        now     = time.time()

        # Expire old tokens
        self._active_tokens = deque(
            ((t, ts) for t, ts in self._active_tokens if now - ts < TOKEN_TTL),
            maxlen=5
        )

        # Try each active token against current gesture
        for token, _ in self._active_tokens:
            key = (token, gesture)
            if key in _FUSION_RULES:
                action = _FUSION_RULES[key]
                if (action != self._last_fused or
                        now - self._last_fused_time > self._fuse_cooldown):
                    self._last_fused      = action
                    self._last_fused_time = now
                    log.info("VGF fused: voice='%s' + gesture='%s' → '%s'",
                             token, gesture, action)
                    self._active_tokens.clear()  # consume token
                    self._draw_hud(frame, token, gesture, action)
                    return action

        self._draw_standby(frame, bool(self._active_tokens))
        return None

    # ── HUD helpers ───────────────────────────────────────────────────────────

    def _draw_hud(self, frame, token: str, gesture: str, action: str) -> None:
        import cv2
        h, w = frame.shape[:2]
        label = f"FUSED: [{token}] + [{gesture}] → {action}"
        cv2.putText(frame, label, (10, h - 15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 200), 1, cv2.LINE_AA)

    def _draw_standby(self, frame, has_token: bool) -> None:
        import cv2
        if not has_token:
            return
        h, w = frame.shape[:2]
        # Blink indicator showing token is armed
        t = time.time()
        if int(t * 3) % 2 == 0:
            cv2.putText(frame, "VGF ARMED", (10, h - 15),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 200, 255), 1, cv2.LINE_AA)
