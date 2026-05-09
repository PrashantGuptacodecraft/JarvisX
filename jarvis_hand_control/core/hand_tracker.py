"""
core/hand_tracker.py
MediaPipe Hands wrapper — processes camera frames and returns
structured hand tracking results with full type safety.
"""
from __future__ import annotations

import time
import logging
from dataclasses import dataclass, field
from typing import Optional

import cv2
import mediapipe as mp
import numpy as np

log = logging.getLogger(__name__)

# MediaPipe hand landmark indices
WRIST           = 0
THUMB_CMC       = 1;  THUMB_MCP = 2;  THUMB_IP = 3;  THUMB_TIP = 4
INDEX_MCP       = 5;  INDEX_PIP = 6;  INDEX_DIP = 7;  INDEX_TIP = 8
MIDDLE_MCP      = 9;  MIDDLE_PIP = 10; MIDDLE_DIP = 11; MIDDLE_TIP = 12
RING_MCP        = 13; RING_PIP = 14;  RING_DIP = 15; RING_TIP = 16
PINKY_MCP       = 17; PINKY_PIP = 18; PINKY_DIP = 19; PINKY_TIP = 20

FINGERTIP_IDS = {
    "thumb":  THUMB_TIP,
    "index":  INDEX_TIP,
    "middle": MIDDLE_TIP,
    "ring":   RING_TIP,
    "pinky":  PINKY_TIP,
}


@dataclass
class HandTrackingResult:
    """Single-frame output from HandTracker.process_frame()."""
    landmarks_list:     list[list]            # one list-of-21-landmarks per hand
    handedness_list:    list[str]             # "Right" or "Left" per hand
    annotated_frame:    np.ndarray            # BGR frame with skeleton drawn
    hand_count:         int                   # 0, 1, or 2
    processing_time_ms: float                 # detection latency
    raw_results:        object = field(repr=False, default=None)   # raw mp result


class HandTracker:
    """
    Wraps MediaPipe Hands for frame-by-frame detection.

    Usage
    -----
    tracker = HandTracker(settings)
    result  = tracker.process_frame(bgr_frame)
    lm_arr  = tracker.get_landmark_array(0)   # shape (21, 3)
    """

    def __init__(
        self,
        settings=None,
        max_hands: int = 2,
        min_detection_confidence: float = 0.70,
        min_tracking_confidence: float  = 0.60,
        model_complexity: int = 0,
    ) -> None:
        self._max_hands  = max_hands
        self._min_detect = min_detection_confidence
        self._min_track  = min_tracking_confidence
        self._complexity = model_complexity

        if settings is not None:
            self._max_hands = 2 if settings.load_features().get("dual_hand_enabled", True) else 1

        self._mp_hands   = mp.solutions.hands
        self._mp_draw    = mp.solutions.drawing_utils
        self._mp_styles  = mp.solutions.drawing_styles

        self._hands = self._mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=self._max_hands,
            min_detection_confidence=self._min_detect,
            min_tracking_confidence=self._min_track,
            model_complexity=self._model_complexity_clamped(),
        )

        self._last_result: Optional[HandTrackingResult] = None
        log.info(
            "HandTracker init: max_hands=%d detect=%.2f track=%.2f complexity=%d",
            self._max_hands, self._min_detect, self._min_track, self._complexity,
        )

    # ── Public API ────────────────────────────────────────────────────────────

    def process_frame(self, frame: np.ndarray) -> HandTrackingResult:
        """
        Run MediaPipe Hands on a BGR frame.

        Parameters
        ----------
        frame : np.ndarray  BGR image from cv2.VideoCapture

        Returns
        -------
        HandTrackingResult with all detected hands' data.
        """
        t0 = time.perf_counter()

        # MediaPipe expects RGB
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        rgb.flags.writeable = False
        mp_result = self._hands.process(rgb)
        rgb.flags.writeable = True

        latency_ms = (time.perf_counter() - t0) * 1000.0

        annotated = frame.copy()
        landmarks_list: list[list] = []
        handedness_list: list[str] = []

        if mp_result.multi_hand_landmarks:
            for hand_lm, hand_hand in zip(
                mp_result.multi_hand_landmarks,
                mp_result.multi_handedness,
            ):
                # Draw skeleton
                self._mp_draw.draw_landmarks(
                    annotated,
                    hand_lm,
                    self._mp_hands.HAND_CONNECTIONS,
                    self._mp_styles.get_default_hand_landmarks_style(),
                    self._mp_styles.get_default_hand_connections_style(),
                )
                landmarks_list.append(hand_lm.landmark)
                label = hand_hand.classification[0].label   # "Left" | "Right"
                handedness_list.append(label)

        result = HandTrackingResult(
            landmarks_list=landmarks_list,
            handedness_list=handedness_list,
            annotated_frame=annotated,
            hand_count=len(landmarks_list),
            processing_time_ms=round(latency_ms, 2),
            raw_results=mp_result,
        )
        self._last_result = result
        return result

    def get_hand_label(self, hand_index: int) -> str:
        """Return 'Right' or 'Left' for the given hand index. Returns '' if not found."""
        if self._last_result is None:
            return ""
        if hand_index >= len(self._last_result.handedness_list):
            return ""
        return self._last_result.handedness_list[hand_index]

    def get_landmark_array(self, hand_index: int) -> Optional[np.ndarray]:
        """
        Return landmarks as numpy array of shape (21, 3) with columns [x, y, z].
        x and y are normalised [0, 1]. z is relative depth.
        Returns None if hand_index is out of range.
        """
        if self._last_result is None:
            return None
        if hand_index >= len(self._last_result.landmarks_list):
            return None
        lm_list = self._last_result.landmarks_list[hand_index]
        return np.array([[lm.x, lm.y, lm.z] for lm in lm_list], dtype=np.float32)

    def get_fingertip_positions(self, hand_index: int,
                                frame_w: int = 1280,
                                frame_h: int = 720) -> dict[str, tuple[int, int]]:
        """
        Return pixel (x, y) positions of all 5 fingertips.
        Returns empty dict if hand not detected.
        """
        arr = self.get_landmark_array(hand_index)
        if arr is None:
            return {}
        return {
            finger: (int(arr[tip_id, 0] * frame_w), int(arr[tip_id, 1] * frame_h))
            for finger, tip_id in FINGERTIP_IDS.items()
        }

    def close(self) -> None:
        """Release MediaPipe resources."""
        try:
            self._hands.close()
            log.info("HandTracker closed")
        except Exception as exc:
            log.debug("HandTracker close error: %s", exc)

    # ── Private ───────────────────────────────────────────────────────────────

    def _model_complexity_clamped(self) -> int:
        return max(0, min(self._complexity, 1))

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
