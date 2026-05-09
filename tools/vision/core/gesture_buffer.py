"""
core/gesture_buffer.py
Dual-layer smoothing: majority-vote confirmation + EMA cursor smoothing.
"""
from __future__ import annotations
import math
from collections import deque
from dataclasses import dataclass
from typing import Optional

from tools.vision.core.gesture_classifier import GestureResult, G_NONE, G_CURSOR


# ── Config ────────────────────────────────────────────────────────────────────
VOTE_WINDOW     = 7      # frames in voting window
VOTE_THRESHOLD  = 5      # gesture must appear in ≥5 of 7 frames to confirm
EMA_ALPHA       = 0.35   # cursor exponential moving average
DEAD_ZONE_PX    = 10     # pixels: ignore if cursor moves less than this


@dataclass
class SmoothedState:
    gesture: Optional[str]    # confirmed gesture name or None
    confidence: float
    cursor_x: int
    cursor_y: int
    cursor_moved: bool        # False if within dead zone
    hand: str = "right"


class GestureBuffer:
    """
    Confirms gestures using majority vote over last VOTE_WINDOW frames.
    Only emits a gesture if it appears in ≥ VOTE_THRESHOLD frames.
    """

    def __init__(self) -> None:
        self._window: deque[GestureResult] = deque(maxlen=VOTE_WINDOW)
        self._last_confirmed: Optional[str] = None

    def update(self, result: GestureResult) -> Optional[GestureResult]:
        """
        Add result to window. Return confirmed GestureResult or None.
        For cursor/none gestures, always pass through (no vote needed).
        """
        self._window.append(result)
        name = result.name

        if name in (G_NONE, G_CURSOR):
            self._last_confirmed = name
            return result  # pass-through: cursor needs every frame

        if len(self._window) < VOTE_WINDOW:
            return None

        votes = sum(1 for r in self._window if r.name == name)
        if votes >= VOTE_THRESHOLD:
            if name != self._last_confirmed:
                self._last_confirmed = name
                avg_conf = sum(r.confidence for r in self._window if r.name == name) / votes
                return GestureResult(name, avg_conf, result.hand)
        return None

    def reset(self) -> None:
        self._window.clear()
        self._last_confirmed = None


class CursorSmoother:
    """
    EMA smoothing for cursor with dead zone, jump cap, and initialization guard.
    """

    def __init__(self, screen_w: int, screen_h: int,
                 alpha: float = EMA_ALPHA, dead_zone: float = DEAD_ZONE_PX) -> None:
        self._sw, self._sh = screen_w, screen_h
        self._alpha = alpha
        self._dead_zone = dead_zone
        self._sx: float = screen_w / 2
        self._sy: float = screen_h / 2
        self._initialized = False

    def smooth(self, raw_x: float, raw_y: float) -> tuple[int, int, bool]:
        """
        Apply EMA to (raw_x, raw_y) in screen coords.
        Returns (x, y, moved) — moved=False if within dead zone.
        """
        if not self._initialized:
            self._sx, self._sy = raw_x, raw_y
            self._initialized = True
            return int(raw_x), int(raw_y), True

        nx = self._sx * (1 - self._alpha) + raw_x * self._alpha
        ny = self._sy * (1 - self._alpha) + raw_y * self._alpha

        moved = math.hypot(nx - self._sx, ny - self._sy) >= self._dead_zone
        if moved:
            self._sx, self._sy = nx, ny

        x = max(0, min(int(self._sx), self._sw - 1))
        y = max(0, min(int(self._sy), self._sh - 1))
        return x, y, moved

    def get_pos(self) -> tuple[int, int]:
        return int(self._sx), int(self._sy)

    def set_alpha(self, alpha: float) -> None:
        self._alpha = max(0.05, min(0.95, alpha))

    def set_dead_zone(self, px: float) -> None:
        self._dead_zone = max(1.0, px)
