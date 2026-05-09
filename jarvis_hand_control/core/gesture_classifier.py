"""
core/gesture_classifier.py
Maps FingerState + landmarks to GestureResult.
Classifies 18 gestures with confidence scores.
Velocity computed from position history deque (10 frames).
"""
from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from core.finger_analyzer import FingerAnalyzer, FingerState, FingerStatus, FINGERTIP_IDS

log = logging.getLogger(__name__)

# ── Gesture name constants ────────────────────────────────────────────────────
G_CURSOR_MOVE   = "cursor_move"
G_LEFT_CLICK    = "left_click"
G_RIGHT_CLICK   = "right_click"
G_DOUBLE_CLICK  = "double_click"
G_FREEZE        = "freeze_cursor"
G_SCROLL_UP     = "scroll_up"
G_SCROLL_DOWN   = "scroll_down"
G_SWIPE_LEFT    = "swipe_left"
G_SWIPE_RIGHT   = "swipe_right"
G_SWIPE_UP      = "swipe_up"
G_SWIPE_DOWN    = "swipe_down"
G_THUMBS_UP     = "thumbs_up"
G_THUMBS_DOWN   = "thumbs_down"
G_OK_SIGN       = "ok_sign"
G_PEACE         = "peace_sign"
G_ROCK          = "rock_sign"
G_FIST          = "fist"
G_DRAWING       = "drawing_mode"
G_NONE          = "none"

# Velocity threshold for swipes (normalised units per frame, ~0.13)
SWIPE_VEL_THRESH  = 0.13
# Pinch/distance thresholds (normalised × 1000 ≈ px on 1280 frame)
CLICK_DIST_THRESH  = 30.0   # index+middle tips for left_click
RCLICK_DIST_THRESH = 25.0   # thumb+index for right_click
OK_DIST_THRESH     = 20.0   # thumb+index loop for ok_sign
PEACE_SPREAD_THRESH= 60.0   # index+middle spread for peace
DRAWING_HOLD_MS    = 450.0  # ms index must be alone before drawing_mode


@dataclass
class GestureResult:
    gesture_name: str    = G_NONE
    confidence:   float  = 0.0
    hand_label:   str    = "Right"
    cursor_x:     float  = 0.0
    cursor_y:     float  = 0.0
    metadata:     dict   = field(default_factory=dict)
    timestamp:    float  = field(default_factory=time.time)


class GestureClassifier:
    """
    Classifies hand landmarks into a GestureResult.

    Usage
    -----
    clf = GestureClassifier()
    result = clf.classify(landmarks_array, hand_label="Right")
    """

    def __init__(self, settings=None) -> None:
        self._analyzer = FingerAnalyzer()
        # Position history for velocity: deque of (x, y, timestamp)
        self._pos_history: deque[tuple[float, float, float]] = deque(maxlen=10)
        # Last left_click time for double_click detection
        self._last_lclick_time: float = 0.0
        self._double_click_window: float = 0.4  # seconds
        # Drawing mode hold tracking
        self._index_only_since: Optional[float] = None
        self._in_drawing_mode: bool = False

    def classify(self, landmarks: Optional[np.ndarray],
                 hand_label: str = "Right") -> GestureResult:
        """
        Parameters
        ----------
        landmarks  : np.ndarray shape (21, 3) or None
        hand_label : "Right" | "Left"

        Returns
        -------
        GestureResult
        """
        if landmarks is None or landmarks.shape != (21, 3):
            return GestureResult(gesture_name=G_NONE, confidence=0.0,
                                 hand_label=hand_label)

        fs = self._analyzer.analyze(landmarks)

        # Current wrist position (cursor anchor)
        cx = float(landmarks[FINGERTIP_IDS["index"], 0])
        cy = float(landmarks[FINGERTIP_IDS["index"], 1])

        now = time.time()
        self._pos_history.append((cx, cy, now))
        vx, vy = self._compute_velocity()

        # ── Classify in priority order ─────────────────────────────────────────

        # 1. Freeze cursor: all 5 extended + palm facing camera
        if fs.open_count == 5:
            orient = self._analyzer.get_palm_orientation(landmarks)
            if orient == "toward":
                return GestureResult(G_FREEZE, 0.80, hand_label, cx, cy,
                                     {"orientation": orient})

        # 2. Thumbs up / down (thumb extended, all others bent)
        if (fs.is_extended("thumb") and fs.is_bent("index")
                and fs.is_bent("middle") and fs.is_bent("ring")
                and fs.is_bent("pinky")):
            # Distinguish up vs down by thumb tip vs wrist Y
            thumb_tip_y = landmarks[FINGERTIP_IDS["thumb"], 1]
            wrist_y     = landmarks[0, 1]
            if thumb_tip_y < wrist_y - 0.08:
                return GestureResult(G_THUMBS_UP, 0.90, hand_label, cx, cy)
            if thumb_tip_y > wrist_y + 0.05:
                return GestureResult(G_THUMBS_DOWN, 0.90, hand_label, cx, cy)

        # 3. Rock sign: index + pinky extended, middle + ring bent
        if (fs.is_extended("index") and fs.is_extended("pinky")
                and fs.is_bent("middle") and fs.is_bent("ring")):
            return GestureResult(G_ROCK, 0.87, hand_label, cx, cy)

        # 4. Fist: all fingers bent
        if fs.closed_count >= 4:
            wrist_ang = self._analyzer.get_wrist_angle(landmarks)
            if wrist_ang < -15:
                conf = min(0.95, 0.75 + abs(wrist_ang) / 200.0)
                return GestureResult(G_SCROLL_UP, conf, hand_label, cx, cy,
                                     {"wrist_angle": wrist_ang})
            if wrist_ang > 15:
                conf = min(0.95, 0.75 + abs(wrist_ang) / 200.0)
                return GestureResult(G_SCROLL_DOWN, conf, hand_label, cx, cy,
                                     {"wrist_angle": wrist_ang})
            return GestureResult(G_FIST, 0.88, hand_label, cx, cy)

        # 5. Right click: thumb+index pinch
        if self._analyzer.is_pinching(landmarks, "thumb", "index", RCLICK_DIST_THRESH):
            if fs.is_bent("middle") and fs.is_bent("ring") and fs.is_bent("pinky"):
                return GestureResult(G_RIGHT_CLICK, 0.85, hand_label, cx, cy)

        # 6. OK sign: thumb+index loop, others extended
        if self._analyzer.is_pinching(landmarks, "thumb", "index", OK_DIST_THRESH):
            if (fs.is_extended("middle") and fs.is_extended("ring")
                    and fs.is_extended("pinky")):
                return GestureResult(G_OK_SIGN, 0.88, hand_label, cx, cy)

        # 7. Peace sign: index+middle extended and spread, others bent
        if (fs.is_extended("index") and fs.is_extended("middle")
                and fs.is_bent("ring") and fs.is_bent("pinky")):
            # Check spread
            idx_tip = landmarks[FINGERTIP_IDS["index"], :2]
            mid_tip = landmarks[FINGERTIP_IDS["middle"], :2]
            spread  = np.linalg.norm(idx_tip - mid_tip) * 1000.0

            # Swipe detection using velocity
            if abs(vx) > SWIPE_VEL_THRESH and abs(vx) > abs(vy) * 1.5:
                if vx < 0:
                    return GestureResult(G_SWIPE_LEFT, 0.85, hand_label, cx, cy,
                                         {"velocity_x": vx})
                return GestureResult(G_SWIPE_RIGHT, 0.85, hand_label, cx, cy,
                                     {"velocity_x": vx})

            # Left click: index+middle, tips close together
            if spread < CLICK_DIST_THRESH:
                return self._handle_click(hand_label, cx, cy)

            if spread > PEACE_SPREAD_THRESH:
                return GestureResult(G_PEACE, 0.87, hand_label, cx, cy,
                                     {"spread_px": spread})

        # 8. Three fingers up → swipe up/down
        if (fs.is_extended("index") and fs.is_extended("middle")
                and fs.is_extended("ring") and fs.is_bent("pinky")):
            if abs(vy) > SWIPE_VEL_THRESH and abs(vy) > abs(vx) * 1.5:
                if vy < 0:
                    return GestureResult(G_SWIPE_UP, 0.85, hand_label, cx, cy,
                                         {"velocity_y": vy})
                return GestureResult(G_SWIPE_DOWN, 0.85, hand_label, cx, cy,
                                     {"velocity_y": vy})

        # 9. Drawing mode: index only extended, held for 450ms
        if (fs.is_extended("index") and fs.is_bent("middle")
                and fs.is_bent("ring") and fs.is_bent("pinky")):
            if self._index_only_since is None:
                self._index_only_since = now
            held_ms = (now - self._index_only_since) * 1000.0
            if held_ms >= DRAWING_HOLD_MS:
                self._in_drawing_mode = True
                ext_ratio = self._analyzer.get_finger_angle(landmarks, "index") / 35.0
                conf = min(0.97, 0.85 + (1.0 - min(ext_ratio, 1.0)) * 0.12)
                return GestureResult(G_DRAWING, conf, hand_label, cx, cy,
                                     {"hold_ms": held_ms})
            # Before hold threshold: cursor_move
            self._in_drawing_mode = False
            conf = self._cursor_confidence(fs)
            return GestureResult(G_CURSOR_MOVE, conf, hand_label, cx, cy)
        else:
            self._index_only_since = None
            self._in_drawing_mode  = False

        # 10. Cursor move fallback
        if fs.is_extended("index"):
            conf = self._cursor_confidence(fs)
            return GestureResult(G_CURSOR_MOVE, conf, hand_label, cx, cy)

        return GestureResult(G_NONE, 0.0, hand_label, cx, cy)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _handle_click(self, hand_label: str,
                      cx: float, cy: float) -> GestureResult:
        now = time.time()
        if now - self._last_lclick_time < self._double_click_window:
            self._last_lclick_time = 0.0   # reset so triple doesn't trigger
            return GestureResult(G_DOUBLE_CLICK, 0.95, hand_label, cx, cy)
        self._last_lclick_time = now
        return GestureResult(G_LEFT_CLICK, 0.90, hand_label, cx, cy)

    def _compute_velocity(self) -> tuple[float, float]:
        """Velocity as delta between current and 4-frames-ago position."""
        if len(self._pos_history) < 5:
            return 0.0, 0.0
        old = self._pos_history[-5]
        new = self._pos_history[-1]
        dt  = max(new[2] - old[2], 1e-6)
        return (new[0] - old[0]) / dt, (new[1] - old[1]) / dt

    @staticmethod
    def _cursor_confidence(fs: FingerState) -> float:
        """Higher confidence when only index is extended and others are clearly bent."""
        bent_score = sum(
            1 for f in ("middle", "ring", "pinky") if fs.is_bent(f)
        ) / 3.0
        return round(0.70 + bent_score * 0.25, 3)
