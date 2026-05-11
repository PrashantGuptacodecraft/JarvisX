"""
tools/vision/modules/object_detector.py
Real-time YOLO object detection overlay for JarvisX.

Uses ultralytics YOLOv8-nano (lightweight, fast).
Graceful no-op if ultralytics not installed.

Usage:
    detector = ObjectDetector()
    detector.start()
    annotated_frame = detector.annotate(frame)   # adds bounding boxes
    objects = detector.detected_objects          # list of label strings
"""
from __future__ import annotations
import threading
import time
import logging
from typing import Optional
import numpy as np

log = logging.getLogger("object_detector")

# Colors for bounding boxes (BGR)
_CLASS_COLORS = [
    (0, 220, 255), (0, 255, 100), (255, 100, 0), (200, 0, 255),
    (255, 200, 0), (0, 100, 255), (255, 0, 150), (100, 255, 200),
]

# Confidence threshold for detections
CONF_THRESHOLD = 0.45


class ObjectDetector:
    """
    Runs YOLOv8-nano inference on camera frames.
    Annotates frames with bounding boxes + labels.
    Maintains a list of currently detected objects.
    """

    def __init__(self, model_size: str = "yolov8n.pt", analysis_interval: float = 0.5):
        self.model_size = model_size
        self.analysis_interval = analysis_interval

        self.available: bool = False
        self._model = None
        self.detected_objects: list[str] = []
        self._latest_results = None
        self._results_lock = threading.Lock()

        self._frame: Optional[np.ndarray] = None
        self._frame_lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None

        self._init_model()

    def _init_model(self):
        try:
            from ultralytics import YOLO
            self._model = YOLO(self.model_size)
            self.available = True
            log.info(f"ObjectDetector: YOLOv8 loaded ({self.model_size})")
        except ImportError:
            log.warning(
                "ObjectDetector: ultralytics not installed. "
                "Run: pip install ultralytics"
            )
        except Exception as e:
            log.warning(f"ObjectDetector: model load failed: {e}")

    def start(self):
        if not self.available:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="object-detector")
        self._thread.start()
        log.info("ObjectDetector started.")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)

    def push_frame(self, frame: np.ndarray):
        if not self.available or frame is None:
            return
        with self._frame_lock:
            self._frame = frame.copy()

    def annotate(self, frame: np.ndarray) -> np.ndarray:
        """Draw detection boxes on the frame. Returns annotated frame."""
        if not self.available:
            return frame
        import cv2
        with self._results_lock:
            results = self._latest_results
        if results is None:
            return frame

        h, w = frame.shape[:2]
        labels_this_frame = []
        for result in results:
            boxes = result.boxes
            if boxes is None:
                continue
            for box in boxes:
                conf = float(box.conf[0])
                if conf < CONF_THRESHOLD:
                    continue
                cls_id = int(box.cls[0])
                label = result.names.get(cls_id, str(cls_id))
                labels_this_frame.append(label)
                color = _CLASS_COLORS[cls_id % len(_CLASS_COLORS)]

                # Bounding box
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                # Clamp to frame
                x1, y1 = max(0, x1), max(0, y1)
                x2, y2 = min(w-1, x2), min(h-1, y2)
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2, cv2.LINE_AA)

                # Label background + text
                text = f"{label} {conf:.0%}"
                (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
                cv2.rectangle(frame, (x1, y1 - th - 8), (x1 + tw + 6, y1), color, -1)
                cv2.putText(
                    frame, text, (x1 + 3, y1 - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1, cv2.LINE_AA,
                )

        self.detected_objects = list(dict.fromkeys(labels_this_frame))  # dedupe, ordered
        return frame

    def describe_scene(self) -> str:
        """Return a natural language description of detected objects."""
        if not self.detected_objects:
            return "I can't see any identifiable objects right now."
        counts: dict[str, int] = {}
        for obj in self.detected_objects:
            counts[obj] = counts.get(obj, 0) + 1
        parts = []
        for label, count in counts.items():
            parts.append(f"{count} {label}" + ("s" if count > 1 else ""))
        return "I can see: " + ", ".join(parts) + "."

    def _loop(self):
        while self._running:
            time.sleep(self.analysis_interval)
            frame = None
            with self._frame_lock:
                if self._frame is not None:
                    frame = self._frame.copy()
            if frame is None:
                continue
            try:
                results = self._model(frame, verbose=False, conf=CONF_THRESHOLD)
                with self._results_lock:
                    self._latest_results = results
            except Exception as e:
                log.debug(f"ObjectDetector inference error: {e}")
