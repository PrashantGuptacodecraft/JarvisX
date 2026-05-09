"""
core/finger_analyzer.py
Joint-angle vector analysis using numpy dot products and arccos.
NEVER uses Y-coordinate comparison — fully geometry-based.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

import numpy as np

log = logging.getLogger(__name__)

# ── Landmark index constants ──────────────────────────────────────────────────
WRIST          = 0
THUMB_CMC      = 1;  THUMB_MCP  = 2;  THUMB_IP   = 3;  THUMB_TIP  = 4
INDEX_MCP      = 5;  INDEX_PIP  = 6;  INDEX_DIP  = 7;  INDEX_TIP  = 8
MIDDLE_MCP     = 9;  MIDDLE_PIP = 10; MIDDLE_DIP = 11; MIDDLE_TIP = 12
RING_MCP       = 13; RING_PIP   = 14; RING_DIP   = 15; RING_TIP   = 16
PINKY_MCP      = 17; PINKY_PIP  = 18; PINKY_DIP  = 19; PINKY_TIP  = 20

# (proximal_joint, middle_joint, distal_joint) for angle measurement
_FINGER_TRIPLETS: dict[str, tuple[int, int, int]] = {
    "index":  (INDEX_MCP,  INDEX_PIP,  INDEX_DIP),
    "middle": (MIDDLE_MCP, MIDDLE_PIP, MIDDLE_DIP),
    "ring":   (RING_MCP,   RING_PIP,   RING_DIP),
    "pinky":  (PINKY_MCP,  PINKY_PIP,  PINKY_DIP),
}
_THUMB_TRIPLET = (THUMB_CMC, THUMB_MCP, THUMB_IP)

# Angle thresholds (degrees)
EXTENDED_THRESH_FINGER = 35.0    # angle < 35° → EXTENDED
BENT_THRESH_FINGER     = 65.0    # angle > 65° → BENT
EXTENDED_THRESH_THUMB  = 45.0
BENT_THRESH_THUMB      = 75.0


class FingerStatus(Enum):
    EXTENDED = auto()
    BENT     = auto()
    PARTIAL  = auto()


@dataclass
class FingerState:
    thumb:  FingerStatus
    index:  FingerStatus
    middle: FingerStatus
    ring:   FingerStatus
    pinky:  FingerStatus
    # Convenience counts
    open_count:       int = 0
    closed_count:     int = 0
    extended_fingers: list[str] = field(default_factory=list)
    bent_fingers:     list[str] = field(default_factory=list)

    def is_extended(self, finger: str) -> bool:
        return getattr(self, finger) == FingerStatus.EXTENDED

    def is_bent(self, finger: str) -> bool:
        return getattr(self, finger) == FingerStatus.BENT


def _vec(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """3-D vector from landmark a to landmark b."""
    return b - a


def _angle_between(v1: np.ndarray, v2: np.ndarray) -> float:
    """Angle in degrees between two 3-D vectors using dot product."""
    n1 = np.linalg.norm(v1)
    n2 = np.linalg.norm(v2)
    if n1 < 1e-9 or n2 < 1e-9:
        return 0.0
    cos_a = np.dot(v1, v2) / (n1 * n2)
    cos_a = float(np.clip(cos_a, -1.0, 1.0))
    return math.degrees(math.acos(cos_a))


def _finger_angle(lm: np.ndarray, prox: int, mid: int, dist: int) -> float:
    """
    Compute the bend angle at the middle joint (mid) of a finger triplet.
    Returns degrees — small = straight, large = curled.
    """
    v1 = _vec(lm[prox], lm[mid])
    v2 = _vec(lm[mid],  lm[dist])
    return _angle_between(v1, v2)


def _classify_finger(angle: float, ext_thresh: float,
                     bent_thresh: float) -> FingerStatus:
    if angle < ext_thresh:
        return FingerStatus.EXTENDED
    if angle > bent_thresh:
        return FingerStatus.BENT
    return FingerStatus.PARTIAL


class FingerAnalyzer:
    """
    Analyses a (21, 3) landmark array and returns a FingerState.
    All geometry computed via dot-product angle — no Y-axis comparisons.
    Thread-safe: no mutable state.
    """

    def analyze(self, landmarks: np.ndarray) -> FingerState:
        """
        Parameters
        ----------
        landmarks : np.ndarray  shape (21, 3), normalised xyz

        Returns
        -------
        FingerState
        """
        if landmarks is None or landmarks.shape != (21, 3):
            # Return neutral state gracefully
            return FingerState(
                thumb=FingerStatus.PARTIAL, index=FingerStatus.PARTIAL,
                middle=FingerStatus.PARTIAL, ring=FingerStatus.PARTIAL,
                pinky=FingerStatus.PARTIAL,
            )

        lm = landmarks

        # Thumb
        thumb_ang  = _finger_angle(lm, *_THUMB_TRIPLET)
        thumb_st   = _classify_finger(thumb_ang, EXTENDED_THRESH_THUMB, BENT_THRESH_THUMB)

        # Four fingers
        finger_states: dict[str, FingerStatus] = {}
        for name, triplet in _FINGER_TRIPLETS.items():
            ang = _finger_angle(lm, *triplet)
            finger_states[name] = _classify_finger(
                ang, EXTENDED_THRESH_FINGER, BENT_THRESH_FINGER
            )

        all_states = {"thumb": thumb_st, **finger_states}
        extended   = [n for n, s in all_states.items() if s == FingerStatus.EXTENDED]
        bent       = [n for n, s in all_states.items() if s == FingerStatus.BENT]

        return FingerState(
            thumb  = thumb_st,
            index  = finger_states["index"],
            middle = finger_states["middle"],
            ring   = finger_states["ring"],
            pinky  = finger_states["pinky"],
            open_count       = len(extended),
            closed_count     = len(bent),
            extended_fingers = extended,
            bent_fingers     = bent,
        )

    def get_finger_angle(self, landmarks: np.ndarray, finger_name: str) -> float:
        """Return bend angle in degrees for a named finger."""
        if landmarks is None or landmarks.shape != (21, 3):
            return 0.0
        if finger_name == "thumb":
            return _finger_angle(landmarks, *_THUMB_TRIPLET)
        triplet = _FINGER_TRIPLETS.get(finger_name)
        if triplet is None:
            return 0.0
        return _finger_angle(landmarks, *triplet)

    def get_palm_orientation(self, landmarks: np.ndarray) -> str:
        """
        Determine if the palm faces toward or away from the camera.
        Uses the cross product of two palm edge vectors to get the normal,
        then checks the z component.
        Returns 'toward' or 'away'.
        """
        if landmarks is None or landmarks.shape != (21, 3):
            return "unknown"
        # Vectors along palm base: index MCP → pinky MCP and wrist → middle MCP
        v1 = _vec(landmarks[INDEX_MCP], landmarks[PINKY_MCP])
        v2 = _vec(landmarks[WRIST],     landmarks[MIDDLE_MCP])
        normal = np.cross(v1, v2)
        # Positive z-normal → palm toward camera (front-facing)
        return "toward" if normal[2] > 0 else "away"

    def get_wrist_angle(self, landmarks: np.ndarray) -> float:
        """
        Compute tilt of the wrist (for scroll speed control).
        Returns angle in degrees between wrist→index_MCP vector and horizontal.
        Positive = tilted up, negative = tilted down.
        """
        if landmarks is None or landmarks.shape != (21, 3):
            return 0.0
        wrist_to_mcp = _vec(landmarks[WRIST], landmarks[INDEX_MCP])
        # Project onto XY plane
        horizontal = np.array([1.0, 0.0, 0.0])
        angle = _angle_between(wrist_to_mcp[:2].tolist() + [0.0],
                               [1.0, 0.0, 0.0])
        # Sign: negative y component means hand tilted upward in image coords
        if wrist_to_mcp[1] < 0:
            angle = -angle
        return angle

    def is_pinching(self, landmarks: np.ndarray,
                    finger1: str = "thumb",
                    finger2: str = "index",
                    threshold: float = 30.0) -> bool:
        """
        Return True if the pixel distance between two fingertips is below threshold.
        threshold is in normalised units × 1000 (approx pixels on 1280-wide frame).
        """
        if landmarks is None or landmarks.shape != (21, 3):
            return False
        t1 = FINGERTIP_IDS[finger1]
        t2 = FINGERTIP_IDS[finger2]
        # Use only XY for pinch (ignore depth)
        dist = np.linalg.norm(landmarks[t1, :2] - landmarks[t2, :2]) * 1000.0
        return dist < threshold

    def get_hand_openness(self, landmarks: np.ndarray) -> float:
        """
        Return a 0.0–1.0 measure of how open the hand is.
        0.0 = fully fisted, 1.0 = fully open flat.
        """
        if landmarks is None or landmarks.shape != (21, 3):
            return 0.0
        angles = []
        for name, triplet in _FINGER_TRIPLETS.items():
            angles.append(_finger_angle(landmarks, *triplet))
        # Thumb
        angles.append(_finger_angle(landmarks, *_THUMB_TRIPLET))
        avg_angle = float(np.mean(angles))
        # Map: 0° (fully straight) → 1.0, 90°+ (fully curled) → 0.0
        return float(np.clip(1.0 - avg_angle / 90.0, 0.0, 1.0))


# ── Convenience alias ─────────────────────────────────────────────────────────
FINGERTIP_IDS = {
    "thumb":  THUMB_TIP,
    "index":  INDEX_TIP,
    "middle": MIDDLE_TIP,
    "ring":   RING_TIP,
    "pinky":  PINKY_TIP,
}
