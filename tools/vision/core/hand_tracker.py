"""
core/hand_tracker.py
Camera thread + MediaPipe HandLandmarker with FPS governor.
Puts landmark dicts into a thread-safe queue for action thread to consume.
"""
from __future__ import annotations
import logging
import os
import queue
import threading
import time
from typing import Optional

log = logging.getLogger("hand_tracker")

_BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
MODEL_PATH = os.path.join(_BASE, "models", "hand_landmarker.task")

TARGET_FPS      = 30
FPS_DROP_THRESH = 20      # drop to every-other-frame below this
LOG_INTERVAL    = 30      # seconds between latency logs


class HandTracker:
    """
    Runs MediaPipe HandLandmarker in a dedicated camera thread.
    Publishes landmark data to a thread-safe queue.
    Implements FPS governor and latency logging.
    """

    def __init__(self, cam_index: int = 0, max_hands: int = 2) -> None:
        self._cam_index = cam_index
        self._max_hands = max_hands
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._data_queue: queue.Queue = queue.Queue(maxsize=4)
        self._frame_queue: queue.Queue = queue.Queue(maxsize=2)  # for HUD display
        self._fps = 0.0
        self._latencies: list[float] = []
        self._last_log = time.time()
        self._frame_skip = False  # FPS governor toggle

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self) -> bool:
        """Start camera thread. Returns False if model/camera missing."""
        if not os.path.exists(MODEL_PATH):
            log.error("Model not found: %s", MODEL_PATH)
            return False
        try:
            import mediapipe, cv2  # noqa
        except ImportError as e:
            log.error("Missing deps: %s", e)
            return False
        self._running = True
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="hand-tracker"
        )
        self._thread.start()
        log.info("HandTracker started (cam=%d, max_hands=%d)", self._cam_index, self._max_hands)
        return True

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)

    def get_data(self, timeout: float = 0.05) -> Optional[dict]:
        """Get latest landmark data from queue. Returns None if empty."""
        try:
            return self._data_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def get_frame(self) -> Optional[object]:
        """Get latest raw BGR frame for HUD rendering."""
        try:
            return self._frame_queue.get_nowait()
        except queue.Empty:
            return None

    @property
    def fps(self) -> float:
        return self._fps

    # ── Camera loop (runs in dedicated thread) ────────────────────────────────

    def _loop(self) -> None:
        import cv2
        import mediapipe as mp

        HandLandmarker        = mp.tasks.vision.HandLandmarker
        HandLandmarkerOptions = mp.tasks.vision.HandLandmarkerOptions
        RunningMode           = mp.tasks.vision.RunningMode
        BaseOptions           = mp.tasks.BaseOptions
        MpImage               = mp.Image
        MpImageFormat         = mp.ImageFormat

        options = HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=MODEL_PATH),
            running_mode=RunningMode.IMAGE,
            num_hands=self._max_hands,
            min_hand_detection_confidence=0.65,
            min_hand_presence_confidence=0.55,
            min_tracking_confidence=0.55,
        )

        cap = cv2.VideoCapture(self._cam_index, cv2.CAP_DSHOW)
        if not cap.isOpened():
            cap = cv2.VideoCapture(self._cam_index)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

        frame_count = 0
        fps_ts = time.time()

        with HandLandmarker.create_from_options(options) as landmarker:
            while self._running:
                t_capture = time.time()
                ret, frame = cap.read()
                if not ret:
                    time.sleep(0.05)
                    continue

                frame = cv2.flip(frame, 1)
                frame_count += 1

                # FPS calculation
                now = time.time()
                elapsed = now - fps_ts
                if elapsed >= 1.0:
                    self._fps = frame_count / elapsed
                    frame_count = 0
                    fps_ts = now

                # FPS governor: skip every other frame when FPS < threshold
                if self._fps > 0 and self._fps < FPS_DROP_THRESH:
                    self._frame_skip = not self._frame_skip
                    if self._frame_skip:
                        self._publish_frame(frame)
                        time.sleep(1.0 / TARGET_FPS)
                        continue
                else:
                    self._frame_skip = False

                # MediaPipe detection
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                try:
                    result = landmarker.detect(
                        MpImage(image_format=MpImageFormat.SRGB, data=rgb)
                    )
                except Exception as e:
                    log.debug("Detection error: %s", e)
                    self._publish_frame(frame)
                    continue

                t_detect = time.time()
                latency_ms = (t_detect - t_capture) * 1000
                self._latencies.append(latency_ms)

                # Build data packet
                hands = []
                for i, lm in enumerate(result.hand_landmarks or []):
                    handedness = "right"
                    if result.handedness and i < len(result.handedness):
                        label = result.handedness[i][0].category_name
                        handedness = label.lower()
                    hands.append({"landmarks": lm, "handedness": handedness})

                packet = {
                    "hands": hands,
                    "frame": frame.copy(),
                    "fps": self._fps,
                    "latency_ms": latency_ms,
                    "timestamp": t_capture,
                    "landmarker": landmarker,  # for calibration access
                }

                # Non-blocking put (drop old if full)
                try:
                    self._data_queue.put_nowait(packet)
                except queue.Full:
                    try:
                        self._data_queue.get_nowait()
                        self._data_queue.put_nowait(packet)
                    except queue.Empty:
                        pass

                self._publish_frame(frame)
                self._maybe_log_latency()
                time.sleep(max(0, 1.0 / TARGET_FPS - (time.time() - t_capture)))

        cap.release()

    def _publish_frame(self, frame) -> None:
        try:
            self._frame_queue.put_nowait(frame)
        except queue.Full:
            try:
                self._frame_queue.get_nowait()
                self._frame_queue.put_nowait(frame)
            except queue.Empty:
                pass

    def _maybe_log_latency(self) -> None:
        now = time.time()
        if now - self._last_log >= LOG_INTERVAL and self._latencies:
            avg = sum(self._latencies) / len(self._latencies)
            log.info("Avg detection latency: %.1f ms over last %d frames",
                     avg, len(self._latencies))
            self._latencies.clear()
            self._last_log = now
