"""
ui/hud_renderer.py
HUDRenderer — composites all HUD elements onto the camera frame.
Z-order (bottom→top): animated border → scan line → skeleton →
  corner brackets → gesture label → history → mode → FPS →
  voice status → cooldown indicators → pulse ring.
"""
from __future__ import annotations

import logging
import math
import time
from collections import deque
from typing import Any, Optional

import cv2
import numpy as np

from ui.hud_assets import (
    COLOR_CYAN, COLOR_GREEN, COLOR_GRAY, COLOR_ORANGE, COLOR_WHITE,
    COLOR_YELLOW, COLOR_TEAL, COLOR_RED, COLOR_DARK_BG, COLOR_PURPLE,
    GESTURE_COLORS, FONT, FONT_MONO,
    FONT_SCALE_LARGE, FONT_SCALE_MEDIUM, FONT_SCALE_SMALL, FONT_SCALE_TINY,
    FONT_THICKNESS, FONT_THICKNESS_THIN,
    CORNER_BRACKET_SIZE, CORNER_BRACKET_THICKNESS,
    HISTORY_MAX_ITEMS, HISTORY_ITEM_HEIGHT, SIDEBAR_WIDTH,
    BADGE_HEIGHT, BADGE_PADDING, HUD_MARGIN,
    PULSE_DURATION_FRAMES, SCAN_LINE_SPEED, HAND_CONNECTIONS,
    FINGERTIP_IDS, CONF_HIGH, CONF_MEDIUM, WAVEFORM_BARS,
)

log = logging.getLogger(__name__)


class HUDRenderer:
    """
    Renders the complete JARVIS HUD onto every camera frame.

    Call update() each frame — it composites all layers in z-order.
    """

    def __init__(self, settings=None) -> None:
        self.frame_count:      int   = 0
        self.gesture_history:  deque = deque(maxlen=HISTORY_MAX_ITEMS)
        self.last_gesture_name: str  = "none"
        self.pulse_frame:      int   = 0
        self.scan_line_y:      int   = 0
        self._pulse_center:    tuple = (100, 100)

    # ── Main update ───────────────────────────────────────────────────────────

    def update(
        self,
        frame:           np.ndarray,
        tracking_result,                    # HandTrackingResult or None
        gesture_result,                     # GestureResult or None
        guard_status:    dict  = None,
        fusion_status          = None,
        mode_name:       str   = "normal",
        fps:             float = 0.0,
    ) -> np.ndarray:
        """Composite all HUD layers. Modifies frame in-place and returns it."""
        self.frame_count += 1
        self.scan_line_y  = (self.scan_line_y + SCAN_LINE_SPEED) % frame.shape[0]

        gesture_name = "none"
        confidence   = 0.0
        landmarks    = None
        hand_label   = "Right"

        if gesture_result is not None:
            gesture_name = getattr(gesture_result, "gesture_name", "none")
            confidence   = getattr(gesture_result, "confidence",   0.0)
        if tracking_result is not None and tracking_result.hand_count > 0:
            landmarks  = tracking_result.landmarks_list[0]
            hand_label = tracking_result.handedness_list[0] if tracking_result.handedness_list else "Right"

        # Update history
        if gesture_name not in ("none", "cursor_move") and gesture_name != self.last_gesture_name:
            self.update_history(gesture_name)
            self.last_gesture_name = gesture_name

        # Cursor center for pulse ring
        if gesture_result is not None:
            h, w = frame.shape[:2]
            cx = int(getattr(gesture_result, "cursor_x", 0.5) * w)
            cy = int(getattr(gesture_result, "cursor_y", 0.5) * h)
            self._pulse_center = (cx, cy)

        # ── Z-order rendering ──────────────────────────────────────────────
        self.draw_animated_border(frame)
        self.draw_scanning_line(frame)
        if landmarks is not None:
            self.draw_hand_landmarks(frame, landmarks, hand_label)
        self.draw_corner_brackets(frame)
        if gesture_name not in ("none",):
            h, w = frame.shape[:2]
            self.draw_gesture_label(frame, gesture_name, confidence,
                                    (HUD_MARGIN, h // 2 - 30))
        self.draw_gesture_history(frame, self.gesture_history)
        self.draw_mode_indicator(frame, mode_name)
        self.draw_fps_counter(frame, fps)

        # Voice status
        if fusion_status is not None:
            is_active   = getattr(fusion_status, "is_voice_active", False)
            last_phrase = getattr(fusion_status, "last_phrase", "")
            fusion_score = getattr(fusion_status, "fusion_score", 0.0)
            self.draw_voice_status(frame, is_active, last_phrase, fusion_score)

        if guard_status:
            self.draw_cooldown_indicators(frame, guard_status)

        if gesture_name in ("left_click", "double_click", "right_click"):
            self.draw_pulse_ring(frame, self._pulse_center)

        return frame

    # ── Drawing methods ───────────────────────────────────────────────────────

    def draw_corner_brackets(self, frame: np.ndarray) -> None:
        """Four L-shaped corner brackets in cyan."""
        h, w = frame.shape[:2]
        m = HUD_MARGIN
        L = CORNER_BRACKET_SIZE
        t = CORNER_BRACKET_THICKNESS
        c = COLOR_CYAN

        # Top-left
        cv2.line(frame, (m, m),     (m + L, m),     c, t, cv2.LINE_AA)
        cv2.line(frame, (m, m),     (m, m + L),     c, t, cv2.LINE_AA)
        # Top-right
        cv2.line(frame, (w-m, m),   (w-m-L, m),     c, t, cv2.LINE_AA)
        cv2.line(frame, (w-m, m),   (w-m, m+L),     c, t, cv2.LINE_AA)
        # Bottom-left
        cv2.line(frame, (m, h-m),   (m+L, h-m),     c, t, cv2.LINE_AA)
        cv2.line(frame, (m, h-m),   (m, h-m-L),     c, t, cv2.LINE_AA)
        # Bottom-right
        cv2.line(frame, (w-m, h-m), (w-m-L, h-m),   c, t, cv2.LINE_AA)
        cv2.line(frame, (w-m, h-m), (w-m, h-m-L),   c, t, cv2.LINE_AA)

    def draw_scanning_line(self, frame: np.ndarray) -> None:
        """Translucent cyan horizontal scan line moving top→bottom."""
        h, w = frame.shape[:2]
        y = self.scan_line_y
        overlay = frame.copy()
        cv2.line(overlay, (0, y), (w, y), COLOR_CYAN, 1)
        cv2.addWeighted(overlay, 0.20, frame, 0.80, 0, frame)

    def draw_hand_landmarks(self, frame: np.ndarray,
                             landmarks: list, hand_label: str) -> None:
        """Skeleton + colored fingertip dots."""
        h, w = frame.shape[:2]
        hand_col = COLOR_CYAN if hand_label == "Right" else COLOR_ORANGE

        pts = [(int(lm.x * w), int(lm.y * h)) for lm in landmarks]

        # Connections
        for a, b in HAND_CONNECTIONS:
            if a < len(pts) and b < len(pts):
                cv2.line(frame, pts[a], pts[b], (200, 200, 200), 1, cv2.LINE_AA)

        # Joints
        for i, pt in enumerate(pts):
            if i in FINGERTIP_IDS:
                cv2.circle(frame, pt, 5, hand_col, -1, cv2.LINE_AA)
                cv2.circle(frame, pt, 6, COLOR_WHITE, 1, cv2.LINE_AA)
            elif i == 0:
                cv2.circle(frame, pt, 5, COLOR_YELLOW, -1, cv2.LINE_AA)
            else:
                cv2.circle(frame, pt, 3, (180, 180, 180), -1, cv2.LINE_AA)

    def draw_pulse_ring(self, frame: np.ndarray,
                         center_xy: tuple) -> None:
        """Expanding fading ring at the click point."""
        progress = (self.frame_count % PULSE_DURATION_FRAMES) / PULSE_DURATION_FRAMES
        radius   = int(30 + progress * 30)
        alpha    = 1.0 - progress
        col      = tuple(int(c * alpha) for c in COLOR_CYAN)
        overlay  = frame.copy()
        cv2.circle(overlay, center_xy, radius, col, 2, cv2.LINE_AA)
        cv2.addWeighted(overlay, alpha, frame, 1.0 - alpha, 0, frame)

    def draw_gesture_label(self, frame: np.ndarray,
                            gesture_name: str, confidence: float,
                            position: tuple) -> None:
        """Semi-transparent badge with gesture name and confidence."""
        label     = gesture_name.replace("_", " ").upper()
        conf_text = f"{int(confidence * 100)}%"
        col       = GESTURE_COLORS.get(gesture_name, COLOR_WHITE)

        (tw, th), _ = cv2.getTextSize(label, FONT, FONT_SCALE_MEDIUM, FONT_THICKNESS)
        px, py = position
        pad = BADGE_PADDING

        # Dark background
        overlay = frame.copy()
        cv2.rectangle(overlay, (px - pad, py - th - pad),
                       (px + tw + pad, py + 24), COLOR_DARK_BG, -1)
        cv2.addWeighted(overlay, 0.65, frame, 0.35, 0, frame)

        # Gesture name
        cv2.putText(frame, label, (px, py), FONT,
                    FONT_SCALE_MEDIUM, col, FONT_THICKNESS, cv2.LINE_AA)
        # Confidence
        cv2.putText(frame, conf_text, (px, py + 18), FONT,
                    FONT_SCALE_TINY, COLOR_GRAY, FONT_THICKNESS_THIN, cv2.LINE_AA)

    def draw_fps_counter(self, frame: np.ndarray, fps: float) -> None:
        """FPS in top-right corner."""
        h, w = frame.shape[:2]
        label = f"FPS: {fps:.1f}"
        (tw, _), _ = cv2.getTextSize(label, FONT, FONT_SCALE_SMALL, FONT_THICKNESS_THIN)
        cv2.putText(frame, label, (w - tw - HUD_MARGIN, HUD_MARGIN + 14),
                    FONT, FONT_SCALE_SMALL, COLOR_GRAY,
                    FONT_THICKNESS_THIN, cv2.LINE_AA)

    def draw_mode_indicator(self, frame: np.ndarray, mode_name: str) -> None:
        """Mode badge in top-left."""
        if mode_name == "normal":
            return
        col   = COLOR_GREEN if mode_name == "precision" else COLOR_YELLOW
        label = mode_name.upper()
        cv2.putText(frame, label, (HUD_MARGIN, HUD_MARGIN + 14),
                    FONT, FONT_SCALE_SMALL, col, FONT_THICKNESS_THIN, cv2.LINE_AA)

    def draw_voice_status(self, frame: np.ndarray,
                           is_active: bool, last_phrase: str,
                           fusion_score: float) -> None:
        """Microphone icon + voice status at bottom-left."""
        h, w = frame.shape[:2]
        bx, by = HUD_MARGIN, h - 55

        # Mic body (rectangle)
        mic_col = COLOR_GREEN if is_active else COLOR_GRAY
        cv2.rectangle(frame, (bx + 4, by),      (bx + 16, by + 16), mic_col, -1)
        cv2.rectangle(frame, (bx + 4, by),      (bx + 16, by + 16), mic_col, 1)
        # Mic stand
        cv2.line(frame, (bx + 10, by + 16), (bx + 10, by + 22), mic_col, 2)
        cv2.line(frame, (bx + 6,  by + 22), (bx + 14, by + 22), mic_col, 2)

        # Pulse ring when active
        if is_active:
            pulse_r = int(16 + 6 * abs(math.sin(time.time() * 8)))
            overlay = frame.copy()
            cv2.circle(overlay, (bx + 10, by + 10), pulse_r, COLOR_GREEN, 1)
            cv2.addWeighted(overlay, 0.5, frame, 0.5, 0, frame)

        # Last phrase
        phrase_disp = (last_phrase[:28] + "…") if len(last_phrase) > 28 else last_phrase
        cv2.putText(frame, phrase_disp, (bx + 24, by + 10),
                    FONT, FONT_SCALE_TINY, mic_col, FONT_THICKNESS_THIN, cv2.LINE_AA)

        # Fusion score bar
        bar_w = 120
        filled = int(fusion_score * bar_w)
        bar_col = COLOR_GREEN if fusion_score > 0.72 else COLOR_YELLOW
        cv2.rectangle(frame, (bx, by + 28), (bx + bar_w, by + 34), (50, 50, 50), -1)
        if filled > 0:
            cv2.rectangle(frame, (bx, by + 28), (bx + filled, by + 34), bar_col, -1)
        cv2.putText(frame, f"{fusion_score:.2f}", (bx + bar_w + 4, by + 34),
                    FONT, FONT_SCALE_TINY, COLOR_GRAY, FONT_THICKNESS_THIN, cv2.LINE_AA)

    def draw_gesture_history(self, frame: np.ndarray, history: deque) -> None:
        """Right sidebar with fading gesture history."""
        h, w = frame.shape[:2]
        x0 = w - SIDEBAR_WIDTH
        y0 = HUD_MARGIN + 30

        # Sidebar background
        overlay = frame.copy()
        cv2.rectangle(overlay, (x0, y0 - 4),
                       (w - HUD_MARGIN, y0 + HISTORY_MAX_ITEMS * HISTORY_ITEM_HEIGHT + 8),
                       COLOR_DARK_BG, -1)
        cv2.addWeighted(overlay, 0.50, frame, 0.50, 0, frame)

        # Header
        cv2.putText(frame, "HISTORY", (x0 + 4, y0 + 10),
                    FONT, FONT_SCALE_TINY, COLOR_CYAN, FONT_THICKNESS_THIN, cv2.LINE_AA)

        now = time.time()
        items = list(reversed(history))
        for i, (g_name, ts) in enumerate(items):
            age     = now - ts
            fade    = max(0.25, 1.0 - age / 8.0)
            col     = GESTURE_COLORS.get(g_name, COLOR_GRAY)
            col_f   = tuple(int(c * fade) for c in col)
            label   = g_name.replace("_", " ")
            age_str = f"{int(age)}s"
            y       = y0 + 26 + i * HISTORY_ITEM_HEIGHT
            cv2.putText(frame, label,   (x0 + 4, y),
                        FONT, FONT_SCALE_TINY, col_f, FONT_THICKNESS_THIN, cv2.LINE_AA)
            cv2.putText(frame, age_str, (w - HUD_MARGIN - 28, y),
                        FONT, FONT_SCALE_TINY, (80, 80, 80), FONT_THICKNESS_THIN, cv2.LINE_AA)

    def draw_animated_border(self, frame: np.ndarray) -> None:
        """Single-pixel animated border with oscillating cyan hue."""
        h, w = frame.shape[:2]
        t   = self.frame_count * 0.05
        val = int(180 + 75 * math.sin(t))
        col = (val, val, 0)   # cyan-ish oscillation in BGR
        cv2.rectangle(frame, (0, 0), (w - 1, h - 1), col, 1)

    def draw_cooldown_indicators(self, frame: np.ndarray,
                                  guard_status: dict) -> None:
        """
        Small arc indicators for gestures currently on cooldown.
        Positioned in bottom-right corner cluster.
        """
        h, w = frame.shape[:2]
        # Filter to only gestures that are on cooldown and have short cooldowns
        on_cd = [
            (g, info) for g, info in guard_status.items()
            if not info["ready"] and info["remaining_ms"] > 0
            and g not in ("cursor_move", "none", "freeze_cursor")
        ]
        on_cd.sort(key=lambda x: x[1]["remaining_ms"])

        pad = 8
        cx0 = w - HUD_MARGIN - 18
        cy0 = h - HUD_MARGIN - 18

        for idx, (gesture, info) in enumerate(on_cd[:6]):
            remaining = info["remaining_ms"]
            cooldown  = max(remaining, 1)

            # Find max cooldown from guard status last_fired_ms
            total_cd  = remaining + info.get("last_fired_ms", remaining)
            frac      = 1.0 - (remaining / max(total_cd, 1))
            angle     = int(frac * 360)

            cx = cx0 - idx * (36 + pad)
            cy = cy0

            col = GESTURE_COLORS.get(gesture, COLOR_GRAY)
            # Background circle
            cv2.circle(frame, (cx, cy), 16, (40, 40, 40), -1)
            # Arc showing cooldown progress
            cv2.ellipse(frame, (cx, cy), (16, 16), -90, 0, angle,
                        col, 2, cv2.LINE_AA)
            # Tiny label
            short = gesture[:3].upper()
            cv2.putText(frame, short, (cx - 10, cy + 4),
                        FONT, 0.30, col, 1, cv2.LINE_AA)

    def update_history(self, gesture_name: str) -> None:
        """Append gesture name with current timestamp to history deque."""
        self.gesture_history.append((gesture_name, time.time()))
