"""
ui/ar_effects.py
Pure functions for AR visual effects.
No classes. No state. All functions are deterministic given the same inputs
(except frame_count-driven animations which are intentionally time-varying).
"""
from __future__ import annotations

import math
import random

import cv2
import numpy as np


# ── Circuit pattern ───────────────────────────────────────────────────────────

def generate_circuit_pattern(width: int, height: int) -> np.ndarray:
    """
    Generate a static tiling circuit-board pattern as a BGR numpy array.

    Algorithm:
      - Draw horizontal and vertical line segments on a grid with spacing 32px
      - Add random T-branches and nodes at intersections
    Returns uint8 BGR image of shape (height, width, 3).
    """
    canvas = np.zeros((height, width, 3), dtype=np.uint8)
    grid   = 32
    rng    = random.Random(42)   # deterministic seed for stable pattern

    line_col = (0, 60, 0)         # dark green circuit colour
    node_col = (0, 120, 40)

    # Horizontal lines
    for gy in range(0, height, grid):
        x = 0
        while x < width:
            seg_len = rng.randint(2, 6) * grid
            end_x   = min(x + seg_len, width - 1)
            cv2.line(canvas, (x, gy), (end_x, gy), line_col, 1)
            x = end_x + rng.randint(0, 2) * grid

    # Vertical lines
    for gx in range(0, width, grid):
        y = 0
        while y < height:
            seg_len = rng.randint(2, 5) * grid
            end_y   = min(y + seg_len, height - 1)
            cv2.line(canvas, (gx, y), (gx, end_y), line_col, 1)
            y = end_y + rng.randint(0, 2) * grid

    # Nodes at intersections (random subset)
    for gy in range(0, height, grid):
        for gx in range(0, width, grid):
            if rng.random() < 0.25:
                cv2.circle(canvas, (gx, gy), 2, node_col, -1)

    return canvas


def scroll_circuit_pattern(pattern: np.ndarray,
                            frame_count: int,
                            speed: int = 1) -> np.ndarray:
    """
    Scroll the circuit pattern horizontally using numpy.roll.
    Offset = (frame_count * speed) % pattern_width.
    Returns the scrolled pattern as a new array.
    """
    offset = (frame_count * speed) % pattern.shape[1]
    return np.roll(pattern, -offset, axis=1)


# ── Pulse ring ────────────────────────────────────────────────────────────────

def draw_pulse_ring(frame: np.ndarray, center: tuple[int, int],
                    frame_count: int,
                    color: tuple = (255, 255, 0),
                    max_radius: int = 60,
                    duration: int = 12) -> np.ndarray:
    """
    Draw an expanding, fading circle at center.
    progress = (frame_count % duration) / duration
    radius   = 30 → max_radius
    alpha    = 1.0 → 0.0
    """
    progress = (frame_count % duration) / max(duration, 1)
    radius   = int(30 + progress * (max_radius - 30))
    alpha    = max(0.0, 1.0 - progress)
    col      = tuple(int(c * alpha) for c in color)

    if radius > 0 and alpha > 0.01:
        overlay = frame.copy()
        cv2.circle(overlay, center, radius, col, 2, cv2.LINE_AA)
        cv2.addWeighted(overlay, alpha, frame, 1.0 - alpha, 0, frame)

    return frame


# ── Waveform bars ─────────────────────────────────────────────────────────────

def draw_waveform_bars(frame: np.ndarray,
                        amplitude_array: np.ndarray,
                        bar_count: int = 32,
                        max_height: int = 60) -> np.ndarray:
    """
    Draw a waveform bar graph along the bottom edge of the frame.

    amplitude_array : 1-D float array, values 0.0–1.0, length >= bar_count
    bar_count       : number of bars to draw
    max_height      : maximum bar height in pixels
    """
    h, w = frame.shape[:2]
    bar_w = 4
    gap   = 2
    total_w = bar_count * (bar_w + gap)
    x0    = (w - total_w) // 2
    y_base = h - 4

    # Resample amplitude to bar_count values
    if len(amplitude_array) != bar_count:
        indices = np.linspace(0, len(amplitude_array) - 1, bar_count).astype(int)
        amps    = amplitude_array[indices]
    else:
        amps = amplitude_array

    for i, amp in enumerate(amps):
        amp_clamped = float(np.clip(amp, 0.0, 1.0))
        bar_h       = max(2, int(amp_clamped * max_height))
        bx          = x0 + i * (bar_w + gap)

        # Color: green → yellow → red with amplitude
        if amp_clamped < 0.5:
            g = 255
            r = int(amp_clamped * 2 * 255)
        else:
            r = 255
            g = int((1.0 - (amp_clamped - 0.5) * 2) * 255)
        col = (0, g, r)

        cv2.rectangle(frame,
                       (bx,          y_base - bar_h),
                       (bx + bar_w,  y_base),
                       col, -1)

    return frame


# ── Glow effect ───────────────────────────────────────────────────────────────

def apply_glow_effect(frame: np.ndarray,
                       stroke_layer: np.ndarray,
                       blur_radius: int = 15) -> np.ndarray:
    """
    Blur stroke_layer and blend at 60% opacity underneath the crisp strokes,
    then composite the result onto frame.

    stroke_layer : BGR array same shape as frame, black where no stroke
    blur_radius  : GaussianBlur kernel size (odd)
    """
    k = blur_radius | 1   # ensure odd
    blurred = cv2.GaussianBlur(stroke_layer, (k, k), 0)

    # Composite: blurred (60%) under crisp strokes
    glow_layer = cv2.addWeighted(blurred, 0.60, stroke_layer, 1.0, 0)

    # Overlay where strokes exist
    mask = cv2.cvtColor(glow_layer, cv2.COLOR_BGR2GRAY)
    _, mask = cv2.threshold(mask, 1, 255, cv2.THRESH_BINARY)
    frame[mask > 0] = np.clip(
        frame[mask > 0].astype(np.int32) + glow_layer[mask > 0].astype(np.int32),
        0, 255
    ).astype(np.uint8)

    return frame


# ── Name badge ────────────────────────────────────────────────────────────────

def draw_name_badge(frame: np.ndarray,
                    text: str,
                    position: str = "bottom_left",
                    frame_count: int = 0) -> np.ndarray:
    """
    Draw a JARVIS-style name badge with a scanning line animation.

    position : "bottom_left" | "bottom_right" | "top_left" | "top_right"
    """
    h, w = frame.shape[:2]

    (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
    pad   = 8
    bw    = tw + pad * 2
    bh    = th + pad * 2

    # Position
    if position == "bottom_left":
        x0, y0 = 12, h - bh - 12
    elif position == "bottom_right":
        x0, y0 = w - bw - 12, h - bh - 12
    elif position == "top_right":
        x0, y0 = w - bw - 12, 12
    else:
        x0, y0 = 12, 12

    # Dark background
    overlay = frame.copy()
    cv2.rectangle(overlay, (x0, y0), (x0 + bw, y0 + bh), (10, 10, 10), -1)
    cv2.addWeighted(overlay, 0.75, frame, 0.25, 0, frame)

    # Cyan border
    cv2.rectangle(frame, (x0, y0), (x0 + bw, y0 + bh), (255, 255, 0), 1)

    # Text
    cv2.putText(frame, text, (x0 + pad, y0 + pad + th),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 0), 1, cv2.LINE_AA)

    # Scanning line inside badge
    scan_offset = (frame_count * 2) % bh
    sy = y0 + scan_offset
    if y0 <= sy <= y0 + bh:
        scan_overlay = frame.copy()
        cv2.line(scan_overlay, (x0, sy), (x0 + bw, sy), (255, 255, 0), 1)
        cv2.addWeighted(scan_overlay, 0.35, frame, 0.65, 0, frame)

    return frame


# ── Scanning line overlay ────────────────────────────────────────────────────

def draw_scanning_line_overlay(frame: np.ndarray,
                                frame_count: int,
                                speed: int = 4) -> np.ndarray:
    """
    Full-width horizontal cyan scan line at 20% opacity, moving top→bottom.
    Resets to top when reaching the bottom.
    """
    h, w  = frame.shape[:2]
    y     = (frame_count * speed) % h
    overlay = frame.copy()
    cv2.line(overlay, (0, y), (w, y), (255, 255, 0), 1)
    cv2.addWeighted(overlay, 0.20, frame, 0.80, 0, frame)
    return frame
