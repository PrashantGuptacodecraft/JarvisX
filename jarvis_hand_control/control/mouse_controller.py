"""
control/mouse_controller.py
Non-linear accelerated mouse control with edge magnetism and boundary clamping.
"""
from __future__ import annotations

import logging
import math
import time
from typing import Optional

log = logging.getLogger(__name__)

try:
    import pyautogui
    pyautogui.FAILSAFE = False
    pyautogui.PAUSE    = 0
    _PA = True
except ImportError:
    _PA = False
    log.warning("pyautogui not installed — mouse control disabled")

# Acceleration curve thresholds
_VEL_SLOW = 0.04    # normalised velocity below this → slow multiplier
_VEL_FAST = 0.15    # normalised velocity above this → fast multiplier
_MUL_SLOW = 0.55
_MUL_FAST = 2.20

# Edge magnetism
_EDGE_PX   = 40     # pixels from edge where magnetism applies
_EDGE_MULT = 0.30   # speed multiplier within edge zone

# Mode sensitivity overrides
_MODE_MULT = {
    "normal":       1.0,
    "precision":    0.55,
    "presentation": 1.90,
}


class MouseController:
    """
    Maps normalised landmark coordinates to screen-space cursor movement
    with non-linear velocity acceleration and edge magnetism.
    """

    def __init__(self, settings=None) -> None:
        self._sw: int = 1920
        self._sh: int = 1080
        self._mode:  str   = "normal"
        self._frozen: bool = False

        if _PA:
            self._sw, self._sh = pyautogui.size()
        if settings:
            self._sw = getattr(settings, "SCREEN_WIDTH",  self._sw)
            self._sh = getattr(settings, "SCREEN_HEIGHT", self._sh)

        self._prev_sx: float = self._sw / 2
        self._prev_sy: float = self._sh / 2
        self._prev_time: float = time.perf_counter()

    # ── Primary move ──────────────────────────────────────────────────────────

    def move(self, landmark_x: float, landmark_y: float,
             frame_w: int = 1280, frame_h: int = 720) -> tuple[int, int]:
        """
        Map a normalised landmark position [0, 1] to screen coordinates.
        Applies acceleration, edge magnetism, and boundary clamping.
        Returns the (screen_x, screen_y) that was moved to.
        """
        if self._frozen:
            return int(self._prev_sx), int(self._prev_sy)

        # Map landmark → raw screen coords (with 10% edge crop)
        raw_sx = self._remap(landmark_x, 0.10, 0.90, 0, self._sw)
        raw_sy = self._remap(landmark_y, 0.10, 0.85, 0, self._sh)

        # Delta since last frame
        dx = raw_sx - self._prev_sx
        dy = raw_sy - self._prev_sy

        # Velocity (normalised)
        now = time.perf_counter()
        dt  = max(now - self._prev_time, 1e-4)
        vel = math.hypot(dx / self._sw, dy / self._sh) / dt
        self._prev_time = now

        # Acceleration multiplier
        if vel < _VEL_SLOW:
            mul = _MUL_SLOW
        elif vel > _VEL_FAST:
            mul = _MUL_FAST
        else:
            t   = (vel - _VEL_SLOW) / (_VEL_FAST - _VEL_SLOW)
            mul = _MUL_SLOW + t * (_MUL_FAST - _MUL_SLOW)

        # Mode sensitivity override
        mul *= _MODE_MULT.get(self._mode, 1.0)

        # Edge magnetism: slow down near edges (per axis independently)
        sx_candidate = self._prev_sx + dx * mul
        sy_candidate = self._prev_sy + dy * mul

        if sx_candidate < _EDGE_PX or sx_candidate > self._sw - _EDGE_PX:
            dx *= _EDGE_MULT
        if sy_candidate < _EDGE_PX or sy_candidate > self._sh - _EDGE_PX:
            dy *= _EDGE_MULT

        # Apply final position
        final_sx = self._prev_sx + dx * mul
        final_sy = self._prev_sy + dy * mul

        # Boundary clamp
        final_sx = max(0.0, min(final_sx, self._sw - 1))
        final_sy = max(0.0, min(final_sy, self._sh - 1))

        self._prev_sx = final_sx
        self._prev_sy = final_sy

        if _PA:
            try:
                pyautogui.moveTo(int(final_sx), int(final_sy), _pause=False)
            except Exception as exc:
                log.debug("moveTo error: %s", exc)

        return int(final_sx), int(final_sy)

    # ── Clicks ────────────────────────────────────────────────────────────────

    def left_click(self) -> None:
        if not _PA: return
        try: pyautogui.click()
        except Exception as e: log.debug("left_click: %s", e)

    def right_click(self) -> None:
        if not _PA: return
        try: pyautogui.rightClick()
        except Exception as e: log.debug("right_click: %s", e)

    def double_click(self) -> None:
        if not _PA: return
        try: pyautogui.doubleClick()
        except Exception as e: log.debug("double_click: %s", e)

    def click_and_hold(self) -> None:
        if not _PA: return
        try: pyautogui.mouseDown()
        except Exception as e: log.debug("click_and_hold: %s", e)

    def release(self) -> None:
        if not _PA: return
        try: pyautogui.mouseUp()
        except Exception as e: log.debug("release: %s", e)

    def drag_to(self, x: int, y: int) -> None:
        """Drag from current position to (x, y) with left button held."""
        if not _PA: return
        try:
            pyautogui.dragTo(x, y, duration=0.10, button="left", _pause=False)
            self._prev_sx = float(x)
            self._prev_sy = float(y)
        except Exception as e: log.debug("drag_to: %s", e)

    # ── Scroll ────────────────────────────────────────────────────────────────

    def scroll(self, direction: str, amount: int = 3) -> None:
        """Scroll up (positive) or down (negative)."""
        if not _PA: return
        clicks = amount if direction == "up" else -amount
        try: pyautogui.scroll(clicks)
        except Exception as e: log.debug("scroll: %s", e)

    # ── Freeze ────────────────────────────────────────────────────────────────

    def freeze(self) -> None:
        """Freeze cursor in place (for freeze_cursor gesture)."""
        self._frozen = True

    def unfreeze(self) -> None:
        self._frozen = False

    # ── Queries ───────────────────────────────────────────────────────────────

    def get_current_position(self) -> tuple[int, int]:
        return int(self._prev_sx), int(self._prev_sy)

    def set_mode(self, mode: str) -> None:
        """Switch between 'normal', 'precision', 'presentation'."""
        if mode in _MODE_MULT:
            self._mode = mode
            log.info("Mouse mode: %s (×%.2f)", mode, _MODE_MULT[mode])

    def screen_size(self) -> tuple[int, int]:
        return self._sw, self._sh

    # ── Utilities ─────────────────────────────────────────────────────────────

    @staticmethod
    def _remap(v: float, src_lo: float, src_hi: float,
               dst_lo: float, dst_hi: float) -> float:
        if src_hi == src_lo:
            return dst_lo
        return dst_lo + (v - src_lo) / (src_hi - src_lo) * (dst_hi - dst_lo)
