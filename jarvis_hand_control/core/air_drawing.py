"""
core/air_drawing.py
AirDrawingEngine — multi-layer, multi-brush air drawing with shape snapping,
stroke replay, and animated entry/exit transitions.
"""
from __future__ import annotations

import json
import logging
import os
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from core.drawing_shapes import (
    detect_shape_type, snap_to_circle, snap_to_rect,
    snap_to_line, flash_confirmation,
)

log = logging.getLogger(__name__)

# ── Paths ─────────────────────────────────────────────────────────────────────
_BASE      = Path(__file__).resolve().parent.parent
_DRAW_DIR  = _BASE / "drawings"
_DRAW_DIR.mkdir(parents=True, exist_ok=True)

# ── Palette (BGR) ─────────────────────────────────────────────────────────────
DEFAULT_PALETTE = [
    (0,   255, 100),   # green
    (0,   200, 255),   # cyan
    (255, 100,   0),   # blue
    (180,   0, 255),   # violet
    (0,   100, 255),   # orange
    (0,     0, 255),   # red
    (255, 255, 255),   # white
    (0,   220, 255),   # yellow
]

BRUSH_MODES  = ["pen", "marker", "spray", "eraser"]
DRAWING_HOLD = 0.45   # seconds index must be extended before drawing activates
EXIT_HOLD    = 0.60   # seconds fist held to trigger exit+save
SNAP_PAUSE   = 0.70   # seconds pause before shape snapping fires


# ── Data containers ───────────────────────────────────────────────────────────

@dataclass
class StrokePoint:
    x:          float
    y:          float
    z:          float
    timestamp:  float
    pressure:   float   # derived from z: 0.0–1.0
    brush_mode: str


@dataclass
class Stroke:
    points:    list[StrokePoint] = field(default_factory=list)
    color:     tuple             = (0, 255, 100)
    brush_mode: str              = "pen"


@dataclass
class Layer:
    strokes:  list[Stroke] = field(default_factory=list)
    visible:  bool         = True
    opacity:  float        = 1.0
    name:     str          = "Layer 1"


# ── Engine ────────────────────────────────────────────────────────────────────

class AirDrawingEngine:
    """
    Full air-drawing engine with layers, brushes, shape snap, and replay.
    Call update(frame, hand_data, gesture_result) every frame.
    """

    def __init__(self, settings=None) -> None:
        # Layer state
        self.layers:              list[Layer] = [Layer(name="Layer 1")]
        self.active_layer_index:  int         = 0
        self.current_stroke:      list[StrokePoint] = []

        # Drawing state
        self.is_drawing:          bool  = False
        self.brush_mode:          str   = "pen"
        self.active_color:        tuple = DEFAULT_PALETTE[0]
        self.color_palette:       list  = DEFAULT_PALETTE.copy()
        self.color_index:         int   = 0

        # Canvas (initialised on first frame)
        self._overlay:            Optional[np.ndarray] = None
        self._frame_h:            int  = 720
        self._frame_w:            int  = 1280

        # Shape snapping
        self._snap_enabled:       bool  = True
        self._last_point_time:    float = 0.0
        self._flash_frames:       int   = 0
        self._flash_shape:        str   = "freeform"
        self._flash_points:       list  = []

        # Entry animation
        self._entry_anim_end:     float = 0.0
        self._entry_cx:           int   = 0
        self._entry_cy:           int   = 0

        # Exit / save state
        self._fist_hold_start:    Optional[float] = None
        self._saving:             bool  = False

        # Replay buffer: list of {x, y, z, t, color, brush}
        self._replay_events:      list  = []
        self._session_start:      float = time.time()

    # ── Main update ───────────────────────────────────────────────────────────

    def update(self, frame: np.ndarray, hand_data: dict,
               gesture_result: dict) -> np.ndarray:
        """
        Called every frame. Composites drawing overlay onto frame.
        Returns the annotated frame.
        """
        h, w = frame.shape[:2]
        self._frame_h, self._frame_w = h, w

        # Initialise overlay canvas
        if self._overlay is None or self._overlay.shape[:2] != (h, w):
            self._overlay = np.zeros((h, w, 3), dtype=np.uint8)

        gesture  = gesture_result.get("name", "none")
        lm       = hand_data.get("landmarks")     # np.ndarray (21, 3) or None
        now      = time.time()

        # ── Entry animation ────────────────────────────────────────────────
        if now < self._entry_anim_end and lm is not None:
            tip_px = int(lm[8, 0] * w)
            tip_py = int(lm[8, 1] * h)
            elapsed   = now - (self._entry_anim_end - 0.30)
            radius    = int(elapsed / 0.30 * 50)
            alpha_val = max(0, 255 - int(elapsed / 0.30 * 255))
            ring_col  = (0, int(alpha_val * 0.8), alpha_val)
            cv2.circle(frame, (tip_px, tip_py), radius, ring_col, 2, cv2.LINE_AA)

        # ── Eraser / mode gestures ─────────────────────────────────────────
        if gesture == "rock_sign":
            self._cycle_brush()
        elif gesture == "right_click":
            self._cycle_color()

        # ── Exit: fist held EXIT_HOLD seconds ─────────────────────────────
        if gesture == "fist":
            if self._fist_hold_start is None:
                self._fist_hold_start = now
            held = now - self._fist_hold_start
            self._draw_exit_countdown(frame, held, w, h)
            if held >= EXIT_HOLD:
                self._fist_hold_start = None
                self.save_drawing(frame)
                self.save_replay()
                self._overlay[:] = 0
                self.layers = [Layer(name="Layer 1")]
                self.current_stroke = []
                self.is_drawing = False
                self._replay_events = []
        else:
            self._fist_hold_start = None

        # ── Drawing: drawing_mode gesture + index landmark ─────────────────
        if gesture == "drawing_mode" and lm is not None:
            if not self.is_drawing:
                self.is_drawing = True
                self._entry_anim_end = now + 0.30
                self._entry_cx = int(lm[8, 0] * w)
                self._entry_cy = int(lm[8, 1] * h)

            tip_px = int(lm[8, 0] * w)
            tip_py = int(lm[8, 1] * h)
            z_raw  = float(lm[8, 2])   # depth: 0 = close, negative = behind
            pressure = min(1.0, max(0.0, -z_raw / 0.5))

            sp = StrokePoint(
                x=lm[8, 0], y=lm[8, 1], z=z_raw,
                timestamp=now - self._session_start,
                pressure=pressure, brush_mode=self.brush_mode,
            )
            self.current_stroke.append(sp)
            self._last_point_time = now

            # Replay log
            self._replay_events.append({
                "x": lm[8, 0], "y": lm[8, 1], "z": z_raw,
                "t": round(now - self._session_start, 4),
                "color": list(self.active_color),
                "brush": self.brush_mode,
            })

            # Render stroke point to overlay
            self._render_point(self._overlay, tip_px, tip_py, pressure)

            # Draw crosshair cursor
            cv2.drawMarker(frame, (tip_px, tip_py), self.active_color,
                           cv2.MARKER_CROSS, 18, 2, cv2.LINE_AA)

        elif self.is_drawing and gesture != "drawing_mode":
            # Pen lifted — finalise stroke
            self._finalise_stroke()
            self.is_drawing = False

        # ── Shape snapping ─────────────────────────────────────────────────
        if (self._snap_enabled and self.current_stroke
                and now - self._last_point_time > SNAP_PAUSE
                and not self.is_drawing):
            raw_pts = [(sp.x * w, sp.y * h) for sp in self.current_stroke]
            shape   = detect_shape_type(raw_pts)
            if shape != "freeform":
                self._apply_snap(shape, raw_pts)
            self.current_stroke = []

        # ── Flash confirmation ─────────────────────────────────────────────
        if self._flash_frames > 0:
            frame = flash_confirmation(frame, self._flash_shape, self._flash_points)
            self._flash_frames -= 1

        # ── Composite overlay onto frame ───────────────────────────────────
        mask = cv2.cvtColor(self._overlay, cv2.COLOR_BGR2GRAY)
        _, mask = cv2.threshold(mask, 1, 255, cv2.THRESH_BINARY)
        frame[mask > 0] = self._overlay[mask > 0]

        # ── HUD: brush mode + color swatch ────────────────────────────────
        self._draw_hud(frame, w, h)

        return frame

    # ── Stroke rendering ──────────────────────────────────────────────────────

    def _render_point(self, canvas: np.ndarray, px: int, py: int,
                      pressure: float) -> None:
        """Render one point on the drawing canvas according to brush_mode."""
        col = self.active_color

        if self.brush_mode == "pen":
            thickness = int(2 + pressure * 10)
            if len(self.current_stroke) >= 2:
                prev = self.current_stroke[-2]
                ppx  = int(prev.x * self._frame_w)
                ppy  = int(prev.y * self._frame_h)
                cv2.line(canvas, (ppx, ppy), (px, py), col, thickness, cv2.LINE_AA)

        elif self.brush_mode == "marker":
            thickness = int(8 + pressure * 10)
            tmp = canvas.copy()
            if len(self.current_stroke) >= 2:
                prev = self.current_stroke[-2]
                ppx  = int(prev.x * self._frame_w)
                ppy  = int(prev.y * self._frame_h)
                cv2.line(tmp, (ppx, ppy), (px, py), col, thickness, cv2.LINE_AA)
            cv2.addWeighted(tmp, 0.85, canvas, 0.15, 0, canvas)

        elif self.brush_mode == "spray":
            n_drops  = 12
            radius   = 20
            xs = np.random.normal(px, radius / 2.5, n_drops).astype(int)
            ys = np.random.normal(py, radius / 2.5, n_drops).astype(int)
            for sx, sy in zip(xs, ys):
                if 0 <= sx < self._frame_w and 0 <= sy < self._frame_h:
                    cv2.circle(canvas, (sx, sy), 1, col, -1)

        elif self.brush_mode == "eraser":
            cv2.circle(canvas, (px, py), 30, (0, 0, 0), -1)

    def _finalise_stroke(self) -> None:
        """Commit current_stroke to active layer."""
        if not self.current_stroke:
            return
        layer = self._active_layer()
        stroke = Stroke(
            points=list(self.current_stroke),
            color=self.active_color,
            brush_mode=self.brush_mode,
        )
        layer.strokes.append(stroke)

    def _apply_snap(self, shape: str, raw_pts: list) -> None:
        """Replace last stroke on canvas with snapped version."""
        if shape == "circle":
            snapped = snap_to_circle(raw_pts)
        elif shape == "rectangle":
            snapped = snap_to_rect(raw_pts)
        else:
            snapped = snap_to_line(raw_pts)

        # Redraw snapped stroke on overlay
        pts_arr = np.array([(int(x), int(y)) for x, y in snapped], dtype=np.int32)
        cv2.polylines(self._overlay, [pts_arr],
                      isClosed=(shape in ("circle", "rectangle")),
                      color=self.active_color, thickness=3, lineType=cv2.LINE_AA)

        # Trigger flash
        self._flash_frames  = 6
        self._flash_shape   = shape
        self._flash_points  = snapped
        log.info("Shape snapped: %s", shape)

    # ── Save / Replay ─────────────────────────────────────────────────────────

    def save_drawing(self, frame: np.ndarray) -> str:
        """Save current frame with overlay as PNG. Returns filepath."""
        ts   = time.strftime("%Y%m%d_%H%M%S")
        path = str(_DRAW_DIR / f"drawing_{ts}.png")
        cv2.imwrite(path, frame)
        log.info("Drawing saved: %s", path)
        return path

    def save_replay(self) -> str:
        """Save stroke events as JSON for replay. Returns filepath."""
        ts   = time.strftime("%Y%m%d_%H%M%S")
        path = str(_DRAW_DIR / f"replay_{ts}.json")
        data = {
            "version":  1,
            "frame_w":  self._frame_w,
            "frame_h":  self._frame_h,
            "palette":  [list(c) for c in self.color_palette],
            "events":   self._replay_events,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        log.info("Replay saved: %s", path)
        return path

    def replay(self, json_path: str) -> None:
        """
        Read a replay JSON and redraw strokes on the overlay at original timing.
        Blocking — run in a thread if called at runtime.
        """
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)

        if self._overlay is None:
            self._overlay = np.zeros((self._frame_h, self._frame_w, 3), dtype=np.uint8)

        events = data.get("events", [])
        t0 = time.time()
        prev_event_t = 0.0

        for ev in events:
            # Wait real-time
            wait = ev["t"] - prev_event_t
            if wait > 0:
                time.sleep(wait)
            prev_event_t = ev["t"]

            px  = int(ev["x"] * self._frame_w)
            py  = int(ev["y"] * self._frame_h)
            col = tuple(int(c) for c in ev["color"])
            bm  = ev.get("brush", "pen")

            # Replay brush stroke on overlay
            if bm == "pen":
                cv2.circle(self._overlay, (px, py), 3, col, -1, cv2.LINE_AA)
            elif bm == "spray":
                for _ in range(8):
                    sx = px + int(np.random.normal(0, 8))
                    sy = py + int(np.random.normal(0, 8))
                    if 0 <= sx < self._frame_w and 0 <= sy < self._frame_h:
                        cv2.circle(self._overlay, (sx, sy), 1, col, -1)

        log.info("Replay complete: %s", json_path)

    # ── Layer management ──────────────────────────────────────────────────────

    def add_layer(self) -> None:
        n = len(self.layers) + 1
        self.layers.append(Layer(name=f"Layer {n}"))
        self.active_layer_index = len(self.layers) - 1
        log.info("Added layer %d", self.active_layer_index)

    def layer_up(self) -> None:
        self.active_layer_index = min(
            self.active_layer_index + 1, len(self.layers) - 1
        )

    def layer_down(self) -> None:
        self.active_layer_index = max(self.active_layer_index - 1, 0)

    def merge_all_layers(self) -> None:
        """Flatten all layers into a single layer (keep overlay canvas)."""
        merged = Layer(name="Merged")
        for layer in self.layers:
            if layer.visible:
                merged.strokes.extend(layer.strokes)
        self.layers = [merged]
        self.active_layer_index = 0
        log.info("All layers merged")

    # ── HUD ───────────────────────────────────────────────────────────────────

    def _draw_hud(self, frame: np.ndarray, w: int, h: int) -> None:
        col = self.active_color
        # Color swatch top-right
        cv2.rectangle(frame, (w - 40, 8), (w - 8, 36), col, -1)
        cv2.rectangle(frame, (w - 40, 8), (w - 8, 36), (255, 255, 255), 1)
        # Brush mode label
        cv2.putText(frame, self.brush_mode.upper(), (w - 110, 58),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, col, 1, cv2.LINE_AA)
        # Layer indicator
        lbl = f"L{self.active_layer_index + 1}/{len(self.layers)}"
        cv2.putText(frame, lbl, (w - 110, 76),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, (180, 180, 180), 1, cv2.LINE_AA)

    def _draw_exit_countdown(self, frame: np.ndarray,
                              held: float, w: int, h: int) -> None:
        """Draw a clock-fill countdown circle when exit gesture is held."""
        fraction = min(1.0, held / EXIT_HOLD)
        angle    = int(fraction * 360)
        cx, cy   = w // 2, h // 2
        axes     = (45, 45)
        cv2.ellipse(frame, (cx, cy), axes, -90, 0, angle,
                    (0, 0, 255), 5, cv2.LINE_AA)
        cv2.putText(frame, "SAVING...", (cx - 52, cy + 70),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2, cv2.LINE_AA)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _active_layer(self) -> Layer:
        return self.layers[self.active_layer_index]

    def _cycle_brush(self) -> None:
        idx = (BRUSH_MODES.index(self.brush_mode) + 1) % len(BRUSH_MODES)
        self.brush_mode = BRUSH_MODES[idx]
        log.info("Brush mode: %s", self.brush_mode)

    def _cycle_color(self) -> None:
        self.color_index  = (self.color_index + 1) % len(self.color_palette)
        self.active_color = self.color_palette[self.color_index]
