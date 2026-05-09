"""
core/drawing_shapes.py
Stateless pure functions for stroke shape detection and snapping.
No classes. No state. All functions are deterministic.
"""
from __future__ import annotations

import math
from typing import Sequence


# ── Type alias ────────────────────────────────────────────────────────────────
Point = tuple[float, float]


# ── Shape detection ───────────────────────────────────────────────────────────

def detect_shape_type(points: Sequence[Point]) -> str:
    """
    Classify a stroke into one of four shape types.

    Parameters
    ----------
    points : sequence of (x, y) stroke points

    Returns
    -------
    "circle" | "rectangle" | "line" | "freeform"
    """
    if len(points) < 4:
        return "freeform"

    # ── Line test (fast: check before circle/rect) ─────────────────────────
    total_len = compute_path_length(points)
    start_end = math.hypot(
        points[-1][0] - points[0][0],
        points[-1][1] - points[0][1],
    )
    dir_changes = compute_direction_changes(points, threshold=15.0)

    if dir_changes <= 3 and total_len > 0 and (start_end / total_len) > 0.60:
        return "line"

    # ── Circle test ────────────────────────────────────────────────────────
    cx = sum(p[0] for p in points) / len(points)
    cy = sum(p[1] for p in points) / len(points)
    distances = [math.hypot(p[0] - cx, p[1] - cy) for p in points]
    mean_r    = sum(distances) / len(distances)
    if mean_r < 1e-6:
        return "freeform"
    variance  = sum((d - mean_r) ** 2 for d in distances) / len(distances)
    rel_var   = math.sqrt(variance) / mean_r   # coefficient of variation

    close_loop = math.hypot(
        points[-1][0] - points[0][0],
        points[-1][1] - points[0][1],
    ) < 40.0

    if rel_var < 0.15 and close_loop:
        return "circle"

    # ── Rectangle test ────────────────────────────────────────────────────
    if _is_rectangle(points):
        return "rectangle"

    return "freeform"


def _is_rectangle(points: Sequence[Point]) -> bool:
    """Heuristic: most points lie near the 4 edges of the bounding box."""
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    width  = max_x - min_x
    height = max_y - min_y

    if width < 10 or height < 10:
        return False

    edge_tol = max(width, height) * 0.15   # 15% tolerance

    near_edge_count = 0
    for x, y in points:
        on_h = abs(y - min_y) < edge_tol or abs(y - max_y) < edge_tol
        on_v = abs(x - min_x) < edge_tol or abs(x - max_x) < edge_tol
        if on_h or on_v:
            near_edge_count += 1

    edge_fraction = near_edge_count / len(points)

    # Check for roughly four corners by sampling direction changes
    dir_changes = compute_direction_changes(points, threshold=20.0)
    has_four_corners = 3 <= dir_changes <= 6

    return edge_fraction > 0.75 and has_four_corners


# ── Shape snapping ────────────────────────────────────────────────────────────

def snap_to_circle(points: Sequence[Point]) -> list[Point]:
    """
    Fit a perfect circle to the stroke.
    Returns 360 evenly-spaced points around the fitted circle.
    """
    if not points:
        return []
    cx = sum(p[0] for p in points) / len(points)
    cy = sum(p[1] for p in points) / len(points)
    radius = sum(math.hypot(p[0] - cx, p[1] - cy) for p in points) / len(points)
    return [
        (cx + radius * math.cos(math.radians(deg)),
         cy + radius * math.sin(math.radians(deg)))
        for deg in range(360)
    ]


def snap_to_rect(points: Sequence[Point]) -> list[Point]:
    """
    Snap stroke to its bounding box.
    Returns 200 points evenly distributed around the 4 edges.
    """
    if not points:
        return []
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)

    N = 200
    per_edge = N // 4
    result: list[Point] = []

    # Top edge: left → right
    for i in range(per_edge):
        t = i / per_edge
        result.append((x0 + t * (x1 - x0), y0))
    # Right edge: top → bottom
    for i in range(per_edge):
        t = i / per_edge
        result.append((x1, y0 + t * (y1 - y0)))
    # Bottom edge: right → left
    for i in range(per_edge):
        t = i / per_edge
        result.append((x1 - t * (x1 - x0), y1))
    # Left edge: bottom → top
    for i in range(per_edge):
        t = i / per_edge
        result.append((x0, y1 - t * (y1 - y0)))

    return result


def snap_to_line(points: Sequence[Point]) -> list[Point]:
    """
    Snap stroke to a straight line from first to last point.
    Returns N evenly spaced points along the line.
    """
    if len(points) < 2:
        return list(points)
    p0, p1 = points[0], points[-1]
    total   = compute_path_length(points)
    # At least 50 points, or one per ~5 pixels
    N = max(50, int(total / 5))
    return [
        (p0[0] + (p1[0] - p0[0]) * i / (N - 1),
         p0[1] + (p1[1] - p0[1]) * i / (N - 1))
        for i in range(N)
    ]


# ── Frame overlay ─────────────────────────────────────────────────────────────

def flash_confirmation(frame, shape_type: str,
                        points: Sequence[Point]):
    """
    Draw the snapped shape in pure white on the frame.
    Called for 6 consecutive frames to provide snap confirmation flash.
    Modifies frame in-place and returns it.
    """
    import cv2
    import numpy as np

    if not points:
        return frame

    if shape_type == "circle":
        snapped = snap_to_circle(points)
    elif shape_type == "rectangle":
        snapped = snap_to_rect(points)
    elif shape_type == "line":
        snapped = snap_to_line(points)
    else:
        snapped = list(points)

    if len(snapped) < 2:
        return frame

    pts_arr = np.array([(int(x), int(y)) for x, y in snapped], dtype=np.int32)
    cv2.polylines(frame, [pts_arr], isClosed=(shape_type in ("circle", "rectangle")),
                  color=(255, 255, 255), thickness=3, lineType=cv2.LINE_AA)
    return frame


# ── Path utilities ────────────────────────────────────────────────────────────

def compute_path_length(points: Sequence[Point]) -> float:
    """Return total Euclidean length of the stroke."""
    total = 0.0
    for i in range(1, len(points)):
        total += math.hypot(
            points[i][0] - points[i - 1][0],
            points[i][1] - points[i - 1][1],
        )
    return total


def compute_direction_changes(points: Sequence[Point],
                               threshold: float = 15.0) -> int:
    """
    Count how many times the movement direction changes by more than
    threshold degrees between consecutive segments.
    """
    if len(points) < 3:
        return 0

    changes = 0
    prev_angle: float | None = None

    for i in range(1, len(points)):
        dx = points[i][0] - points[i - 1][0]
        dy = points[i][1] - points[i - 1][1]
        if abs(dx) < 1e-9 and abs(dy) < 1e-9:
            continue
        angle = math.degrees(math.atan2(dy, dx))

        if prev_angle is not None:
            diff = abs(angle - prev_angle)
            # Normalise to 0–180
            if diff > 180:
                diff = 360 - diff
            if diff > threshold:
                changes += 1

        prev_angle = angle

    return changes
