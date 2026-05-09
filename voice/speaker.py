"""voice/speaker.py — JARVIS: brilliant, warm, human-sounding female AI voice.
Golden rules applied via SSML:
  - Natural pauses after Hmm/Right/So/Wait (300–600ms)
  - Subtle pitch drops (-3%) at sentence ends → sounds conclusive, not robotic
  - Emphasis on 1-2 key words max per sentence
  - Mixed prosody rates (slow for emotive, fast for informational)
  - Edge NeerjaExpressiveNeural / AriaNeural for best SSML support
"""

from __future__ import annotations

import asyncio
import os
import queue
import tempfile
import threading
import time

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


def _strip_ssml(text: str) -> str:
    """Strip all XML/SSML tags from text so pyttsx3 speaks plain words only."""
    import re
    # Remove all XML tags
    clean = re.sub(r'<[^>]+>', '', text)
    # Collapse extra whitespace
    clean = re.sub(r'\s+', ' ', clean).strip()
    return clean or text

# ── Voice profiles ────────────────────────────────────────────────────────────
VOICE_PROFILES = {
    # Primary: warm, expressive Indian-English — best SSML support
    "human_girl": {
        "edge_voice":            "en-IN-NeerjaExpressiveNeural",
        "rate":                  "-6%",
        "pitch":                 "+0Hz",
        "volume":                "+0%",
        "ssml_style":            "chat",       # mstts:express-as style
        "ssml_style_degree":     "1.2",
        "pyttsx3_rate":          158,
        "pyttsx3_voice_keywords": ["neerja", "zira", "female", "hazel", "aria"],
    },
    # Confident US female — great for assistant persona
    "aria": {
        "edge_voice":            "en-US-AriaNeural",
        "rate":                  "-4%",
        "pitch":                 "+0Hz",
        "volume":                "+0%",
        "ssml_style":            "chat",
        "ssml_style_degree":     "1.3",
        "pyttsx3_rate":          162,
        "pyttsx3_voice_keywords": ["aria", "zira", "female"],
    },
    # Warm friendly US — Jenny is excellent for natural conversation
    "jenny": {
        "edge_voice":            "en-US-JennyNeural",
        "rate":                  "-5%",
        "pitch":                 "+0Hz",
        "volume":                "+0%",
        "ssml_style":            "chat",
        "ssml_style_degree":     "1.2",
        "pyttsx3_rate":          160,
        "pyttsx3_voice_keywords": ["zira", "female", "hazel"],
    },
    # Soft British — elegant, calm
    "soft_british": {
        "edge_voice":            "en-GB-SoniaNeural",
        "rate":                  "-5%",
        "pitch":                 "+0Hz",
        "volume":                "+0%",
        "ssml_style":            "chat",
        "ssml_style_degree":     "1.0",
        "pyttsx3_rate":          158,
        "pyttsx3_voice_keywords": ["sonia", "hazel", "female"],
    },
    # Cheerful cute — higher energy
    "cute_girl": {
        "edge_voice":            "en-US-AvaMultilingualNeural",
        "rate":                  "-3%",
        "pitch":                 "+0Hz",
        "volume":                "+0%",
        "ssml_style":            "cheerful",
        "ssml_style_degree":     "1.5",
        "pyttsx3_rate":          168,
        "pyttsx3_voice_keywords": ["zira", "ava", "female"],
    },
    # Hindi — Swara is Microsoft's best Hindi Neural voice
    "hindi": {
        "edge_voice":            "hi-IN-SwaraNeural",
        "rate":                  "-5%",
        "pitch":                 "+0Hz",
        "volume":                "+0%",
        "ssml_style":            "chat",
        "ssml_style_degree":     "1.2",
        "pyttsx3_rate":          155,
        "pyttsx3_voice_keywords": ["swara", "female", "hindi"],
    },
    # Hinglish — NeerjaExpressive handles code-switching naturally
    "hinglish": {
        "edge_voice":            "en-IN-NeerjaExpressiveNeural",
        "rate":                  "-6%",
        "pitch":                 "+0Hz",
        "volume":                "+0%",
        "ssml_style":            "chat",
        "ssml_style_degree":     "1.3",
        "pyttsx3_rate":          158,
        "pyttsx3_voice_keywords": ["neerja", "zira", "female", "hazel"],
    },
}

# ── SSML golden-rule helpers ──────────────────────────────────────────────────
_FILLER_PAUSES = {
    # English fillers
    "Hmm":    "450ms", "Hmm,":   "450ms",
    "Right":  "350ms", "Right,": "350ms",
    "So":     "300ms", "So,":    "300ms",
    "Well":   "350ms", "Well,":  "350ms",
    "Wait":   "400ms", "Wait,":  "400ms",
    "Now":    "250ms", "Now,":   "250ms",
    "Look":   "250ms", "Look,":  "250ms",
    "Okay":   "350ms", "Okay,":  "350ms",
    "OK":     "300ms", "OK,":    "300ms",
    "Actually": "300ms", "Actually,": "300ms",
    # Hindi / Hinglish fillers
    "Haan":   "350ms", "Haan,":  "350ms",
    "Accha":  "400ms", "Accha,": "400ms",
    "Theek":  "300ms", "Theek,": "300ms",
    "Dekho":  "300ms", "Dekho,": "300ms",
    "Suno":   "350ms", "Suno,":  "350ms",
    "Aur":    "200ms", "Aur,":   "200ms",
    "Toh":    "250ms", "Toh,":   "250ms",
    "Matlab": "350ms", "Matlab,":"350ms",
}

# Words to auto-emphasise when they appear in a sentence (max 1 per sentence)
_EMPHASIS_WORDS = {
    "absolutely", "exactly", "definitely", "certainly", "really",
    "never", "always", "immediately", "important", "critical",
    "please", "sorry", "love", "great", "perfect", "done",
}

DEFAULT_PROFILE = VOICE_PROFILES["human_girl"]



class Speaker:
    def __init__(self):
        self._lock = threading.Lock()
        self._speaking = False
        self._eleven_voice_lookup_done = False
        self._stop_event = threading.Event()
        self._speech_queue: queue.Queue = queue.Queue()
        self._request_counter = 0
        self._current_request_id = 0
        self._current_text = ""
        self._pyttsx3_engine = None
        self.profile_name = VOICE_PROFILE if VOICE_PROFILE in VOICE_PROFILES else "human_girl"
        self.profile = VOICE_PROFILES.get(self.profile_name, DEFAULT_PROFILE)
        self.edge_voice = EDGE_VOICE or self.profile["edge_voice"]
        self.edge_rate = TTS_RATE or self.profile["rate"]
        self.edge_pitch = TTS_PITCH or self.profile["pitch"]
        self.edge_volume = TTS_VOLUME or self.profile["volume"]
        self.eleven_voice_id = ELEVENLABS_VOICE_ID.strip()
        self.eleven_voice_name = ELEVENLABS_VOICE_NAME.strip()
        self.playback_backend = self._detect_playback_backend()
        self.engine = self._detect_engine()
        self._worker = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker.start()
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

    def speak(self, text: str, blocking: bool = True, interrupt: bool = False, on_complete=None):
        if not text or not text.strip():
            return

        text = text.strip()
        log.info(f"TTS: {text[:80]}")
        done = threading.Event()
        with self._lock:
            self._request_counter += 1
            request_id = self._request_counter

        if interrupt:
            self.stop(clear_queue=True)

        self._speech_queue.put(
            {
                "id": request_id,
                "text": text,
                "done": done,
                "on_complete": on_complete,
            }
        )

        if blocking:
            done.wait()

    @property
    def is_speaking(self) -> bool:
        return self._speaking

    @property
    def current_text(self) -> str:
        with self._lock:
            return self._current_text

    def acknowledge(self) -> bool:
        try:
            import winsound

            winsound.Beep(980, 70)
            winsound.Beep(1320, 55)
            return True
        except Exception:
            return False

    def stop(self, clear_queue: bool = True):
        self._stop_event.set()
        self._stop_active_playback()
        if not clear_queue:
            return

        while True:
            try:
                pending = self._speech_queue.get_nowait()
            except queue.Empty:
                break

            done = pending.get("done")
            if done:
                done.set()

            callback = pending.get("on_complete")
            if callback:
                try:
                    callback(True)
                except TypeError:
                    callback()
                except Exception as exc:
                    log.warning(f"Speech completion callback failed: {exc}")

    def _worker_loop(self):
        while True:
            request = self._speech_queue.get()
            request_id = request["id"]
            text = request["text"]
            done = request["done"]
            on_complete = request.get("on_complete")
            interrupted = False

            with self._lock:
                self._stop_event.clear()
                self._speaking = True
                self._current_request_id = request_id
                self._current_text = text

            try:
                self._speak_now(text)
            except Exception as exc:
                if self._stop_event.is_set():
                    interrupted = True
                else:
                    log.error(f"TTS error ({self.engine}): {exc}")
                    try:
                        if self.engine != "pyttsx3":
                            self._pyttsx3(_strip_ssml(text))
                        else:
                            raise
                    except Exception:
                        log.warning("All TTS engines failed — text: %s", _strip_ssml(text))
            finally:
                interrupted = interrupted or self._stop_event.is_set()
                with self._lock:
                    if self._current_request_id == request_id:
                        self._speaking = False
                        self._current_request_id = 0
                        self._current_text = ""
                    self._pyttsx3_engine = None
                    self._stop_event.clear()
                done.set()
                if on_complete:
                    try:
                        on_complete(interrupted)
                    except TypeError:
                        on_complete()
                    except Exception as exc:
                        log.warning(f"Speech completion callback failed: {exc}")

    def _speak_now(self, text: str):
        if self._stop_event.is_set():
            return
        if self.engine == "elevenlabs":
            self._eleven(text)
            return
        if self.engine == "edge":
            self._edge(text)
            return
        if self.engine == "gtts":
            self._gtts(text)
            return
        if self.engine == "pyttsx3":
            self._pyttsx3(text)
            return
        log.warning("No TTS engine available — text: %s", _strip_ssml(text))

    def _edge(self, text: str):
        """Edge TTS — plain text with native rate/pitch/volume params.
        No SSML used: avoids XML being read aloud when TTS falls back.
        """
        import edge_tts

        # Always use plain text — edge-tts handles prosody via native params
        clean = _strip_ssml(text)   # safety: strip any stray tags

        async def _synthesize():
            communicate = edge_tts.Communicate(
                text=clean,
                voice=self.edge_voice,
                rate=self.edge_rate,
                pitch=self.edge_pitch,
                volume=self.edge_volume,
            )
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as fh:
                tmp_path = fh.name
            await communicate.save(tmp_path)
            return tmp_path

        loop = asyncio.new_event_loop()
        try:
            tmp_path = loop.run_until_complete(_synthesize())
        finally:
            loop.close()

        try:
            if self._stop_event.is_set():
                return
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
            if self._stop_event.is_set():
                return
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

        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
            pygame.mixer.music.load(path)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                if self._stop_event.is_set():
                    pygame.mixer.music.stop()
                    break
                pygame.time.Clock().tick(20)
        except Exception as exc:
            log.warning("pygame playback failed (%s) — trying sounddevice", exc)
            try:
                self._play_with_sounddevice(path)
            except Exception as exc2:
                log.error("All audio playback failed: %s", exc2)
        finally:
            try:
                if pygame.mixer.get_init():
                    pygame.mixer.music.stop()
                    pygame.mixer.quit()
            except Exception:
                pass


    def _play_with_sounddevice(self, path: str):
        import numpy as np
        import sounddevice as sd
        import soundfile as sf

        data, sample_rate = sf.read(path, dtype="float32")
        if getattr(data, "ndim", 1) == 1:
            data = np.column_stack([data, data])

        sd.play(data, sample_rate, blocking=False)
        try:
            while True:
                stream = sd.get_stream()
                if not stream or not getattr(stream, "active", False):
                    break
                if self._stop_event.is_set():
                    sd.stop()
                    break
                time.sleep(0.05)
        finally:
            sd.stop()

    def _pyttsx3(self, text: str):
        import pyttsx3

        engine = pyttsx3.init()
        self._pyttsx3_engine = engine
        engine.setProperty("rate", self.profile.get("pyttsx3_rate", 165))
        engine.setProperty("volume", 1.0)
        keywords = self.profile.get("pyttsx3_voice_keywords", [])
        voices = engine.getProperty("voices")
        for voice in voices:
            voice_name = voice.name.lower()
            if any(keyword in voice_name for keyword in keywords):
                engine.setProperty("voice", voice.id)
                break

        # Always strip SSML/XML tags — pyttsx3 cannot process them
        clean_text = _strip_ssml(text)
        engine.say(clean_text)
        engine.startLoop(False)
        try:
            while True:
                if self._stop_event.is_set():
                    engine.stop()
                    break
                engine.iterate()
                if not engine.isBusy():
                    break
                time.sleep(0.01)
        finally:
            try:
                engine.endLoop()
            except Exception:
                pass

    def _stop_active_playback(self):
        engine = self._pyttsx3_engine
        if engine is not None:
            try:
                engine.stop()
            except Exception:
                pass

        if self.playback_backend == "pygame":
            try:
                import pygame

                if pygame.mixer.get_init():
                    pygame.mixer.music.stop()
            except Exception:
                pass

        if self.playback_backend == "sounddevice":
            try:
                import sounddevice as sd

                sd.stop()
            except Exception:
                pass

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
            if self._stop_event.is_set():
                return
            self._play_audio_file(tmp_path)
        finally:
            try:
                os.remove(tmp_path)
            except OSError:
                pass
