"""
tools/vision/calibration_manager.py
4-step calibration wizard + save/load to config/calibration.json
"""
from __future__ import annotations
import json
import logging
import math
import os
import time
from typing import Optional

log = logging.getLogger("calibration")

_BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CAL_PATH = os.path.join(_BASE, "config", "calibration.json")

_DEFAULTS = {
    "hand_size_baseline": 0.25,
    "click_threshold": 0.07,
    "screen_bounds": {"x0": 0.05, "x1": 0.95, "y0": 0.05, "y1": 0.90},
    "precision_mode": True,
    "calibrated": False,
}


class CalibrationManager:
    """Manages calibration data. Runs 4-step wizard on first launch."""

    def __init__(self) -> None:
        self._data: dict = {}
        self.load()

    # ── Public ────────────────────────────────────────────────────────────────

    def load(self) -> dict:
        """Load calibration from JSON. Return defaults if missing."""
        if os.path.exists(CAL_PATH):
            try:
                with open(CAL_PATH, "r") as f:
                    self._data = json.load(f)
                log.info("Calibration loaded from %s", CAL_PATH)
            except Exception as e:
                log.warning("Could not load calibration (%s), using defaults", e)
                self._data = dict(_DEFAULTS)
        else:
            self._data = dict(_DEFAULTS)
        return self._data

    def save(self) -> None:
        os.makedirs(os.path.dirname(CAL_PATH), exist_ok=True)
        with open(CAL_PATH, "w") as f:
            json.dump(self._data, f, indent=2)
        log.info("Calibration saved to %s", CAL_PATH)

    def needs_calibration(self) -> bool:
        return not self._data.get("calibrated", False)

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def set(self, key: str, value) -> None:
        self._data[key] = value

    def run_wizard(self, cap, landmarker) -> bool:
        """
        Run 4-step calibration wizard using live camera.
        Returns True if completed successfully.
        """
        import cv2
        log.info("Starting calibration wizard")

        steps = [
            self._step1_open_palm,
            self._step2_closed_fist,
            self._step3_corners,
            self._step4_click_tuning,
        ]
        for i, step_fn in enumerate(steps):
            log.info("Calibration step %d/4", i + 1)
            ok = step_fn(cap, landmarker)
            if not ok:
                log.warning("Calibration step %d failed or skipped", i + 1)
                return False

        self._data["calibrated"] = True
        self.save()
        log.info("Calibration complete")
        return True

    # ── Calibration steps ─────────────────────────────────────────────────────

    def _step1_open_palm(self, cap, landmarker) -> bool:
        """60 frames of open palm → hand size baseline."""
        import cv2, mediapipe as mp
        MpImage, MpFmt = mp.Image, mp.ImageFormat
        sizes = []
        prompt = "STEP 1/4: Show OPEN PALM — hold still"
        deadline = time.time() + 10  # max 10 sec

        while time.time() < deadline and len(sizes) < 60:
            ret, frame = cap.read()
            if not ret:
                continue
            frame = cv2.flip(frame, 1)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            cv2.putText(frame, prompt, (20, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 100), 2)
            cv2.putText(frame, f"Captured: {len(sizes)}/60", (20, 70),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)
            cv2.imshow("JARVIS Calibration", frame)
            cv2.waitKey(1)

            result = landmarker.detect(MpImage(image_format=MpFmt.SRGB, data=rgb))
            if result.hand_landmarks:
                lm = result.hand_landmarks[0]
                # Hand size = wrist to middle finger MCP
                size = math.hypot(lm[9].x - lm[0].x, lm[9].y - lm[0].y)
                sizes.append(size)

        cv2.destroyAllWindows()
        if sizes:
            self._data["hand_size_baseline"] = sum(sizes) / len(sizes)
            return True
        return False

    def _step2_closed_fist(self, cap, landmarker) -> bool:
        """Closed fist → compression ratios (placeholder, stored as bool)."""
        import cv2, mediapipe as mp
        MpImage, MpFmt = mp.Image, mp.ImageFormat
        prompt = "STEP 2/4: Make a FIST — hold still"
        ratios = []
        deadline = time.time() + 8

        while time.time() < deadline and len(ratios) < 40:
            ret, frame = cap.read()
            if not ret:
                continue
            frame = cv2.flip(frame, 1)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            cv2.putText(frame, prompt, (20, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 200, 255), 2)
            cv2.imshow("JARVIS Calibration", frame)
            cv2.waitKey(1)

            result = landmarker.detect(MpImage(image_format=MpFmt.SRGB, data=rgb))
            if result.hand_landmarks:
                lm = result.hand_landmarks[0]
                fist_size = math.hypot(lm[9].x - lm[0].x, lm[9].y - lm[0].y)
                baseline = self._data.get("hand_size_baseline", 0.25)
                if baseline > 0:
                    ratios.append(fist_size / baseline)

        cv2.destroyAllWindows()
        if ratios:
            self._data["fist_compression_ratio"] = sum(ratios) / len(ratios)
        return True  # non-critical step

    def _step3_corners(self, cap, landmarker) -> bool:
        """Point to 4 screen corners to calibrate coordinate mapping."""
        import cv2, mediapipe as mp
        MpImage, MpFmt = mp.Image, mp.ImageFormat

        corners_prompts = [
            ("TOP-LEFT corner", "x0", "y0"),
            ("TOP-RIGHT corner", "x1", "y0"),
            ("BOTTOM-LEFT corner", "x0", "y1"),
            ("BOTTOM-RIGHT corner", "x1", "y1"),
        ]
        bounds: dict[str, float] = {}

        for label, xk, yk in corners_prompts:
            prompt = f"STEP 3/4: Point index finger at {label} — hold 2 sec"
            positions = []
            deadline = time.time() + 8

            while time.time() < deadline and len(positions) < 30:
                ret, frame = cap.read()
                if not ret:
                    continue
                frame = cv2.flip(frame, 1)
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                cv2.putText(frame, prompt, (10, 35),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 200, 0), 2)
                cv2.imshow("JARVIS Calibration", frame)
                cv2.waitKey(1)

                result = landmarker.detect(MpImage(image_format=MpFmt.SRGB, data=rgb))
                if result.hand_landmarks:
                    lm = result.hand_landmarks[0]
                    positions.append((lm[8].x, lm[8].y))

            cv2.destroyAllWindows()
            if positions:
                avg_x = sum(p[0] for p in positions) / len(positions)
                avg_y = sum(p[1] for p in positions) / len(positions)
                bounds[xk] = avg_x
                bounds[yk] = avg_y

        if len(bounds) >= 4:
            self._data["screen_bounds"] = {
                "x0": min(bounds.get("x0", 0.05), 0.3),
                "x1": max(bounds.get("x1", 0.95), 0.7),
                "y0": min(bounds.get("y0", 0.05), 0.3),
                "y1": max(bounds.get("y1", 0.90), 0.7),
            }
        return True

    def _step4_click_tuning(self, cap, landmarker) -> bool:
        """5 click gestures → auto-tune PINCH_THRESHOLD."""
        import cv2, mediapipe as mp
        MpImage, MpFmt = mp.Image, mp.ImageFormat
        dists = []
        prompt = "STEP 4/4: PINCH (click) 5 times slowly"

        deadline = time.time() + 20
        last_dist = 1.0
        click_count = 0

        while time.time() < deadline and click_count < 5:
            ret, frame = cap.read()
            if not ret:
                continue
            frame = cv2.flip(frame, 1)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            cv2.putText(frame, prompt, (10, 35),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 100, 200), 2)
            cv2.putText(frame, f"Clicks: {click_count}/5", (10, 65),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 200), 1)
            cv2.imshow("JARVIS Calibration", frame)
            cv2.waitKey(1)

            result = landmarker.detect(MpImage(image_format=MpFmt.SRGB, data=rgb))
            if result.hand_landmarks:
                lm = result.hand_landmarks[0]
                dist = math.hypot(lm[4].x - lm[8].x, lm[4].y - lm[8].y)
                if last_dist > 0.10 and dist < 0.06:
                    dists.append(dist)
                    click_count += 1
                    time.sleep(0.4)
                last_dist = dist

        cv2.destroyAllWindows()
        if dists:
            avg_thresh = sum(dists) / len(dists) * 1.3  # 30% margin
            self._data["click_threshold"] = min(0.12, max(0.04, avg_thresh))
        return True
