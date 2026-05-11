"""
voice/authenticator.py
Voice Biometric Authentication for JarvisX.

Uses resemblyzer to extract voice embeddings.
Enrollment: record 5s sample → store embedding in data/voice_profile.npy
Authentication: compare live audio embedding against stored profile.

Graceful no-op if resemblyzer not installed.
"""
from __future__ import annotations
import os
import threading
import time
import logging
import numpy as np
from pathlib import Path

log = logging.getLogger("voice_auth")

_PROFILE_DIR = Path(__file__).resolve().parent.parent / "data" / "voice"
_PROFILE_PATH = _PROFILE_DIR / "voice_profile.npy"
_SIMILARITY_THRESHOLD = 0.75   # cosine similarity min to accept
_ENROLLMENT_SECONDS  = 6.0     # how long to record for enrollment


class VoiceAuthenticator:
    """
    Voice biometric authenticator.

    Usage:
        auth = VoiceAuthenticator()
        if not auth.is_enrolled:
            auth.enroll()          # records and saves voice profile
        ok = auth.authenticate(audio_data_bytes, sample_rate=16000)
    """

    def __init__(self):
        self.available: bool = False
        self.is_enrolled: bool = False
        self._encoder = None
        self._profile_embedding: np.ndarray | None = None
        self._lock = threading.Lock()

        _PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        self._init_backend()
        self._load_profile()

    # ── Init ──────────────────────────────────────────────────────────────────

    def _init_backend(self):
        try:
            from resemblyzer import VoiceEncoder
            self._encoder = VoiceEncoder()
            self.available = True
            log.info("VoiceAuthenticator: resemblyzer backend ready.")
        except ImportError:
            log.warning(
                "VoiceAuthenticator: resemblyzer not installed. "
                "Run: pip install resemblyzer   (voice auth disabled)"
            )
        except Exception as e:
            log.warning(f"VoiceAuthenticator init failed: {e}")

    def _load_profile(self):
        if not self.available:
            return
        if _PROFILE_PATH.exists():
            try:
                self._profile_embedding = np.load(str(_PROFILE_PATH))
                self.is_enrolled = True
                log.info("VoiceAuthenticator: profile loaded.")
            except Exception as e:
                log.warning(f"VoiceAuthenticator: profile load failed: {e}")

    # ── Enrollment ────────────────────────────────────────────────────────────

    def enroll(self, audio_bytes: bytes = None, sample_rate: int = 16000) -> str:
        """
        Enroll a voice profile.
        If audio_bytes is provided, use it directly.
        Otherwise, record from microphone.
        Returns status message.
        """
        if not self.available:
            return "Voice authentication not available (resemblyzer not installed)."
        try:
            wav = self._bytes_to_wav(audio_bytes, sample_rate) if audio_bytes else self._record_sample()
            if wav is None or len(wav) < sample_rate:
                return "Recording too short for enrollment."
            embedding = self._embed(wav, sample_rate)
            if embedding is None:
                return "Could not extract voice features."
            with self._lock:
                self._profile_embedding = embedding
                np.save(str(_PROFILE_PATH), embedding)
                self.is_enrolled = True
            log.info("VoiceAuthenticator: profile enrolled and saved.")
            return "Voice profile enrolled successfully."
        except Exception as e:
            log.error(f"VoiceAuthenticator enrollment error: {e}")
            return f"Enrollment failed: {e}"

    # ── Authentication ────────────────────────────────────────────────────────

    def authenticate(self, audio_bytes: bytes, sample_rate: int = 16000) -> bool:
        """
        Authenticate a voice against the stored profile.
        Returns True if voice matches, False otherwise.
        If no profile enrolled or backend unavailable, always returns True.
        """
        if not self.available or not self.is_enrolled:
            return True  # Graceful passthrough
        try:
            wav = self._bytes_to_wav(audio_bytes, sample_rate)
            if wav is None or len(wav) < int(sample_rate * 0.5):
                return True  # Too short to authenticate, allow through
            embedding = self._embed(wav, sample_rate)
            if embedding is None:
                return True
            with self._lock:
                profile = self._profile_embedding
            if profile is None:
                return True
            similarity = float(np.dot(embedding, profile) / (
                np.linalg.norm(embedding) * np.linalg.norm(profile) + 1e-8
            ))
            accepted = similarity >= _SIMILARITY_THRESHOLD
            log.debug(f"VoiceAuth: similarity={similarity:.3f} → {'ACCEPT' if accepted else 'REJECT'}")
            return accepted
        except Exception as e:
            log.debug(f"VoiceAuthenticator auth error: {e}")
            return True  # Fail open (do not lock user out on error)

    def reset(self) -> str:
        """Delete stored voice profile."""
        try:
            if _PROFILE_PATH.exists():
                _PROFILE_PATH.unlink()
            with self._lock:
                self._profile_embedding = None
                self.is_enrolled = False
            return "Voice profile deleted."
        except Exception as e:
            return f"Reset failed: {e}"

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _embed(self, wav: np.ndarray, sample_rate: int) -> np.ndarray | None:
        """Extract voice embedding using resemblyzer."""
        if self._encoder is None:
            return None
        try:
            from resemblyzer import preprocess_wav
            processed = preprocess_wav(wav, source_sr=sample_rate)
            return self._encoder.embed_utterance(processed)
        except Exception as e:
            log.debug(f"Embedding error: {e}")
            return None

    @staticmethod
    def _bytes_to_wav(audio_bytes: bytes, sample_rate: int) -> np.ndarray | None:
        """Convert raw PCM int16 bytes to float32 numpy array."""
        try:
            samples = np.frombuffer(audio_bytes, dtype=np.int16)
            return samples.astype(np.float32) / 32768.0
        except Exception:
            return None

    def _record_sample(self) -> np.ndarray | None:
        """Record a voice sample from the microphone."""
        try:
            import sounddevice as sd
            log.info(f"Recording {_ENROLLMENT_SECONDS}s voice sample for enrollment...")
            samples = sd.rec(
                int(_ENROLLMENT_SECONDS * 16000),
                samplerate=16000, channels=1, dtype="float32",
            )
            sd.wait()
            return samples.flatten()
        except Exception as e:
            log.warning(f"VoiceAuthenticator recording failed: {e}")
            return None
