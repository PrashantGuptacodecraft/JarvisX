"""
control/mouse_controller.py
Non-linear acceleration curve + edge magnetism + calibration-aware mapping.
"""
from __future__ import annotations
import math
from typing import Optional

try:
    import pyautogui
    pyautogui.FAILSAFE = False
    pyautogui.PAUSE = 0
    _HAS_PYAUTOGUI = True
except ImportError:
    _HAS_PYAUTOGUI = False


# ── Acceleration curve config ─────────────────────────────────────────────────
SLOW_VEL        = 0.04   # normalized velocity: below = precision mode (0.5x)
FAST_VEL        = 0.15   # normalized velocity: above = fast mode (2.2x)
SLOW_MULT       = 0.50
FAST_MULT       = 2.20
EDGE_DIST_PX    = 40     # pixels from edge: apply edge magnetism
EDGE_MULT       = 0.30   # speed multiplier near edges


class MouseController:
    """
    Handles all mouse movement and click operations.
    Uses non-linear acceleration and edge magnetism.
    """

    def __init__(self, screen_w: int, screen_h: int,
                 calibration: Optional[dict] = None) -> None:
        self._sw, self._sh = screen_w, screen_h
        self._cal = calibration or {}
        self._precision_mode = self._cal.get("precision_mode", True)
        self._last_x: float = screen_w / 2
        self._last_y: float = screen_h / 2

        # Coordinate mapping bounds from calibration (or defaults)
        bounds = self._cal.get("screen_bounds", {})
        self._map_x0 = bounds.get("x0", 0.05)
        self._map_x1 = bounds.get("x1", 0.95)
        self._map_y0 = bounds.get("y0", 0.05)
        self._map_y1 = bounds.get("y1", 0.90)

    # ── Public API ────────────────────────────────────────────────────────────

    def map_landmark(self, norm_x: float, norm_y: float) -> tuple[float, float]:
        """Map normalized hand position to raw screen coordinates."""
        rx = (norm_x - self._map_x0) / max(self._map_x1 - self._map_x0, 1e-6)
        ry = (norm_y - self._map_y0) / max(self._map_y1 - self._map_y0, 1e-6)
        rx = max(0.0, min(1.0, rx))
        ry = max(0.0, min(1.0, ry))
        return rx * self._sw, ry * self._sh

    def apply_acceleration(self, raw_x: float, raw_y: float) -> tuple[float, float]:
        """Apply non-linear acceleration based on velocity."""
        dx = raw_x - self._last_x
        dy = raw_y - self._last_y
        norm_vel = math.hypot(dx / self._sw, dy / self._sh)
        mult = self._velocity_multiplier(norm_vel)

        # Edge magnetism
        mult = self._apply_edge_magnetism(raw_x, raw_y, mult)

        # Mode sensitivity adjustment
        if self._precision_mode:
            mult *= 0.55
        else:
            mult *= 1.9

        cx = self._last_x + dx * mult
        cy = self._last_y + dy * mult
        cx = max(0.0, min(float(self._sw - 1), cx))
        cy = max(0.0, min(float(self._sh - 1), cy))
        self._last_x, self._last_y = cx, cy
        return cx, cy

    def move(self, x: int, y: int) -> None:
        if _HAS_PYAUTOGUI:
            pyautogui.moveTo(x, y, duration=0)

    def left_click(self) -> None:
        if _HAS_PYAUTOGUI:
            pyautogui.click()

    def right_click(self) -> None:
        if _HAS_PYAUTOGUI:
            pyautogui.rightClick()

    def double_click(self) -> None:
        if _HAS_PYAUTOGUI:
            pyautogui.doubleClick()

    def scroll(self, amount: int) -> None:
        if _HAS_PYAUTOGUI:
            pyautogui.scroll(amount)

    def set_precision_mode(self, on: bool) -> None:
        self._precision_mode = on

    # ── Private helpers ───────────────────────────────────────────────────────

    def _velocity_multiplier(self, norm_vel: float) -> float:
        """Smoothly interpolate multiplier between slow and fast zones."""
        if norm_vel <= SLOW_VEL:
            return SLOW_MULT
        if norm_vel >= FAST_VEL:
            return FAST_MULT
        t = (norm_vel - SLOW_VEL) / (FAST_VEL - SLOW_VEL)
        # Smooth cubic interpolation
        t = t * t * (3 - 2 * t)
        return SLOW_MULT + t * (FAST_MULT - SLOW_MULT)

    def _apply_edge_magnetism(self, x: float, y: float, mult: float) -> float:
        """Reduce speed near screen edges for easier edge targeting."""
        near_edge = (
            x < EDGE_DIST_PX or x > self._sw - EDGE_DIST_PX or
            y < EDGE_DIST_PX or y > self._sh - EDGE_DIST_PX
        )
        return mult * EDGE_MULT if near_edge else mult
