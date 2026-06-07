"""
tools/vision/modules/gaze_tracker.py
Eye/gaze tracking using MediaPipe Face Mesh iris landmarks.

Maps iris position → normalized screen gaze coordinates.
Dwell-click: gaze at same point for 2s → fires a click action.

Graceful no-op if mediapipe not available.

Usage:
    tracker = GazeTracker()
    tracker.start()
    annotated = tracker.annotate(frame)       # draws iris dots on frame
    gx, gy = tracker.gaze_position            # 0.0–1.0 normalized
    tracker.stop()
"""
from __future__ import annotations
import threading
import time
import math
import logging
import os
import urllib.request
from typing import Optional, Tuple
import numpy as np

log = logging.getLogger("gaze_tracker")

# MediaPipe iris landmark indices (left/right eye)
_LEFT_IRIS  = [474, 475, 476, 477]
_RIGHT_IRIS = [469, 470, 471, 472]

# Dwell-click: if gaze stays within this normalized radius for DWELL_TIME seconds
DWELL_RADIUS = 0.04
DWELL_TIME   = 2.0


class GazeTracker:
    """
    Tracks eye/gaze position using MediaPipe Face Mesh.
    Provides normalized screen coordinates (0-1) for where the user is looking.
    """

    def __init__(self, click_callback=None):
        """
        click_callback: callable(x: float, y: float)
                        called when a dwell-click is detected
        """
        self.click_callback = click_callback
        self.available: bool = False
        self.gaze_position: Tuple[float, float] = (0.5, 0.5)
        self.gaze_confidence: float = 0.0

        self._face_mesh = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._frame: Optional[np.ndarray] = None
        self._frame_lock = threading.Lock()

        # Dwell tracking
        self._dwell_start: Optional[float] = None
        self._dwell_anchor: Optional[Tuple[float, float]] = None
        self._dwell_fired = False

        # Smoothing (EMA)
        self._smooth_x = 0.5
        self._smooth_y = 0.5
        self._alpha = 0.25

        self._init_backend()

    def _init_backend(self):
        try:
            model_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "models", "face_landmarker.task")
            if not os.path.exists(model_path):
                log.info("Downloading face_landmarker.task...")
                os.makedirs(os.path.dirname(model_path), exist_ok=True)
                urllib.request.urlretrieve("https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task", model_path)
                
            import mediapipe as mp
            BaseOptions = mp.tasks.BaseOptions
            FaceLandmarker = mp.tasks.vision.FaceLandmarker
            FaceLandmarkerOptions = mp.tasks.vision.FaceLandmarkerOptions
            VisionRunningMode = mp.tasks.vision.RunningMode
            
            options = FaceLandmarkerOptions(
                base_options=BaseOptions(model_asset_path=model_path),
                running_mode=VisionRunningMode.IMAGE,
                num_faces=1,
                min_face_detection_confidence=0.5,
                min_face_presence_confidence=0.5,
                min_tracking_confidence=0.5,
                output_face_blendshapes=False,
                output_facial_transformation_matrixes=False
            )
            self._face_mesh = FaceLandmarker.create_from_options(options)
            self.available = True
            log.info("GazeTracker: MediaPipe FaceLandmarker ready (iris tracking enabled).")
        except ImportError:
            log.warning("GazeTracker: mediapipe not installed. Run: pip install mediapipe")
        except Exception as e:
            log.warning(f"GazeTracker init failed: {e}")

    def start(self):
        if not self.available:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="gaze-tracker")
        self._thread.start()
        log.info("GazeTracker started.")

    def stop(self):
        self._running = False
        if self._face_mesh:
            try:
                self._face_mesh.close()
            except Exception:
                pass
        if self._thread:
            self._thread.join(timeout=2)

    def push_frame(self, frame: np.ndarray):
        if not self.available or frame is None:
            return
        with self._frame_lock:
            self._frame = frame.copy()

    def annotate(self, frame: np.ndarray) -> np.ndarray:
        """Draw iris dots on the frame."""
        if not self.available:
            return frame
        try:
            import cv2
            gx, gy = self.gaze_position
            h, w = frame.shape[:2]
            px, py = int(gx * w), int(gy * h)
            # Outer ring
            cv2.circle(frame, (px, py), 12, (0, 220, 255), 1, cv2.LINE_AA)
            # Inner dot
            cv2.circle(frame, (px, py), 4, (0, 220, 255), -1, cv2.LINE_AA)
            # Cross hair
            cv2.line(frame, (px - 16, py), (px + 16, py), (0, 220, 255), 1, cv2.LINE_AA)
            cv2.line(frame, (px, py - 16), (px, py + 16), (0, 220, 255), 1, cv2.LINE_AA)

            # Dwell progress arc
            if self._dwell_start is not None and not self._dwell_fired:
                elapsed = time.time() - self._dwell_start
                progress = min(elapsed / DWELL_TIME, 1.0)
                angle = int(360 * progress)
                cv2.ellipse(frame, (px, py), (16, 16), -90, 0, angle, (255, 200, 0), 2, cv2.LINE_AA)
        except Exception as e:
            log.debug(f"GazeTracker annotate error: {e}")
        return frame

    def _loop(self):
        while self._running:
            frame = None
            with self._frame_lock:
                if self._frame is not None:
                    frame = self._frame.copy()
            if frame is None:
                time.sleep(0.05)
                continue
            self._process(frame)
            time.sleep(0.05)  # ~20 fps gaze analysis

    def _process(self, frame: np.ndarray):
        import cv2
        import mediapipe as mp
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = self._face_mesh.detect(mp_image)
        
        if not result.face_landmarks:
            self.gaze_confidence = 0.0
            return

        lm = result.face_landmarks[0]
        h, w = frame.shape[:2]

        # Average iris center (left + right)
        try:
            left_cx  = sum(lm[i].x for i in _LEFT_IRIS)  / len(_LEFT_IRIS)
            left_cy  = sum(lm[i].y for i in _LEFT_IRIS)  / len(_LEFT_IRIS)
            right_cx = sum(lm[i].x for i in _RIGHT_IRIS) / len(_RIGHT_IRIS)
            right_cy = sum(lm[i].y for i in _RIGHT_IRIS) / len(_RIGHT_IRIS)
        except IndexError:
            return

        raw_x = (left_cx + right_cx) / 2.0
        raw_y = (left_cy + right_cy) / 2.0

        # EMA smoothing
        self._smooth_x = self._alpha * raw_x + (1 - self._alpha) * self._smooth_x
        self._smooth_y = self._alpha * raw_y + (1 - self._alpha) * self._smooth_y

        self.gaze_position = (
            max(0.0, min(1.0, self._smooth_x)),
            max(0.0, min(1.0, self._smooth_y)),
        )
        self.gaze_confidence = 1.0

        # Dwell click detection
        self._check_dwell()

    def _check_dwell(self):
        gx, gy = self.gaze_position
        if self._dwell_anchor is None:
            self._dwell_anchor = (gx, gy)
            self._dwell_start = time.time()
            self._dwell_fired = False
            return

        ax, ay = self._dwell_anchor
        dist = math.hypot(gx - ax, gy - ay)

        if dist > DWELL_RADIUS:
            # Gaze moved — reset dwell
            self._dwell_anchor = (gx, gy)
            self._dwell_start = time.time()
            self._dwell_fired = False
            return

        if not self._dwell_fired and time.time() - self._dwell_start >= DWELL_TIME:
            self._dwell_fired = True
            log.info(f"Dwell-click at ({gx:.2f}, {gy:.2f})")
            if self.click_callback:
                try:
                    self.click_callback(gx, gy)
                except Exception as e:
                    log.debug(f"Dwell click callback error: {e}")
