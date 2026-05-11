"""
tools/vision/modules/emotion_detector.py
Real-time facial emotion + stress detection running in a background thread.

Uses deepface (preferred) or fer as fallback.
Graceful no-op if neither is installed.

Usage:
    detector = EmotionDetector()
    detector.start()                    # starts background thread
    emotion = detector.current_emotion  # "happy", "sad", "angry", etc.
    stress  = detector.stress_level     # 0.0 – 1.0
    detector.stop()
"""
from __future__ import annotations
import threading
import time
import logging
from typing import Optional
import numpy as np

log = logging.getLogger("emotion_detector")

# Stress-indicating emotions and their weights
_STRESS_EMOTIONS = {
    "angry":     0.9,
    "fear":      0.85,
    "disgust":   0.7,
    "sad":       0.65,
    "surprise":  0.4,
    "neutral":   0.1,
    "happy":     0.0,
}

# How many consecutive stress readings before alerting
_STRESS_ALERT_SECONDS = 60


class EmotionDetector:
    """
    Background thread that analyses camera frames for facial emotion.

    Integrates with the gesture engine frame pipeline:
        detector.push_frame(frame)   ← called by gesture engine each tick
        detector.current_emotion     ← read from anywhere
    """

    def __init__(self, alert_callback=None, analysis_interval: float = 3.0):
        """
        alert_callback: callable(emotion: str, stress: float)
                        called when stress persists > _STRESS_ALERT_SECONDS
        analysis_interval: seconds between analyses (default 3s to be gentle on CPU)
        """
        self.alert_callback = alert_callback
        self.analysis_interval = analysis_interval

        self.current_emotion: str = "neutral"
        self.emotion_confidence: float = 0.0
        self.stress_level: float = 0.0
        self.available: bool = False
        self.backend: str = "none"

        self._frame: Optional[np.ndarray] = None
        self._frame_lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stress_since: Optional[float] = None
        self._alert_fired = False
        self._history: list[str] = []

        self._init_backend()

    # ── Backend detection ───────────────────────────────────────────────────────

    def _init_backend(self):
        """Try deepface first, then fer, then mark unavailable."""
        try:
            import deepface  # noqa: F401
            self.backend = "deepface"
            self.available = True
            log.info("EmotionDetector: using deepface backend")
            return
        except ImportError:
            pass

        try:
            from fer import FER  # noqa: F401
            self.backend = "fer"
            self.available = True
            log.info("EmotionDetector: using fer backend")
            return
        except ImportError:
            pass

        log.warning(
            "EmotionDetector: no backend available. "
            "Install 'deepface' or 'fer' for emotion detection."
        )

    # ── Public API ──────────────────────────────────────────────────────────────

    def start(self):
        """Start the background analysis thread."""
        if not self.available:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="emotion-detector")
        self._thread.start()
        log.info("EmotionDetector started.")

    def stop(self):
        """Stop the background thread."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)

    def push_frame(self, frame: np.ndarray):
        """Push a new camera frame for analysis. Called from gesture engine thread."""
        if not self.available or frame is None:
            return
        with self._frame_lock:
            self._frame = frame.copy()

    @property
    def emotion_summary(self) -> str:
        """Human-readable emotion summary."""
        if not self.available:
            return ""
        if self.current_emotion == "neutral":
            return ""
        return f"{self.current_emotion} ({self.emotion_confidence:.0%})"

    # ── Background loop ─────────────────────────────────────────────────────────

    def _loop(self):
        while self._running:
            time.sleep(self.analysis_interval)
            frame = None
            with self._frame_lock:
                if self._frame is not None:
                    frame = self._frame.copy()
            if frame is None:
                continue
            self._analyse(frame)

    def _analyse(self, frame: np.ndarray):
        """Run emotion analysis on a frame."""
        try:
            if self.backend == "deepface":
                self._analyse_deepface(frame)
            elif self.backend == "fer":
                self._analyse_fer(frame)
        except Exception as e:
            log.debug(f"EmotionDetector analysis error: {e}")

    def _analyse_deepface(self, frame: np.ndarray):
        from deepface import DeepFace
        results = DeepFace.analyze(
            frame,
            actions=["emotion"],
            enforce_detection=False,
            silent=True,
        )
        if not results:
            return
        result = results[0] if isinstance(results, list) else results
        dominant = result.get("dominant_emotion", "neutral").lower()
        emotions = result.get("emotion", {})
        confidence = emotions.get(dominant, 0) / 100.0
        self._update_state(dominant, confidence)

    def _analyse_fer(self, frame: np.ndarray):
        from fer import FER
        detector = FER(mtcnn=False)
        results = detector.detect_emotions(frame)
        if not results:
            return
        emotions = results[0].get("emotions", {})
        if not emotions:
            return
        dominant = max(emotions, key=emotions.get)
        confidence = emotions[dominant]
        self._update_state(dominant, confidence)

    def _update_state(self, emotion: str, confidence: float):
        self.current_emotion = emotion
        self.emotion_confidence = confidence
        self.stress_level = _STRESS_EMOTIONS.get(emotion, 0.2)

        self._history.append(emotion)
        if len(self._history) > 20:
            self._history.pop(0)

        # Stress tracking
        if self.stress_level >= 0.65:
            if self._stress_since is None:
                self._stress_since = time.time()
                self._alert_fired = False
            elif (
                not self._alert_fired
                and time.time() - self._stress_since >= _STRESS_ALERT_SECONDS
            ):
                self._alert_fired = True
                if self.alert_callback:
                    try:
                        self.alert_callback(emotion, self.stress_level)
                    except Exception as e:
                        log.debug(f"Alert callback error: {e}")
        else:
            self._stress_since = None
            self._alert_fired = False

        log.debug(f"Emotion: {emotion} ({confidence:.2f}) stress={self.stress_level:.2f}")
