"""
tools/vision/modules/air_drawing.py
Air Drawing Module — draw in the air with your index finger.

Activation: index finger up (G_CURSOR gesture) and index tip is extended.
Clear canvas: open palm (G_SCROLL_U).
Save: rock sign (G_SHOT).
"""
from __future__ import annotations
import cv2
import numpy as np
import os
import time
import logging
from collections import deque
from typing import Optional

log = logging.getLogger("air_drawing")

# ── Colors (BGR) cycling with pinky state ─────────────────────────────────────
PALETTE = [
    (0,   255, 100),   # green
    (0,   200, 255),   # cyan
    (255, 100, 0  ),   # blue
    (100, 0,   255),   # violet
    (0,   100, 255),   # orange
    (0,   0,   255),   # red
    (255, 255, 255),   # white
]
BRUSH_SIZES = [2, 4, 7, 11]  # cycle with thumb gesture

_SAVE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))))),
    "data", "drawings"
)


class AirDrawing:
    """
    Draws on a transparent canvas overlaid on the camera frame.
    update(frame, hand_data, gesture_result) → annotated frame.
    """

    def __init__(self) -> None:
        self._canvas:  Optional[np.ndarray] = None  # initialized on first frame
        self._prev_pt: Optional[tuple]      = None
        self._color_idx  = 0
        self._brush_idx  = 1
        self._drawing    = False
        self._last_clear = 0.0
        self._last_save  = 0.0
        self._stroke_buf: deque = deque(maxlen=4)  # smooth tip path
        os.makedirs(_SAVE_DIR, exist_ok=True)
        log.info("AirDrawing module initialized")

    # ── Public API ────────────────────────────────────────────────────────────

    def update(self, frame: np.ndarray, hand_data: dict,
               gesture_result: dict) -> None:
        """Annotate frame with air-drawing canvas. Modifies frame in-place."""
        h, w = frame.shape[:2]
        if self._canvas is None:
            self._canvas = np.zeros((h, w, 3), dtype=np.uint8)

        gesture = gesture_result.get("name", "NONE")
        lm      = hand_data.get("landmarks")

        # ── Canvas actions ────────────────────────────────────────────────────
        now = time.time()

        # Clear canvas on open palm
        if gesture == "SCROLL_UP" and now - self._last_clear > 1.5:
            self._canvas[:] = 0
            self._prev_pt   = None
            self._last_clear = now
            log.info("AirDrawing: canvas cleared")
            return

        # Save canvas on screenshot gesture
        if gesture == "SCREENSHOT" and now - self._last_save > 2.0:
            self._save_canvas(frame)
            self._last_save = now
            return

        # Change color on right click (index+middle+ring)
        if gesture == "RIGHT_CLICK":
            self._color_idx = (self._color_idx + 1) % len(PALETTE)
            self._prev_pt   = None
            return

        # ── Drawing ───────────────────────────────────────────────────────────
        if gesture == "CURSOR_MOVE" and lm is not None:
            tip_x = int(lm[8].x * w)
            tip_y = int(lm[8].y * h)
            self._stroke_buf.append((tip_x, tip_y))

            if len(self._stroke_buf) >= 2:
                # Smooth via average of last 3 points
                avg_x = int(sum(p[0] for p in self._stroke_buf) / len(self._stroke_buf))
                avg_y = int(sum(p[1] for p in self._stroke_buf) / len(self._stroke_buf))
                pt = (avg_x, avg_y)

                if self._prev_pt is not None:
                    color = PALETTE[self._color_idx]
                    thickness = BRUSH_SIZES[self._brush_idx]
                    cv2.line(self._canvas, self._prev_pt, pt, color, thickness, cv2.LINE_AA)
                self._prev_pt = pt
        else:
            self._prev_pt = None  # lift pen when not cursor gesture

        # ── Blend canvas onto frame ───────────────────────────────────────────
        mask = cv2.cvtColor(self._canvas, cv2.COLOR_BGR2GRAY)
        _, mask = cv2.threshold(mask, 1, 255, cv2.THRESH_BINARY)
        frame[mask > 0] = self._canvas[mask > 0]

        # Drawing HUD
        color = PALETTE[self._color_idx]
        cv2.circle(frame, (w - 30, 30), BRUSH_SIZES[self._brush_idx] + 2, color, -1)
        cv2.putText(frame, "DRAW", (w - 70, 55),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)

    def clear(self) -> None:
        if self._canvas is not None:
            self._canvas[:] = 0
        self._prev_pt = None

    def _save_canvas(self, frame: np.ndarray) -> None:
        ts = time.strftime("%Y%m%d_%H%M%S")
        blended = frame.copy()
        path = os.path.join(_SAVE_DIR, f"drawing_{ts}.png")
        cv2.imwrite(path, blended)
        log.info("AirDrawing saved to %s", path)
