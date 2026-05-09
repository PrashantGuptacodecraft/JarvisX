"""
core/gesture_buffer.py
Dual-layer gesture smoothing:
  Layer 1 — Majority-vote confirmation buffer (7 frames, 5/7 threshold)
  Layer 2 — EMA cursor smoothing with dead zone and velocity smoothing
"""
from __future__ import annotations

import logging
from collections import Counter, deque
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger(__name__)

_BUFFER_SIZE  = 7      # number of frames in confirmation window
_CONFIRM_NEED = 5      # votes required to confirm
_EMA_ALPHA    = 0.35   # cursor position EMA weight
_VEL_ALPHA    = 0.40   # velocity EMA weight
_DEAD_ZONE_DEFAULT = 10  # pixels


@dataclass
class BufferedGesture:
    """Output of GestureBuffer.update() when a gesture is confirmed."""
    gesture_name:  str
    confidence:    float
    smoothed_x:    float
    smoothed_y:    float
    velocity_x:    float
    velocity_y:    float
    raw_x:         float
    raw_y:         float
    frame_count:   int


class GestureBuffer:
    """
    Dual-layer gesture + cursor smoother.

    Layer 1 (Gesture Confirmation):
        Maintains a 7-frame rolling buffer.
        A gesture is confirmed only if the same name appears in ≥5 frames.
        A different gesture immediately resets the buffer.
        Confidence is the average across matching frames.

    Layer 2 (Coordinate Smoothing):
        EMA with configurable alpha.
        Dead zone suppresses updates below DEAD_ZONE_PX in both axes.
        Velocity is separately EMA-smoothed with alpha=0.4.
    """

    def __init__(self, dead_zone_px: int = _DEAD_ZONE_DEFAULT,
                 smooth_alpha: float = _EMA_ALPHA) -> None:
        self._dead_zone   = dead_zone_px
        self._alpha       = smooth_alpha

        # Layer 1
        self._gesture_buf: deque[tuple[str, float]] = deque(maxlen=_BUFFER_SIZE)
        self._last_confirmed: Optional[str] = None
        self._confirmed_frames: int = 0

        # Layer 2 — cursor EMA state
        self._sx: float = 0.0
        self._sy: float = 0.0
        self._svx: float = 0.0
        self._svy: float = 0.0
        self._prev_x: float = 0.0
        self._prev_y: float = 0.0
        self._initialized: bool = False

        self._last_output: Optional[BufferedGesture] = None

    # ── Primary update ────────────────────────────────────────────────────────

    def update(self, gesture_result) -> Optional[BufferedGesture]:
        """
        Accept a GestureResult from GestureClassifier.
        Returns BufferedGesture when gesture is confirmed, else None.

        Parameters
        ----------
        gesture_result : GestureResult (has .gesture_name, .confidence, .cursor_x, .cursor_y)
        """
        name = gesture_result.gesture_name
        conf = gesture_result.confidence
        rx   = gesture_result.cursor_x
        ry   = gesture_result.cursor_y

        # ── Layer 1: gesture confirmation ─────────────────────────────────────
        # If gesture changed, reset buffer immediately
        if self._gesture_buf and self._gesture_buf[-1][0] != name:
            self._gesture_buf.clear()
            self._last_confirmed = None
            self._confirmed_frames = 0

        self._gesture_buf.append((name, conf))
        confirmed_name, avg_conf = self._vote()

        # ── Layer 2: coordinate smoothing (always) ────────────────────────────
        sx, sy, vx, vy = self._smooth_cursor(rx, ry)

        if confirmed_name is None:
            return None

        self._confirmed_frames += 1
        output = BufferedGesture(
            gesture_name  = confirmed_name,
            confidence    = round(avg_conf, 4),
            smoothed_x    = sx,
            smoothed_y    = sy,
            velocity_x    = vx,
            velocity_y    = vy,
            raw_x         = rx,
            raw_y         = ry,
            frame_count   = self._confirmed_frames,
        )
        self._last_output = output
        return output

    # ── State queries ─────────────────────────────────────────────────────────

    def get_smoothed_position(self) -> tuple[float, float]:
        """Return latest EMA-smoothed (x, y)."""
        return self._sx, self._sy

    def reset(self) -> None:
        """Clear all buffers and EMA state."""
        self._gesture_buf.clear()
        self._last_confirmed    = None
        self._confirmed_frames  = 0
        self._initialized       = False
        self._sx = self._sy = 0.0
        self._svx = self._svy = 0.0
        self._last_output = None
        log.debug("GestureBuffer reset")

    def get_current_confidence(self) -> float:
        """Return the averaged confidence of the current vote window."""
        _, conf = self._vote()
        return conf

    def is_gesture_stable(self) -> bool:
        """True if the same gesture has appeared in ≥5 of the last 7 frames."""
        name, _ = self._vote()
        return name is not None

    # ── Internal ──────────────────────────────────────────────────────────────

    def _vote(self) -> tuple[Optional[str], float]:
        """
        Majority vote over the current buffer.
        Returns (confirmed_name, avg_confidence) or (None, 0.0).
        """
        if len(self._gesture_buf) < _BUFFER_SIZE:
            return None, 0.0

        counts: Counter = Counter()
        conf_sums: dict[str, float] = {}

        for g_name, g_conf in self._gesture_buf:
            counts[g_name] += 1
            conf_sums[g_name] = conf_sums.get(g_name, 0.0) + g_conf

        top_name, top_count = counts.most_common(1)[0]
        if top_count >= _CONFIRM_NEED:
            avg_conf = conf_sums[top_name] / top_count
            return top_name, avg_conf

        return None, 0.0

    def _smooth_cursor(self, rx: float, ry: float) -> tuple[float, float, float, float]:
        """
        Apply EMA + dead zone + velocity smoothing.
        Returns (smoothed_x, smoothed_y, velocity_x, velocity_y).
        """
        if not self._initialized:
            self._sx = rx
            self._sy = ry
            self._prev_x = rx
            self._prev_y = ry
            self._initialized = True
            return rx, ry, 0.0, 0.0

        # EMA update
        new_sx = self._alpha * rx + (1.0 - self._alpha) * self._sx
        new_sy = self._alpha * ry + (1.0 - self._alpha) * self._sy

        # Dead zone: if movement < dead_zone in BOTH axes, freeze
        dx = abs(new_sx - self._sx) * 1280.0   # approx px
        dy = abs(new_sy - self._sy) * 720.0
        if dx < self._dead_zone and dy < self._dead_zone:
            new_sx = self._sx
            new_sy = self._sy

        # Raw velocity (frame delta)
        raw_vx = rx - self._prev_x
        raw_vy = ry - self._prev_y

        # EMA velocity smoothing
        self._svx = _VEL_ALPHA * raw_vx + (1.0 - _VEL_ALPHA) * self._svx
        self._svy = _VEL_ALPHA * raw_vy + (1.0 - _VEL_ALPHA) * self._svy

        self._prev_x = rx
        self._prev_y = ry
        self._sx     = new_sx
        self._sy     = new_sy

        return new_sx, new_sy, self._svx, self._svy
