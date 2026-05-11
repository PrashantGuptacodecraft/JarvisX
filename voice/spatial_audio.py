"""
voice/spatial_audio.py
Spatial audio engine for JarvisX.

Applies stereo panning and optional room reverb to TTS audio output
to give a sense of directionality — left=system, center=AI, right=web.

Requires pydub. Graceful no-op if not installed.
"""
from __future__ import annotations
import logging
import io
import os
from pathlib import Path

log = logging.getLogger("spatial_audio")

# Task-type → stereo pan position (-1.0=full left, 0=center, 1.0=full right)
_TASK_PAN = {
    # System tasks: left speaker
    "system":    -0.6,
    "apps":      -0.5,
    "files":     -0.4,
    "terminal":  -0.7,
    # AI / conversational: center
    "ai":         0.0,
    "memory":     0.0,
    "tasks":     -0.1,
    # Web / external: right speaker
    "web":        0.6,
    "browser":    0.5,
    "whatsapp":   0.4,
    "vision":     0.3,
}

_DEFAULT_PAN = 0.0
_REVERB_DECAY = 0.3   # simple echo coefficient


class SpatialAudioEngine:
    """
    Post-processes TTS audio files/bytes with stereo panning.

    Usage:
        engine = SpatialAudioEngine()
        panned_bytes = engine.apply(audio_bytes, task_type="web", fmt="mp3")
    """

    def __init__(self):
        self.available: bool = False
        self._init_backend()

    def _init_backend(self):
        try:
            import pydub  # noqa: F401
            self.available = True
            log.info("SpatialAudioEngine: pydub backend ready.")
        except ImportError:
            log.warning(
                "SpatialAudioEngine: pydub not installed. "
                "Run: pip install pydub   (spatial audio disabled)"
            )

    def get_pan(self, task_type: str) -> float:
        """Return pan value for a given task type."""
        return _TASK_PAN.get((task_type or "").lower(), _DEFAULT_PAN)

    def apply(
        self,
        audio_bytes: bytes,
        task_type: str = "ai",
        fmt: str = "mp3",
        apply_reverb: bool = False,
    ) -> bytes:
        """
        Apply stereo panning (and optional reverb) to audio bytes.
        Returns processed bytes in the same format.
        Falls through unmodified if pydub unavailable or error occurs.
        """
        if not self.available or not audio_bytes:
            return audio_bytes
        try:
            from pydub import AudioSegment
            from pydub.effects import normalize

            seg = AudioSegment.from_file(io.BytesIO(audio_bytes), format=fmt)
            pan = self.get_pan(task_type)

            if abs(pan) > 0.05:
                seg = seg.pan(pan)

            if apply_reverb:
                seg = self._simple_reverb(seg)

            out = io.BytesIO()
            seg.export(out, format=fmt)
            return out.getvalue()
        except Exception as e:
            log.debug(f"SpatialAudioEngine.apply error: {e}")
            return audio_bytes

    def apply_to_file(
        self,
        filepath: str,
        task_type: str = "ai",
        apply_reverb: bool = False,
    ) -> str:
        """
        Apply spatial audio processing to an audio file in-place.
        Returns the filepath (modified or original).
        """
        if not self.available:
            return filepath
        try:
            from pydub import AudioSegment
            ext = Path(filepath).suffix.lstrip(".").lower() or "mp3"
            seg = AudioSegment.from_file(filepath, format=ext)
            pan = self.get_pan(task_type)
            if abs(pan) > 0.05:
                seg = seg.pan(pan)
            if apply_reverb:
                seg = self._simple_reverb(seg)
            seg.export(filepath, format=ext)
            return filepath
        except Exception as e:
            log.debug(f"SpatialAudioEngine.apply_to_file error: {e}")
            return filepath

    @staticmethod
    def _simple_reverb(seg):
        """Add a simple echo reverb effect."""
        try:
            from pydub import AudioSegment
            delay_ms = 60
            decay = _REVERB_DECAY
            delayed = AudioSegment.silent(duration=delay_ms) + seg
            # Mix original + attenuated delay
            mixed = seg.overlay(delayed - int(20 * (1 - decay)))
            return mixed
        except Exception:
            return seg
