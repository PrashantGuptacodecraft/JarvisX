"""
ui/hud_renderer.py
Full OpenCV HUD: landmarks, gesture label, confidence, pulsing indicator,
FPS counter, gesture history sidebar, mode indicator.
Right hand = cyan, Left hand = orange.
"""
from __future__ import annotations
import math
import time
from collections import deque
from typing import Optional


# ── HUD Colors (BGR) ─────────────────────────────────────────────────────────
C_RIGHT_HAND    = (255, 212, 0)    # cyan
C_LEFT_HAND     = (0, 165, 255)    # orange
C_EXTENDED      = (0, 255, 100)    # green fingertip
C_BENT          = (60, 60, 255)    # red fingertip
C_SKELETON      = (255, 255, 255)  # white bones
C_TEXT          = (255, 255, 255)
C_BG            = (0, 0, 0)
C_CORNER        = (0, 200, 255)
C_PULSE         = (0, 255, 200)

SKELETON_PAIRS = [
    (0,1),(1,2),(2,3),(3,4),
    (0,5),(5,6),(6,7),(7,8),
    (0,9),(9,10),(10,11),(11,12),
    (0,13),(13,14),(14,15),(15,16),
    (0,17),(17,18),(18,19),(19,20),
    (5,9),(9,13),(13,17),(5,17),
]
FINGERTIP_IDS = [4, 8, 12, 16, 20]


class HUDRenderer:
    """Renders all HUD overlays onto a BGR camera frame."""

    def __init__(self) -> None:
        self._fps_history: deque[float] = deque(maxlen=30)
        self._last_frame_t = time.time()
        self._pulse_start: Optional[float] = None
        self._current_gesture: str = "NONE"
        self._mode = "PRECISION"

    # ── Main render entry ─────────────────────────────────────────────────────

    def render(self, frame, right_result=None, left_result=None,
               right_lm=None, left_lm=None, right_fs=None, left_fs=None,
               gesture_history: Optional[deque] = None) -> None:
        """Draw full HUD onto frame (in-place)."""
        import cv2
        now = time.time()
        dt = now - self._last_frame_t
        self._last_frame_t = now
        fps = 1.0 / dt if dt > 0 else 0
        self._fps_history.append(fps)
        avg_fps = sum(self._fps_history) / len(self._fps_history)

        # Skeleton + landmarks
        if right_lm is not None:
            self._draw_skeleton(frame, right_lm, C_RIGHT_HAND, right_fs)
        if left_lm is not None:
            self._draw_skeleton(frame, left_lm, C_LEFT_HAND, left_fs)

        # Gesture labels
        h, w = frame.shape[:2]
        y_offset = 52
        if right_result and right_result.name != "NONE":
            self._draw_gesture_label(frame, right_result, w, y_offset, C_RIGHT_HAND)
            y_offset += 46
            self._update_pulse(right_result.name)
        if left_result and left_result.name != "NONE":
            self._draw_gesture_label(frame, left_result, w, y_offset, C_LEFT_HAND)
            self._update_pulse(left_result.name)

        # Pulsing indicator
        self._draw_pulse(frame, now)

        # FPS counter top-right
        fps_txt = f"FPS {avg_fps:.0f}"
        (fw, fh), _ = cv2.getTextSize(fps_txt, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
        cv2.putText(frame, fps_txt, (w - fw - 10, 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (180, 180, 180), 1, cv2.LINE_AA)

        # Mode indicator top-left
        self._draw_mode(frame)

        # Corner HUD brackets
        self._draw_corners(frame, w, h)

        # Gesture history sidebar
        if gesture_history:
            self._draw_sidebar(frame, gesture_history, w, h)

    # ── Sub-renderers ─────────────────────────────────────────────────────────

    def _draw_skeleton(self, frame, lm, hand_color: tuple,
                       fs=None) -> None:
        import cv2
        h, w = frame.shape[:2]
        pts = [(int(p.x * w), int(p.y * h)) for p in lm]

        # Bones
        for a, b in SKELETON_PAIRS:
            cv2.line(frame, pts[a], pts[b], C_SKELETON, 1, cv2.LINE_AA)

        # Landmark dots
        for i, pt in enumerate(pts):
            color = hand_color
            r = 3
            if i in FINGERTIP_IDS:
                tip_idx = FINGERTIP_IDS.index(i)
                if fs is not None:
                    color = C_EXTENDED if fs.extended[tip_idx] else C_BENT
                r = 6
            cv2.circle(frame, pt, r, color, -1, cv2.LINE_AA)

    def _draw_gesture_label(self, frame, result, frame_w: int,
                            y: int, color: tuple) -> None:
        import cv2
        label = f"{result.name.replace('_', ' ')}  {result.confidence * 100:.0f}%"
        font, scale, thick = cv2.FONT_HERSHEY_SIMPLEX, 0.72, 2
        (tw, th), _ = cv2.getTextSize(label, font, scale, thick)
        x = (frame_w - tw) // 2
        # Semi-transparent pill background
        overlay = frame.copy()
        cv2.rectangle(overlay, (x - 10, y - th - 8), (x + tw + 10, y + 6),
                      C_BG, -1)
        cv2.addWeighted(overlay, 0.55, frame, 0.45, 0, frame)
        cv2.putText(frame, label, (x, y), font, scale, color, thick, cv2.LINE_AA)

    def _update_pulse(self, gesture: str) -> None:
        if gesture not in ("NONE", "CURSOR_MOVE"):
            if self._pulse_start is None:
                self._pulse_start = time.time()
        else:
            self._pulse_start = None

    def _draw_pulse(self, frame, now: float) -> None:
        import cv2
        if self._pulse_start is None:
            return
        h, w = frame.shape[:2]
        elapsed = now - self._pulse_start
        # 2 Hz pulsing: radius oscillates 18–36px
        radius = int(18 + 9 * math.sin(2 * math.pi * 2 * elapsed))
        alpha = 0.4 + 0.3 * math.sin(2 * math.pi * 2 * elapsed)
        cx, cy = w // 2, h - 40
        overlay = frame.copy()
        cv2.circle(overlay, (cx, cy), radius, C_PULSE, 2, cv2.LINE_AA)
        cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0, frame)

    def _draw_mode(self, frame) -> None:
        import cv2
        color = (100, 255, 100) if self._mode == "PRECISION" else (0, 165, 255)
        cv2.putText(frame, f"[{self._mode}]", (8, 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 1, cv2.LINE_AA)

    def _draw_corners(self, frame, w: int, h: int) -> None:
        import cv2
        L = 28
        for (x, y, dx, dy) in [(6,6,1,1),(w-6,6,-1,1),(6,h-6,1,-1),(w-6,h-6,-1,-1)]:
            cv2.line(frame, (x,y), (x+dx*L, y), C_CORNER, 2)
            cv2.line(frame, (x,y), (x, y+dy*L), C_CORNER, 2)

    def _draw_sidebar(self, frame, history: deque, w: int, h: int) -> None:
        import cv2
        sidebar_x = w - 160
        overlay = frame.copy()
        cv2.rectangle(overlay, (sidebar_x - 4, 30), (w - 2, 30 + len(history) * 22 + 8),
                      (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.5, frame, 0.5, 0, frame)
        for i, (name, ts) in enumerate(reversed(list(history))):
            age = time.time() - ts
            alpha_color = max(60, 255 - int(age * 30))
            txt = f"{name[:14]}  {age:.1f}s"
            cv2.putText(frame, txt, (sidebar_x, 48 + i * 22),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.38,
                        (alpha_color, alpha_color, alpha_color), 1, cv2.LINE_AA)

    def set_mode(self, mode: str) -> None:
        self._mode = mode
