"""
tools/vision/modules/ar_overlay.py
AR Virtual Camera Overlay Module.

Renders augmented reality elements on the gesture camera frame:
- 3D-style floating coordinate axes on the wrist
- Real-time gesture label badge with animated border
- Virtual "button grid" that lights up when cursor hovers
- FPS + latency performance indicator
- Dynamic particle trail following the index fingertip
"""
from __future__ import annotations
import cv2
import math
import numpy as np
import time
import logging
from collections import deque

log = logging.getLogger("ar_overlay")

# ── Colors (BGR) ──────────────────────────────────────────────────────────────
C_AXIS_X   = (60,  60,  255)   # red   = X
C_AXIS_Y   = (60,  255, 60 )   # green = Y
C_AXIS_Z   = (255, 60,  60 )   # blue  = Z
C_PARTICLE = (0,   212, 255)   # cyan particles
C_BADGE    = (0,   200, 255)
C_GRID_OFF = (60,  60,  60 )
C_GRID_ON  = (0,   255, 100)

AXIS_LEN   = 40   # pixels
NUM_PARTICLES = 18
PARTICLE_TTL  = 0.6  # seconds

# Virtual button grid
_BUTTONS = [
    {"label": "CLK",  "gesture": "LEFT_CLICK"},
    {"label": "RCK",  "gesture": "RIGHT_CLICK"},
    {"label": "SCU",  "gesture": "SCROLL_UP"},
    {"label": "SCD",  "gesture": "SCROLL_DOWN"},
    {"label": "SCR",  "gesture": "SCREENSHOT"},
    {"label": "VOL+", "gesture": "VOLUME_UP"},
]


class AROverlay:
    """
    Augmented Reality overlay for the gesture camera feed.
    update(frame, hand_data, gesture_result) → None (in-place).
    """

    def __init__(self) -> None:
        self._particles: deque[dict] = deque(maxlen=NUM_PARTICLES)
        self._last_particle = 0.0
        self._angle = 0.0          # rotating axis animation
        self._last_gesture_time = 0.0
        self._last_gesture = "NONE"
        log.info("AROverlay module initialized")

    def update(self, frame: np.ndarray, hand_data: dict,
               gesture_result: dict) -> None:
        h, w = frame.shape[:2]
        lm      = hand_data.get("landmarks")
        gesture = gesture_result.get("name", "NONE")
        now     = time.time()

        self._angle = (self._angle + 2.0) % 360.0

        if lm is not None:
            # ── 1. Particle trail on index fingertip ──────────────────────────
            tip_x = int(lm[8].x * w)
            tip_y = int(lm[8].y * h)
            if gesture == "CURSOR_MOVE" and now - self._last_particle > 0.025:
                self._particles.append({
                    "x": tip_x + np.random.randint(-3, 4),
                    "y": tip_y + np.random.randint(-3, 4),
                    "born": now,
                    "r": np.random.randint(2, 6),
                })
                self._last_particle = now

            # Draw + expire particles
            for p in list(self._particles):
                age   = now - p["born"]
                if age > PARTICLE_TTL:
                    continue
                alpha_f = 1.0 - age / PARTICLE_TTL
                radius  = max(1, int(p["r"] * alpha_f))
                color   = tuple(int(c * alpha_f) for c in C_PARTICLE)
                cv2.circle(frame, (p["x"], p["y"]), radius, color, -1, cv2.LINE_AA)

            # ── 2. 3D Axes on wrist ───────────────────────────────────────────
            wx = int(lm[0].x * w)
            wy = int(lm[0].y * h)
            rad = math.radians(self._angle)
            for (dx, dy), color in [
                ((math.cos(rad), -math.sin(rad)),         C_AXIS_X),
                ((math.cos(rad + math.pi/2), -math.sin(rad + math.pi/2)), C_AXIS_Y),
                ((0, -1),                                  C_AXIS_Z),
            ]:
                ex = wx + int(dx * AXIS_LEN)
                ey = wy + int(dy * AXIS_LEN)
                cv2.arrowedLine(frame, (wx, wy), (ex, ey), color, 1,
                                tipLength=0.25, line_type=cv2.LINE_AA)

        # ── 3. Gesture badge (animated border) ────────────────────────────────
        if gesture not in ("NONE", "CURSOR_MOVE"):
            self._last_gesture      = gesture
            self._last_gesture_time = now

        age_g = now - self._last_gesture_time
        if age_g < 1.5 and self._last_gesture != "NONE":
            pulse = 0.5 + 0.5 * math.sin(now * 6)  # 3 Hz
            border_col = tuple(int(c * pulse) for c in C_BADGE)
            label = self._last_gesture.replace("_", " ")
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.65, 2)
            bx, by = (w - tw) // 2, h - 55
            cv2.rectangle(frame, (bx - 10, by - th - 8),
                          (bx + tw + 10, by + 8), border_col, 2, cv2.LINE_AA)
            cv2.putText(frame, label, (bx, by),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.65, C_BADGE, 2, cv2.LINE_AA)

        # ── 4. Virtual button grid (bottom-left) ──────────────────────────────
        bw, bh, pad = 46, 22, 5
        for i, btn in enumerate(_BUTTONS):
            bx0 = pad + i * (bw + pad)
            by0 = h - bh - pad
            active = gesture == btn["gesture"]
            color  = C_GRID_ON if active else C_GRID_OFF
            cv2.rectangle(frame, (bx0, by0), (bx0 + bw, by0 + bh), color, -1 if active else 1)
            cv2.putText(frame, btn["label"], (bx0 + 3, by0 + 14),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.35,
                        (0, 0, 0) if active else (160, 160, 160), 1)

        # ── 5. Performance ring (top-right) ───────────────────────────────────
        cx, cy, r = w - 24, 24, 18
        t_frac    = (now % 2.0) / 2.0
        angle_end = int(360 * t_frac)
        cv2.ellipse(frame, (cx, cy), (r, r), -90, 0, angle_end,
                    (0, 180, 255), 2, cv2.LINE_AA)
