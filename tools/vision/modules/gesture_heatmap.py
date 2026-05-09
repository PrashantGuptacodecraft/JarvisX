"""
tools/vision/modules/gesture_heatmap.py
Gesture Heatmap Dashboard — accumulates where gestures are fired on screen.
Shows a live semi-transparent heatmap overlay on the camera frame.
Press 'H' key to toggle visibility, rock sign to reset.
"""
from __future__ import annotations
import cv2
import numpy as np
import os
import time
import logging
from collections import defaultdict

log = logging.getLogger("gesture_heatmap")

_HEATMAP_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))))),
    "data", "heatmaps"
)

# Gestures to track (excludes cursor move to avoid noise)
TRACKED = {"LEFT_CLICK", "RIGHT_CLICK", "SCROLL_UP", "SCROLL_DOWN",
           "SCREENSHOT", "VOLUME_UP", "VOLUME_DOWN"}

HEATMAP_ALPHA = 0.45   # overlay transparency
DECAY_RATE    = 0.995  # per-frame decay (1.0 = no decay)
BLUR_KERNEL   = 25     # gaussian blur radius for heat spread


class GestureHeatmap:
    """
    Accumulates gesture fire positions and renders a color heatmap overlay.
    update(frame, hand_data, gesture_result) → None (modifies frame in-place)
    """

    def __init__(self) -> None:
        self._heatmap: np.ndarray | None = None  # float32 accumulation map
        self._visible = True
        self._counts: dict[str, int] = defaultdict(int)
        self._total_fires = 0
        self._last_reset  = time.time()
        os.makedirs(_HEATMAP_DIR, exist_ok=True)
        log.info("GestureHeatmap module initialized")

    # ── Public API ────────────────────────────────────────────────────────────

    def update(self, frame: np.ndarray, hand_data: dict,
               gesture_result: dict) -> None:
        h, w = frame.shape[:2]
        if self._heatmap is None:
            self._heatmap = np.zeros((h, w), dtype=np.float32)

        gesture = gesture_result.get("name", "NONE")
        cx      = gesture_result.get("cursor_x", w // 2)
        cy      = gesture_result.get("cursor_y", h // 2)

        # Map screen cursor coords back to frame coords
        # (cursor is on screen, frame is camera — approximate by normalization)
        lm = hand_data.get("landmarks")
        if lm is not None:
            fx = int(lm[8].x * w)
            fy = int(lm[8].y * h)
        else:
            fx, fy = w // 2, h // 2

        # Accumulate heat at gesture fire position
        if gesture in TRACKED:
            self._counts[gesture] += 1
            self._total_fires     += 1
            if 0 <= fx < w and 0 <= fy < h:
                self._heatmap[fy, fx] += 12.0

        # Reset on screenshot gesture (rock sign)
        if gesture == "SCREENSHOT":
            self._save_heatmap(frame)
            self._heatmap[:] = 0
            self._counts.clear()
            self._total_fires = 0

        # Decay + blur
        self._heatmap *= DECAY_RATE
        blurred = cv2.GaussianBlur(self._heatmap, (BLUR_KERNEL, BLUR_KERNEL), 0)

        # Render overlay
        if self._visible and self._total_fires > 0:
            self._render_overlay(frame, blurred, w, h)
            self._render_stats(frame, w, h)

    def _render_overlay(self, frame: np.ndarray, heat: np.ndarray,
                        w: int, h: int) -> None:
        # Normalize and colorize
        heat_norm = np.clip(heat / (heat.max() + 1e-6), 0, 1)
        heat_uint = (heat_norm * 255).astype(np.uint8)
        colored   = cv2.applyColorMap(heat_uint, cv2.COLORMAP_JET)

        # Only blend where heat > threshold (skip cold areas)
        mask = heat_norm > 0.05
        overlay = frame.copy()
        overlay[mask] = cv2.addWeighted(
            frame, 1 - HEATMAP_ALPHA, colored, HEATMAP_ALPHA, 0
        )[mask]
        frame[:] = overlay

    def _render_stats(self, frame: np.ndarray, w: int, h: int) -> None:
        """Draw gesture count sidebar."""
        sidebar_w = 160
        x0 = w - sidebar_w - 4
        y0 = 70
        overlay = frame.copy()
        cv2.rectangle(overlay, (x0, y0), (w - 4, y0 + len(self._counts) * 20 + 24),
                      (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.55, frame, 0.45, 0, frame)

        cv2.putText(frame, f"Gestures: {self._total_fires}", (x0 + 4, y0 + 14),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, (200, 200, 255), 1)
        for i, (g, cnt) in enumerate(sorted(self._counts.items(),
                                            key=lambda x: -x[1])):
            label = f"{g[:12]}: {cnt}"
            cv2.putText(frame, label, (x0 + 4, y0 + 30 + i * 18),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.37, (180, 255, 180), 1)

    def _save_heatmap(self, frame: np.ndarray) -> None:
        if self._heatmap is None:
            return
        ts = time.strftime("%Y%m%d_%H%M%S")
        path = os.path.join(_HEATMAP_DIR, f"heatmap_{ts}.png")
        cv2.imwrite(path, frame)
        log.info("Heatmap saved to %s", path)
