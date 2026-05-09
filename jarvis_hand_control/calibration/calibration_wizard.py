"""
calibration/calibration_wizard.py
4-step interactive calibration wizard run on top of the live camera feed.
Produces a fully populated CalibrationData object and persists it.
"""
from __future__ import annotations

import logging
import math
import time
from typing import Callable, Optional

import cv2
import numpy as np

from calibration.calibration_manager import CalibrationData, CalibrationManager

log = logging.getLogger(__name__)

# Landmark indices used during calibration
WRIST       = 0
MIDDLE_TIP  = 12
INDEX_TIP   = 8
THUMB_TIP   = 4

# Corner order for step 3
CORNERS = ["TL", "TR", "BL", "BR"]
CORNER_LABELS = {
    "TL": "TOP-LEFT",
    "TR": "TOP-RIGHT",
    "BL": "BOTTOM-LEFT",
    "BR": "BOTTOM-RIGHT",
}


class CalibrationWizard:
    """
    Runs a 4-step calibration sequence on live frames.

    Usage
    -----
    wizard = CalibrationWizard(manager)
    calib  = wizard.run_wizard(frame_callback)
    """

    def __init__(self, manager: CalibrationManager) -> None:
        self._manager = manager

    def run_wizard(self, frame_callback: Callable) -> Optional[CalibrationData]:
        """
        Execute all 4 calibration steps using frame_callback to get frames.

        frame_callback() → (frame: np.ndarray, landmarks: np.ndarray | None)
          where landmarks is shape (21, 3) normalised XYZ or None.

        Returns completed CalibrationData, or None if aborted.
        """
        log.info("Calibration wizard started")

        # ── Step 1: Hand size baseline ────────────────────────────────────────
        hand_size = self._step_hand_size(frame_callback)
        if hand_size is None:
            return None

        # ── Step 2: Closed fist compression ───────────────────────────────────
        compression = self._step_closed_fist(frame_callback, hand_size)
        if compression is None:
            return None

        # ── Step 3: Corner mapping ────────────────────────────────────────────
        corners = self._step_corner_mapping(frame_callback)
        if corners is None:
            return None

        # ── Step 4: Click threshold ───────────────────────────────────────────
        click_thresh = self._step_click_calibration(frame_callback)
        if click_thresh is None:
            return None

        # Assemble and persist
        data = CalibrationData(
            hand_size_baseline=round(hand_size, 4),
            closed_compression_ratio=round(compression, 4),
            corner_mappings=corners,
            click_distance_threshold=round(click_thresh, 2),
        )
        self._manager.save(data)
        log.info("Calibration complete: %s", data)
        return data

    # ── Step implementations ──────────────────────────────────────────────────

    def _step_hand_size(self, cb: Callable) -> Optional[float]:
        """
        Step 1: Capture 60 frames with open palm.
        Measures wrist→middle_tip normalised distance.
        Returns average distance or None if aborted.
        """
        TARGET  = 60
        samples = []

        while len(samples) < TARGET:
            frame, lm = cb()
            if frame is None:
                return None

            progress = len(samples) / TARGET
            if lm is not None and lm.shape == (21, 3):
                dist = float(np.linalg.norm(lm[MIDDLE_TIP, :2] - lm[WRIST, :2]))
                samples.append(dist)

            self.draw_step_overlay(
                frame, step_num=1,
                instruction="Open palm facing camera",
                progress=progress,
                extra=f"Samples: {len(samples)}/{TARGET}",
            )
            cv2.imshow("JARVIS Calibration", frame)
            if cv2.waitKey(1) & 0xFF == 27:
                log.info("Calibration aborted at step 1")
                return None

        return float(np.mean(samples))

    def _step_closed_fist(self, cb: Callable,
                           open_size: float) -> Optional[float]:
        """
        Step 2: Capture 30 frames with closed fist.
        Returns compression_ratio = fist_size / open_size.
        """
        TARGET  = 30
        samples = []

        while len(samples) < TARGET:
            frame, lm = cb()
            if frame is None:
                return None

            progress = len(samples) / TARGET
            if lm is not None and lm.shape == (21, 3):
                # Measure spread of all fingertips relative to wrist
                tips = lm[[4, 8, 12, 16, 20], :2]
                avg_dist = float(np.mean(np.linalg.norm(
                    tips - lm[WRIST, :2], axis=1
                )))
                samples.append(avg_dist)

            self.draw_step_overlay(
                frame, step_num=2,
                instruction="Make a tight fist",
                progress=progress,
                extra=f"Samples: {len(samples)}/{TARGET}",
            )
            cv2.imshow("JARVIS Calibration", frame)
            if cv2.waitKey(1) & 0xFF == 27:
                return None

        fist_size = float(np.mean(samples))
        ratio     = fist_size / max(open_size, 1e-6)
        return ratio

    def _step_corner_mapping(self, cb: Callable) -> Optional[dict]:
        """
        Step 3: Record index fingertip position at 4 screen corners.
        Waits for 1.5s stability at each corner.
        Returns {'TL': [x,y], 'TR': [x,y], 'BL': [x,y], 'BR': [x,y]}.
        """
        corner_map: dict[str, list] = {}
        HOLD_SECS = 1.5

        for corner_key in CORNERS:
            label    = CORNER_LABELS[corner_key]
            hold_start: Optional[float] = None
            last_pos: Optional[tuple]   = None
            STABILITY_PX = 0.03   # normalised stability threshold

            while True:
                frame, lm = cb()
                if frame is None:
                    return None

                if lm is not None and lm.shape == (21, 3):
                    ix, iy = float(lm[INDEX_TIP, 0]), float(lm[INDEX_TIP, 1])
                    cur_pos = (ix, iy)

                    if last_pos is not None:
                        moved = math.hypot(ix - last_pos[0], iy - last_pos[1])
                        if moved < STABILITY_PX:
                            if hold_start is None:
                                hold_start = time.time()
                            held = time.time() - hold_start
                            progress = held / HOLD_SECS
                        else:
                            hold_start = None
                            progress   = 0.0
                    else:
                        progress = 0.0

                    last_pos = cur_pos

                    if hold_start is not None and (time.time() - hold_start) >= HOLD_SECS:
                        corner_map[corner_key] = [round(ix, 4), round(iy, 4)]
                        log.info("Corner %s recorded: %.3f, %.3f", corner_key, ix, iy)
                        # Flash confirmation
                        for _ in range(6):
                            f2, _ = cb()
                            if f2 is not None:
                                h, w = f2.shape[:2]
                                cv2.putText(f2, f"✔ {label} RECORDED",
                                            (w//2 - 140, h//2),
                                            cv2.FONT_HERSHEY_DUPLEX, 1.1, (0, 255, 100), 2)
                                cv2.imshow("JARVIS Calibration", f2)
                                cv2.waitKey(50)
                        break
                else:
                    progress = 0.0

                self.draw_step_overlay(
                    frame, step_num=3,
                    instruction=f"Point to {label} corner",
                    progress=progress,
                    extra=f"Corner {CORNERS.index(corner_key)+1}/4 — hold still",
                    corner_label=corner_key,
                )
                cv2.imshow("JARVIS Calibration", frame)
                if cv2.waitKey(1) & 0xFF == 27:
                    return None

        return corner_map

    def _step_click_calibration(self, cb: Callable) -> Optional[float]:
        """
        Step 4: Capture 5 click gestures, measure thumb+index pinch distance.
        Returns average - 5px safety margin.
        """
        TARGET    = 5
        distances = []
        PINCH_MIN = 50.0   # normalised × 1000 threshold to trigger capture

        while len(distances) < TARGET:
            frame, lm = cb()
            if frame is None:
                return None

            if lm is not None and lm.shape == (21, 3):
                d = float(np.linalg.norm(
                    lm[THUMB_TIP, :2] - lm[INDEX_TIP, :2]
                )) * 1000.0

                # Capture when pinch detected
                if d < PINCH_MIN:
                    distances.append(d)
                    log.info("Click sample %d: %.1f", len(distances), d)
                    # Wait for hand to open again before next sample
                    while True:
                        frame2, lm2 = cb()
                        if frame2 is None:
                            return None
                        if lm2 is not None:
                            d2 = float(np.linalg.norm(
                                lm2[THUMB_TIP, :2] - lm2[INDEX_TIP, :2]
                            )) * 1000.0
                            if d2 > PINCH_MIN * 1.5:
                                break
                        cv2.imshow("JARVIS Calibration", frame2)
                        cv2.waitKey(1)

            self.draw_step_overlay(
                frame, step_num=4,
                instruction="Perform click gesture 5 times",
                progress=len(distances) / TARGET,
                extra=f"Clicks captured: {len(distances)}/{TARGET}",
            )
            cv2.imshow("JARVIS Calibration", frame)
            if cv2.waitKey(1) & 0xFF == 27:
                return None

        avg   = float(np.mean(distances))
        final = max(5.0, avg - 5.0)   # safety margin
        log.info("Click threshold calibrated: %.1f (avg=%.1f)", final, avg)
        return final

    # ── Overlay rendering ────────────────────────────────────────────────────

    @staticmethod
    def draw_step_overlay(frame: np.ndarray, step_num: int,
                           instruction: str, progress: float,
                           extra: str = "",
                           corner_label: str = "") -> None:
        """
        Draw calibration HUD onto frame in-place:
        - Step indicator
        - Large centered instruction text
        - Progress bar
        - Countdown circle (for corner holds)
        - Extra info text
        """
        h, w = frame.shape[:2]
        # Semi-transparent dark overlay at top
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (w, 90), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.65, frame, 0.35, 0, frame)

        # Step indicator
        cv2.putText(frame, f"CALIBRATION  STEP {step_num} OF 4",
                    (16, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.65,
                    (0, 212, 255), 2, cv2.LINE_AA)

        # Instruction text (centered, large)
        (tw, _), _ = cv2.getTextSize(instruction,
                                      cv2.FONT_HERSHEY_DUPLEX, 1.0, 2)
        tx = max(8, (w - tw) // 2)
        cv2.putText(frame, instruction, (tx, 68),
                    cv2.FONT_HERSHEY_DUPLEX, 1.0, (255, 255, 255), 2, cv2.LINE_AA)

        # Progress bar
        bar_w  = w - 40
        filled = int(progress * bar_w)
        cv2.rectangle(frame, (20, h - 24), (20 + bar_w, h - 10), (40, 40, 40), -1)
        col = (0, 255, 100) if progress < 0.9 else (0, 255, 200)
        if filled > 0:
            cv2.rectangle(frame, (20, h - 24), (20 + filled, h - 10), col, -1)
        cv2.putText(frame, f"{int(progress * 100)}%",
                    (20 + bar_w + 6, h - 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, col, 1, cv2.LINE_AA)

        # Countdown circle for corner detection
        if corner_label:
            angle = int(progress * 360)
            cx, cy = w - 55, h - 55
            cv2.ellipse(frame, (cx, cy), (30, 30), -90, 0, angle,
                        (0, 212, 255), 4, cv2.LINE_AA)
            cv2.circle(frame, (cx, cy), 28, (40, 40, 40), -1)
            cv2.putText(frame, corner_label, (cx - 16, cy + 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.36, (255, 255, 255), 1)

        # Extra info
        if extra:
            cv2.putText(frame, extra, (16, h - 32),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.48, (120, 120, 120),
                        1, cv2.LINE_AA)

        # ESC hint
        cv2.putText(frame, "ESC = abort", (w - 120, 26),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.40, (80, 80, 80), 1)
