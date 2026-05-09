"""
core/voice_gesture_fusion.py
VoiceGestureFusion — real-time Whisper voice recognition fused with
hand gestures to produce high-confidence composite commands.
Falls back to SpeechRecognition (Google) if Whisper unavailable.
"""
from __future__ import annotations

import json
import logging
import os
import queue
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

log = logging.getLogger(__name__)

_SAMPLE_RATE    = 16_000
_CHUNK_SECS     = 1.5
_CHUNK_SAMPLES  = int(_SAMPLE_RATE * _CHUNK_SECS)
_VOICE_WINDOW   = 1.2      # seconds — max age of a voice result to fuse
_GESTURE_SOLO   = 0.82     # fire on gesture alone if confidence is this high
_AMP_DECAY      = 0.85     # amplitude envelope decay per frame

_LOG_DIR  = Path(__file__).resolve().parent.parent / "logs"
_LOG_FILE = _LOG_DIR / "fusion_log.jsonl"


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class VoiceResult:
    text:       str
    confidence: float
    timestamp:  float


@dataclass
class FusionResult:
    should_fire:       bool
    fusion_score:      float
    gesture_name:      str
    voice_phrase:      str
    action:            str
    feedback:          str
    suppressed_reason: str
    timestamp:         float = field(default_factory=time.time)


# ── Main class ────────────────────────────────────────────────────────────────

class VoiceGestureFusion:
    """
    Records audio in a background thread, transcribes with Whisper (or Google),
    and fuses the voice result with the current gesture to produce a FusionResult.
    """

    def __init__(self, settings, command_map: dict) -> None:
        self._settings     = settings
        self._cmd_map      = command_map
        self._threshold    = getattr(settings, "FUSION_THRESHOLD", 0.72)
        self._window_ms    = getattr(settings, "FUSION_TIME_WINDOW_MS", 1200)

        self._voice_q: queue.Queue[VoiceResult] = queue.Queue(maxsize=8)
        self._last_voice:  Optional[VoiceResult] = None
        self._last_phrase: str   = ""
        self._amplitude:   float = 0.0
        self._voice_active_until: float = 0.0

        self._running   = False
        self._thread:   Optional[threading.Thread] = None
        self._whisper   = None   # loaded in background
        self._use_google = False

        # Ensure log dir exists
        _LOG_DIR.mkdir(parents=True, exist_ok=True)

        # Start Whisper load in background (non-blocking)
        self._whisper_ready = threading.Event()
        threading.Thread(target=self._load_whisper, daemon=True,
                         name="whisper-loader").start()

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Begin audio capture thread."""
        if self._running:
            return
        self._running = True
        self._thread  = threading.Thread(
            target=self._audio_capture_thread,
            daemon=True, name="voice-capture"
        )
        self._thread.start()
        log.info("VoiceGestureFusion started (sample_rate=%d)", _SAMPLE_RATE)

    def stop(self) -> None:
        """Gracefully stop the capture thread."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=3.0)
        log.info("VoiceGestureFusion stopped")

    # ── Core fusion ───────────────────────────────────────────────────────────

    def check_fusion(self, gesture_name: str,
                     gesture_confidence: float) -> FusionResult:
        """
        Attempt to fuse latest voice result with the given gesture.
        Returns a FusionResult indicating whether an action should fire.
        """
        now = time.time()

        # Drain queue to get the freshest voice result
        latest: Optional[VoiceResult] = None
        while True:
            try:
                vr = self._voice_q.get_nowait()
                latest = vr
            except queue.Empty:
                break

        if latest is not None:
            self._last_voice  = latest
            self._last_phrase = latest.text.strip().lower()

        # Decide whether voice is fresh enough to use
        voice_in_window = (
            self._last_voice is not None
            and (now - self._last_voice.timestamp) <= (self._window_ms / 1000.0)
        )

        if voice_in_window:
            voice_phrase = self._normalise_phrase(self._last_phrase)
            voice_conf   = self._last_voice.confidence

            # Look up command
            fusion_key = f"{voice_phrase}+{gesture_name}"
            cmd = self._cmd_map.get(fusion_key)

            if cmd is not None:
                # Weighted score: gesture 60%, voice 40%
                score = gesture_confidence * 0.6 + voice_conf * 0.4
                min_score = cmd.get("min_fusion_score", self._threshold)

                if score >= min_score:
                    result = FusionResult(
                        should_fire=True,
                        fusion_score=round(score, 4),
                        gesture_name=gesture_name,
                        voice_phrase=voice_phrase,
                        action=cmd["action"],
                        feedback=cmd["feedback"],
                        suppressed_reason="",
                    )
                    self._log_event(result)
                    self._last_voice = None   # consume token
                    return result
                else:
                    result = FusionResult(
                        should_fire=False,
                        fusion_score=round(score, 4),
                        gesture_name=gesture_name,
                        voice_phrase=voice_phrase,
                        action="",
                        feedback="",
                        suppressed_reason="score_too_low",
                    )
                    self._log_event(result)
                    return result
            else:
                # Voice heard but no matching fusion rule
                result = FusionResult(
                    should_fire=False,
                    fusion_score=0.0,
                    gesture_name=gesture_name,
                    voice_phrase=voice_phrase,
                    action="",
                    feedback="",
                    suppressed_reason="no_matching_command",
                )
                self._log_event(result)
                return result

        # No voice in window — gesture-only high-confidence path
        if gesture_confidence >= _GESTURE_SOLO:
            result = FusionResult(
                should_fire=True,
                fusion_score=round(gesture_confidence, 4),
                gesture_name=gesture_name,
                voice_phrase="",
                action=f"gesture_only:{gesture_name}",
                feedback="",
                suppressed_reason="",
            )
            self._log_event(result)
            return result

        return FusionResult(
            should_fire=False,
            fusion_score=round(gesture_confidence, 4),
            gesture_name=gesture_name,
            voice_phrase="",
            action="",
            feedback="",
            suppressed_reason="no_voice_and_low_confidence",
        )

    # ── Status queries ────────────────────────────────────────────────────────

    def get_last_voice_phrase(self) -> str:
        """Return the last transcribed phrase for HUD display."""
        return self._last_phrase

    def get_mic_amplitude(self) -> float:
        """Return smoothed amplitude 0.0–1.0 for waveform visualisation."""
        return min(1.0, self._amplitude)

    def is_voice_active(self) -> bool:
        """True if audio was detected in the last 500ms."""
        return time.time() < self._voice_active_until

    # ── Background threads ────────────────────────────────────────────────────

    def _load_whisper(self) -> None:
        """Load Whisper model in a daemon thread (non-blocking startup)."""
        model_name = getattr(self._settings, "WHISPER_MODEL", "tiny")
        try:
            import whisper
            log.info("Loading Whisper model '%s'…", model_name)
            self._whisper = whisper.load_model(model_name)
            log.info("Whisper model '%s' loaded", model_name)
        except Exception as exc:
            log.warning("Whisper unavailable (%s) — falling back to Google STT", exc)
            self._use_google = True
        finally:
            self._whisper_ready.set()

    def _audio_capture_thread(self) -> None:
        """
        Daemon thread: records 1.5-second chunks, transcribes, queues results.
        """
        try:
            import sounddevice as sd
        except ImportError:
            log.error("sounddevice not installed — voice capture disabled")
            return

        log.info("Audio capture thread started")

        while self._running:
            try:
                # Record 1.5s chunk
                audio = sd.rec(
                    _CHUNK_SAMPLES,
                    samplerate=_SAMPLE_RATE,
                    channels=1,
                    dtype="float32",
                )
                sd.wait()
                audio_flat = audio.flatten()

                # Update amplitude for waveform HUD
                rms = float(np.sqrt(np.mean(audio_flat ** 2)))
                self._amplitude = self._amplitude * _AMP_DECAY + rms * (1 - _AMP_DECAY)
                if rms > 0.005:
                    self._voice_active_until = time.time() + 0.5

                # Skip silent chunks (saves compute)
                if rms < 0.003:
                    continue

                # Transcribe
                vr = self._transcribe(audio_flat)
                if vr is not None and vr.text.strip():
                    if not self._voice_q.full():
                        self._voice_q.put(vr)
                    log.debug("Voice: '%s' (conf=%.2f)", vr.text, vr.confidence)

            except Exception as exc:
                log.debug("Audio capture error: %s", exc)
                time.sleep(0.1)

    def _transcribe(self, audio: np.ndarray) -> Optional[VoiceResult]:
        """Transcribe audio array. Uses Whisper if available, else Google."""
        if not self._use_google and self._whisper is not None:
            try:
                result = self._whisper.transcribe(
                    audio, language="en", fp16=False, verbose=False
                )
                text = result.get("text", "").strip()
                segs = result.get("segments", [])
                if segs:
                    avg_conf = float(np.mean([
                        min(1.0, max(0.0, s.get("no_speech_prob", 0.5)))
                        for s in segs
                    ]))
                    conf = round(1.0 - avg_conf, 3)   # no_speech_prob → speech_conf
                else:
                    conf = 0.6
                return VoiceResult(text=text, confidence=conf, timestamp=time.time())
            except Exception as exc:
                log.debug("Whisper transcribe error: %s", exc)
                return None

        # Google STT fallback
        try:
            import speech_recognition as sr
            recognizer = sr.Recognizer()
            audio_bytes = (audio * 32767).astype(np.int16).tobytes()
            audio_data  = sr.AudioData(audio_bytes, _SAMPLE_RATE, 2)
            text = recognizer.recognize_google(audio_data)
            return VoiceResult(text=text, confidence=0.70, timestamp=time.time())
        except Exception as exc:
            log.debug("Google STT error: %s", exc)
            return None

    # ── Utilities ─────────────────────────────────────────────────────────────

    @staticmethod
    def _normalise_phrase(phrase: str) -> str:
        """
        Strip punctuation and extract the first meaningful keyword.
        Maps common synonyms to canonical command words.
        """
        SYNONYMS = {
            "shut": "close", "exit": "close", "quit": "close",
            "undo": "undo",  "revert": "undo",
            "snap": "screenshot", "capture": "screenshot",
            "find": "search", "look": "search",
        }
        clean = "".join(c for c in phrase.lower() if c.isalpha() or c.isspace())
        words = clean.split()
        for word in words:
            if word in SYNONYMS:
                return SYNONYMS[word]
            # Return first word that is a known command prefix
            if any(word in key for key in ["open","close","search","save",
                                            "bigger","undo","screenshot","jarvis",
                                            "play","stop","next","volume","new",
                                            "back","zoom","copy","paste","select",
                                            "delete"]):
                return word
        return words[0] if words else ""

    def _log_event(self, result: FusionResult) -> None:
        """Append a JSON line to fusion_log.jsonl."""
        entry = {
            "ts":         round(result.timestamp, 3),
            "fired":      result.should_fire,
            "score":      result.fusion_score,
            "gesture":    result.gesture_name,
            "voice":      result.voice_phrase,
            "action":     result.action,
            "suppressed": result.suppressed_reason,
        }
        try:
            with _LOG_FILE.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as exc:
            log.debug("Log write error: %s", exc)
