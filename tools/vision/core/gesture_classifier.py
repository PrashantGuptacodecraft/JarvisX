"""
core/gesture_classifier.py
Maps FingerState + landmark data → gesture name + confidence score.
Handles all gestures including swipe detection using 4-frame velocity.
"""
from __future__ import annotations
import math
from collections import deque
from dataclasses import dataclass
from typing import Optional

from tools.vision.core.finger_analyzer import FingerState, FingerAnalyzer

# ── Gesture constants ─────────────────────────────────────────────────────────
G_CURSOR        = "CURSOR_MOVE"
G_CLICK         = "LEFT_CLICK"
G_RCLICK        = "RIGHT_CLICK"
G_DCLICK        = "DOUBLE_CLICK"
G_SCROLL_U      = "SCROLL_UP"
G_SCROLL_D      = "SCROLL_DOWN"
G_VOL_UP        = "VOLUME_UP"
G_VOL_DN        = "VOLUME_DOWN"
G_SWIPE_L       = "SWIPE_LEFT"
G_SWIPE_R       = "SWIPE_RIGHT"
G_SWIPE_U       = "SWIPE_UP"
G_SWIPE_D       = "SWIPE_DOWN"
G_WAKE          = "WAKE_JARVIS"
G_SHOT          = "SCREENSHOT"
G_PRECISION     = "TOGGLE_MODE"
G_ZOOM          = "PINCH_ZOOM"
G_NONE          = "NONE"

PINCH_THRESH    = 0.07   # normalized: thumb+index click
SWIPE_VEL       = 0.13   # normalized velocity threshold for swipe
SWIPE_AXIS_RATIO = 0.40  # non-dominant axis must be < 40% of dominant


@dataclass
class GestureResult:
    name: str
    confidence: float        # 0–1
    hand: str = "right"      # "right" | "left"
    swipe_dx: float = 0.0
    swipe_dy: float = 0.0


class GestureClassifier:
    """Classifies hand pose into a gesture with confidence score."""

    def __init__(self) -> None:
        self._analyzer = FingerAnalyzer()
        # 4-frame position history for swipe velocity
        self._pos_history: deque[tuple[float, float]] = deque(maxlen=5)
        self._swipe_dir_history: deque[str] = deque(maxlen=4)

    def classify(self, landmarks, handedness: str = "right") -> GestureResult:
        """Classify gesture from landmarks. Returns GestureResult."""
        fs = self._analyzer.analyze(landmarks)
        lm = landmarks

        # Update swipe position history (index fingertip)
        self._pos_history.append((lm[8].x, lm[8].y))

        # ── Priority order: specific → general ───────────────────────────────

        # Rock sign = toggle mode
        if fs.index and fs.pinky and not fs.middle and not fs.ring:
            return GestureResult(G_PRECISION, 0.9 * fs.confidence, handedness)

        # Open palm = scroll up (left hand) / wake (right)
        if fs.count >= 4:
            if handedness == "left":
                return GestureResult(G_SCROLL_U, 0.85, handedness)
            wrist_y = lm[0].y
            if wrist_y < 0.4:
                return GestureResult(G_WAKE, 0.88, handedness)
            return GestureResult(G_SCROLL_U, 0.82, handedness)

        # Fist
        if fs.count == 0:
            g = G_SCROLL_D if handedness == "left" else G_SCROLL_D
            return GestureResult(g, 0.85, handedness)

        # Volume (left hand only)
        if handedness == "left":
            if fs.thumb and not fs.index and not fs.middle and not fs.ring and not fs.pinky:
                thumb_up = lm[4].y < lm[0].y - 0.10
                thumb_dn = lm[4].y > lm[0].y + 0.05
                if thumb_up:
                    return GestureResult(G_VOL_UP, 0.90, handedness)
                if thumb_dn:
                    return GestureResult(G_VOL_DN, 0.88, handedness)

        # Screenshot = rock sign (index + pinky, already caught above for mode)
        # Reached only if index & pinky without mode intent
        if fs.index and fs.pinky and not fs.middle and not fs.ring and not fs.thumb:
            return GestureResult(G_SHOT, 0.87, handedness)

        # Pinch click — any hand
        pinch = self._analyzer.pinch_distance(lm, 4, 8)
        if pinch < PINCH_THRESH and not fs.middle and not fs.ring and not fs.pinky:
            return GestureResult(G_CLICK, min(1.0, (PINCH_THRESH - pinch) / PINCH_THRESH + 0.5), handedness)

        # Thumb side tap = click
        if fs.thumb and not fs.index and not fs.middle and not fs.ring and not fs.pinky:
            return GestureResult(G_CLICK, 0.78, handedness)

        # Right click = index + middle
        if fs.index and fs.middle and not fs.ring and not fs.pinky:
            return GestureResult(G_RCLICK, 0.85, handedness)

        # Curl click = index curled (tip below DIP)
        index_curled = lm[8].y > lm[7].y + 0.02
        if index_curled and not fs.middle and not fs.ring and not fs.pinky:
            return GestureResult(G_CLICK, 0.80, handedness)

        # Cursor = only index extended
        if fs.index and not fs.middle and not fs.ring and not fs.pinky:
            swipe = self._check_swipe()
            if swipe:
                return GestureResult(swipe, 0.83, handedness)
            return GestureResult(G_CURSOR, fs.confidence, handedness)

        return GestureResult(G_NONE, fs.confidence, handedness)

    def _check_swipe(self) -> Optional[str]:
        """Detect swipe from 4-frame velocity history."""
        if len(self._pos_history) < 5:
            return None
        x0, y0 = self._pos_history[0]
        x1, y1 = self._pos_history[-1]
        dx, dy = x1 - x0, y1 - y0
        vel = math.hypot(dx, dy)
        if vel < SWIPE_VEL:
            return None
        # Axis dominance check
        if abs(dx) > abs(dy):
            if abs(dy) / abs(dx) > SWIPE_AXIS_RATIO:
                return None
            direction = G_SWIPE_R if dx > 0 else G_SWIPE_L
        else:
            if abs(dx) / abs(dy) > SWIPE_AXIS_RATIO:
                return None
            direction = G_SWIPE_D if dy > 0 else G_SWIPE_U
        # Check directional consistency across last 4 frames
        self._swipe_dir_history.append(direction)
        if len(self._swipe_dir_history) >= 4 and len(set(list(self._swipe_dir_history)[-4:])) == 1:
            self._pos_history.clear()
            return direction
        return None
