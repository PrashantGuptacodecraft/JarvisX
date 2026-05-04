"""voice/speaker.py - natural-sounding TTS with human female voice profiles."""

from __future__ import annotations

import asyncio
import os
import tempfile
import threading

from config.logger import get_logger
from config.settings import (
    EDGE_VOICE,
    ELEVENLABS_KEY,
    ELEVENLABS_MODEL_ID,
    ELEVENLABS_SIMILARITY_BOOST,
    ELEVENLABS_SPEAKER_BOOST,
    ELEVENLABS_STABILITY,
    ELEVENLABS_STYLE,
    ELEVENLABS_VOICE_ID,
    ELEVENLABS_VOICE_NAME,
    TTS_ENGINE,
    TTS_PITCH,
    TTS_RATE,
    TTS_VOLUME,
    VOICE_PROFILE,
)

log = get_logger("speaker")

VOICE_PROFILES = {
    "cute_girl": {
        "edge_voice": "en-US-AvaMultilingualNeural",
        "rate": "-6%",
        "pitch": "+8Hz",
        "volume": "+0%",
        "pyttsx3_rate": 165,
        "pyttsx3_voice_keywords": ["zira", "aria", "ava", "female", "hazel"],
    },
    "warm_indian": {
        "edge_voice": "en-IN-NeerjaExpressiveNeural",
        "rate": "-3%",
        "pitch": "+4Hz",
        "volume": "+0%",
        "pyttsx3_rate": 168,
        "pyttsx3_voice_keywords": ["neerja", "zira", "female", "hazel"],
    },
    "soft_british": {
        "edge_voice": "en-GB-SoniaNeural",
        "rate": "-5%",
        "pitch": "+3Hz",
        "volume": "+0%",
        "pyttsx3_rate": 160,
        "pyttsx3_voice_keywords": ["sonia", "hazel", "female"],
    },
}

DEFAULT_PROFILE = VOICE_PROFILES["cute_girl"]


class Speaker:
    def __init__(self):
        self._lock = threading.Lock()
        self._speaking = False
        self._eleven_voice_lookup_done = False
        self.profile_name = VOICE_PROFILE if VOICE_PROFILE in VOICE_PROFILES else "cute_girl"
        self.profile = VOICE_PROFILES.get(self.profile_name, DEFAULT_PROFILE)
        self.edge_voice = EDGE_VOICE or self.profile["edge_voice"]
        self.edge_rate = TTS_RATE or self.profile["rate"]
        self.edge_pitch = TTS_PITCH or self.profile["pitch"]
        self.edge_volume = TTS_VOLUME or self.profile["volume"]
        self.eleven_voice_id = ELEVENLABS_VOICE_ID.strip()
        self.eleven_voice_name = ELEVENLABS_VOICE_NAME.strip()
        self.playback_backend = self._detect_playback_backend()
        self.engine = self._detect_engine()
        log.info(
            f"TTS engine: {self.engine}  "
            f"(profile: {self.profile_name}, voice: {self.edge_voice}, playback: {self.playback_backend})"
        )

    def _detect_playback_backend(self) -> str:
        try:
            import pygame  # noqa: F401

            return "pygame"
        except ImportError:
            pass
        try:
            import sounddevice  # noqa: F401
            import soundfile  # noqa: F401

            return "sounddevice"
        except ImportError:
            pass
        return "none"

    def _detect_engine(self) -> str:
        preferred = TTS_ENGINE or "auto"
        if preferred != "auto":
            chosen = self._validate_engine(preferred)
            if chosen:
                return chosen

        for candidate in ("elevenlabs", "edge", "gtts", "pyttsx3"):
            chosen = self._validate_engine(candidate)
            if chosen:
                return chosen
        return "print"

    def _validate_engine(self, engine: str) -> str | None:
        if engine == "elevenlabs":
            if ELEVENLABS_KEY and self.playback_backend != "none":
                voice_id = self._resolve_eleven_voice_id()
                if voice_id or self.eleven_voice_id:
                    return "elevenlabs"
                if self.eleven_voice_name:
                    log.warning(
                        f"ElevenLabs voice name '{self.eleven_voice_name}' could not be resolved. "
                        "Falling back to another TTS engine."
                    )
                    return None
                if self.eleven_voice_id:
                    return "elevenlabs"
            return None
        if engine == "edge":
            if self.playback_backend == "none":
                return None
            try:
                import edge_tts  # noqa: F401

                return "edge"
            except ImportError:
                return None
        if engine == "gtts":
            if self.playback_backend == "none":
                return None
            try:
                from gtts import gTTS  # noqa: F401

                return "gtts"
            except ImportError:
                return None
        if engine == "pyttsx3":
            try:
                import pyttsx3  # noqa: F401

                return "pyttsx3"
            except ImportError:
                return None
        if engine == "print":
            return "print"
        return None

    def _resolve_eleven_voice_id(self) -> str:
        if self.eleven_voice_id:
            return self.eleven_voice_id
        if self._eleven_voice_lookup_done:
            return self.eleven_voice_id

        self._eleven_voice_lookup_done = True
        if not ELEVENLABS_KEY or not self.eleven_voice_name:
            return self.eleven_voice_id

        try:
            import requests

            response = requests.get(
                "https://api.elevenlabs.io/v1/voices",
                headers={"xi-api-key": ELEVENLABS_KEY},
                timeout=15,
            )
            response.raise_for_status()
            voices = response.json().get("voices", [])
            target = self.eleven_voice_name.lower().strip()

            exact_match = next(
                (voice for voice in voices if voice.get("name", "").lower().strip() == target),
                None,
            )
            partial_match = exact_match or next(
                (voice for voice in voices if target in voice.get("name", "").lower()),
                None,
            )

            if partial_match and partial_match.get("voice_id"):
                self.eleven_voice_id = partial_match["voice_id"].strip()
                log.info(
                    f"Resolved ElevenLabs voice '{partial_match.get('name', self.eleven_voice_name)}' "
                    f"to voice_id."
                )
        except Exception as exc:
            log.warning(f"ElevenLabs voice lookup failed: {exc}")

        return self.eleven_voice_id

    def speak(self, text: str, blocking: bool = True):
        if not text or not text.strip():
            return
        text = text.strip()
        log.info(f"TTS: {text[:80]}")
        if blocking:
            self._speak(text)
        else:
            threading.Thread(target=self._speak, args=(text,), daemon=True).start()

    @property
    def is_speaking(self) -> bool:
        return self._speaking

    def _speak(self, text: str):
        with self._lock:
            self._speaking = True
            try:
                if self.engine == "elevenlabs":
                    self._eleven(text)
                elif self.engine == "edge":
                    self._edge(text)
                elif self.engine == "gtts":
                    self._gtts(text)
                elif self.engine == "pyttsx3":
                    self._pyttsx3(text)
                else:
                    print(f"\n[JARVIS] {text}\n")
            except Exception as exc:
                log.error(f"TTS error ({self.engine}): {exc}")
                try:
                    self._pyttsx3(text)
                except Exception:
                    print(f"\n[JARVIS] {text}\n")
            finally:
                self._speaking = False

    def _edge(self, text: str):
        import edge_tts

        async def _synthesize():
            communicate = edge_tts.Communicate(
                text=text,
                voice=self.edge_voice,
                rate=self.edge_rate,
                pitch=self.edge_pitch,
                volume=self.edge_volume,
            )
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as file_handle:
                tmp_path = file_handle.name
            await communicate.save(tmp_path)
            return tmp_path

        loop = asyncio.new_event_loop()
        try:
            tmp_path = loop.run_until_complete(_synthesize())
        finally:
            loop.close()

        try:
            self._play_audio_file(tmp_path)
        finally:
            try:
                os.remove(tmp_path)
            except OSError:
                pass

    def _gtts(self, text: str):
        from gtts import gTTS

        tts = gTTS(text=text, lang="en", slow=False)
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as file_handle:
            tmp_path = file_handle.name
        tts.save(tmp_path)
        try:
            self._play_audio_file(tmp_path)
        finally:
            try:
                os.remove(tmp_path)
            except OSError:
                pass

    def _play_audio_file(self, path: str):
        if self.playback_backend == "pygame":
            self._play_with_pygame(path)
            return
        if self.playback_backend == "sounddevice":
            self._play_with_sounddevice(path)
            return
        raise RuntimeError("No usable audio playback backend is installed")

    def _play_with_pygame(self, path: str):
        import pygame

        pygame.mixer.init()
        try:
            pygame.mixer.music.load(path)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                pygame.time.Clock().tick(10)
        finally:
            pygame.mixer.quit()

    def _play_with_sounddevice(self, path: str):
        import numpy as np
        import sounddevice as sd
        import soundfile as sf

        data, sample_rate = sf.read(path, dtype="float32")
        if getattr(data, "ndim", 1) == 1:
            data = np.column_stack([data, data])
        sd.play(data, sample_rate)
        sd.wait()

    def _pyttsx3(self, text: str):
        import pyttsx3

        engine = pyttsx3.init()
        engine.setProperty("rate", self.profile.get("pyttsx3_rate", 165))
        engine.setProperty("volume", 1.0)
        keywords = self.profile.get("pyttsx3_voice_keywords", [])
        voices = engine.getProperty("voices")
        for voice in voices:
            voice_name = voice.name.lower()
            if any(keyword in voice_name for keyword in keywords):
                engine.setProperty("voice", voice.id)
                break
        engine.say(text)
        engine.runAndWait()

    def _eleven(self, text: str):
        import requests

        voice_id = self._resolve_eleven_voice_id()
        if not voice_id:
            raise RuntimeError(
                "ElevenLabs voice is not configured. Set ELEVENLABS_VOICE_ID or ELEVENLABS_VOICE_NAME."
            )

        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        headers = {
            "xi-api-key": ELEVENLABS_KEY,
            "Content-Type": "application/json",
        }
        body = {
            "text": text,
            "model_id": ELEVENLABS_MODEL_ID,
            "voice_settings": {
                "stability": ELEVENLABS_STABILITY,
                "similarity_boost": ELEVENLABS_SIMILARITY_BOOST,
                "style": ELEVENLABS_STYLE,
                "use_speaker_boost": ELEVENLABS_SPEAKER_BOOST,
            },
        }
        response = requests.post(url, json=body, headers=headers, timeout=20)
        response.raise_for_status()
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as file_handle:
            file_handle.write(response.content)
            tmp_path = file_handle.name
        try:
            self._play_audio_file(tmp_path)
        finally:
            try:
                os.remove(tmp_path)
            except OSError:
                pass
