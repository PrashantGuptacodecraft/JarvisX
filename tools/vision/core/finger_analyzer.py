"""
core/finger_analyzer.py
Joint-angle based finger state detection.
Uses dot-product angles between bone vectors — eliminates Y-axis false positives.
"""
from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Sequence


# ── Per-joint angle thresholds (degrees) ─────────────────────────────────────
# A finger is EXTENDED only if ALL its joint angles exceed their threshold.
THRESHOLDS = {
    "thumb":  {"cmc_mcp": 130, "mcp_ip": 140},
    "index":  {"mcp_pip": 150, "pip_dip": 155},
    "middle": {"mcp_pip": 150, "pip_dip": 155},
    "ring":   {"mcp_pip": 148, "pip_dip": 153},
    "pinky":  {"mcp_pip": 145, "pip_dip": 150},
}


@dataclass
class FingerState:
    """Holds extension booleans + angle data for all 5 fingers."""
    thumb:  bool = False
    index:  bool = False
    middle: bool = False
    ring:   bool = False
    pinky:  bool = False
    angles: dict[str, list[float]] = field(default_factory=dict)
    confidence: float = 0.0  # 0-1: fraction of joints clearly extended/bent

    @property
    def extended(self) -> list[bool]:
        return [self.thumb, self.index, self.middle, self.ring, self.pinky]

    @property
    def count(self) -> int:
        return sum(self.extended)


class FingerAnalyzer:
    """Analyzes MediaPipe hand landmarks to determine finger extension states."""

    # MediaPipe landmark indices
    _LM = {
        "wrist": 0,
        "thumb":  [1, 2, 3, 4],    # CMC, MCP, IP, TIP
        "index":  [5, 6, 7, 8],    # MCP, PIP, DIP, TIP
        "middle": [9, 10, 11, 12],
        "ring":   [13, 14, 15, 16],
        "pinky":  [17, 18, 19, 20],
    }

    def analyze(self, landmarks) -> FingerState:
        """Return FingerState from MediaPipe landmark list."""
        lm = landmarks
        angles: dict[str, list[float]] = {}

        # Thumb: CMC(1)→MCP(2)→IP(3)
        t = self._LM["thumb"]
        t_angles = [
            self._angle(lm[t[0]], lm[t[1]], lm[t[2]]),  # CMC→MCP→IP
            self._angle(lm[t[1]], lm[t[2]], lm[t[3]]),  # MCP→IP→TIP
        ]
        angles["thumb"] = t_angles
        thumb_ext = (t_angles[0] > THRESHOLDS["thumb"]["cmc_mcp"] and
                     t_angles[1] > THRESHOLDS["thumb"]["mcp_ip"])

        results = {"thumb": thumb_ext}
        for name in ("index", "middle", "ring", "pinky"):
            ids = self._LM[name]
            a1 = self._angle(lm[ids[0]], lm[ids[1]], lm[ids[2]])  # MCP→PIP→DIP
            a2 = self._angle(lm[ids[1]], lm[ids[2]], lm[ids[3]])  # PIP→DIP→TIP
            angles[name] = [a1, a2]
            thr = THRESHOLDS[name]
            results[name] = (a1 > thr["mcp_pip"] and a2 > thr["pip_dip"])

        # Confidence: ratio of angles clearly above or below threshold
        total, clear = 0, 0
        for name, ang_list in angles.items():
            thr_vals = list(THRESHOLDS[name].values())
            for ang, thr_v in zip(ang_list, thr_vals):
                total += 1
                if abs(ang - thr_v) > 12:  # 12° margin = clearly decided
                    clear += 1
        confidence = clear / max(total, 1)

        return FingerState(
            thumb=results["thumb"], index=results["index"],
            middle=results["middle"], ring=results["ring"],
            pinky=results["pinky"], angles=angles, confidence=confidence,
        )

    @staticmethod
    def _angle(a, b, c) -> float:
        """Angle at joint B formed by vectors B→A and B→C (in degrees)."""
        ax, ay = a.x - b.x, a.y - b.y
        cx, cy = c.x - b.x, c.y - b.y
        dot = ax * cx + ay * cy
        mag = math.hypot(ax, ay) * math.hypot(cx, cy)
        if mag < 1e-9:
            return 180.0
        return math.degrees(math.acos(max(-1.0, min(1.0, dot / mag))))

    @staticmethod
    def pinch_distance(landmarks, a: int = 4, b: int = 8) -> float:
        """Normalized Euclidean distance between two landmark indices."""
        p, q = landmarks[a], landmarks[b]
        return math.hypot(p.x - q.x, p.y - q.y)
