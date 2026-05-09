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
}

# ── SSML golden-rule helpers ──────────────────────────────────────────────────
_FILLER_PAUSES = {
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
}

# Words to auto-emphasise when they appear in a sentence (max 1 per sentence)
_EMPHASIS_WORDS = {
    "absolutely", "exactly", "definitely", "certainly", "really",
    "never", "always", "immediately", "important", "critical",
    "please", "sorry", "love", "great", "perfect", "done",
}

DEFAULT_PROFILE = VOICE_PROFILES["human_girl"]


def _humanize_to_ssml(text: str, voice: str, profile: dict) -> str:
    """
    Convert plain text to expressive SSML following the golden rules:
    1. Natural pauses after filler words (Hmm, Right, So, Wait…)
    2. Subtle pitch drop (-3%) on sentence endings → conclusive, not robotic
    3. One emphasis word per sentence max
    4. Express-as style wrapper for NeerjaExpressiveNeural / AriaNeural / JennyNeural
    5. Mixed prosody — slightly slower for emotional sentences
    """
    import re

    style       = profile.get("ssml_style", "chat")
    style_deg   = profile.get("ssml_style_degree", "1.2")
    global_rate = profile.get("rate", "-5%")

    # ── Split into sentences ──────────────────────────────────────────────────
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    ssml_parts = []

    for sent in sentences:
        sent = sent.strip()
        if not sent:
            continue

        tokens    = sent.split()
        out       = []
        emph_done = False

        for i, tok in enumerate(tokens):
            # Rule 1: filler word → insert pause after it
            if tok in _FILLER_PAUSES:
                pause = _FILLER_PAUSES[tok]
                out.append(f'{tok}<break time="{pause}"/>')
                continue

            # Rule 3: one emphasis per sentence
            clean = re.sub(r'[^a-z]', '', tok.lower())
            if not emph_done and clean in _EMPHASIS_WORDS:
                out.append(f'<emphasis level="moderate">{tok}</emphasis>')
                emph_done = True
                continue

            out.append(tok)

        sentence_body = ' '.join(out)

        # Rule 2: subtle pitch drop at sentence end for conclusive sound
        ends_declarative = sent.endswith('.') or sent.endswith(',')
        if ends_declarative and len(tokens) > 4:
            # Wrap last 2 words in slight pitch-down prosody
            words = sentence_body.rsplit(' ', 2)
            if len(words) == 3:
                tail  = ' '.join(words[1:])
                sentence_body = (
                    words[0]
                    + ' <prosody pitch="-3%" rate="-3%">' + tail + '</prosody>'
                )

        # Rule 4: slow emotive sentences slightly
        emotive_words = {"sorry", "unfortunately", "afraid", "miss", "love", "care", "please"}
        if any(w in sent.lower() for w in emotive_words):
            sentence_body = f'<prosody rate="-8%">{sentence_body}</prosody>'

        ssml_parts.append(sentence_body)

    inner = '  '.join(ssml_parts)

    # ── Wrap in express-as if voice supports it ───────────────────────────────
    expressive_voices = {
        "neerjaexpressive", "aria", "jenny", "sonia", "ava",
        "guy", "davis", "tony", "jane",
    }
    voice_key = voice.lower().replace("-", "").replace("neural", "")
    use_express = any(v in voice_key for v in expressive_voices)

    if use_express:
        inner = (
            f'<mstts:express-as style="{style}" styledegree="{style_deg}">'
            f'{inner}</mstts:express-as>'
        )

    ssml = (
        '<speak version="1.0" '
        'xmlns="http://www.w3.org/2001/10/synthesis" '
        'xmlns:mstts="https://www.w3.org/2001/mstts" '
        'xml:lang="en-US">'
        f'<voice name="{voice}">'
        f'<prosody rate="{global_rate}">'
        f'{inner}'
        '</prosody></voice></speak>'
    )
    return ssml


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
                            self._pyttsx3(text)
                        else:
                            raise
                    except Exception:
                        print(f"\n[JARVIS] {text}\n")
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
        print(f"\n[JARVIS] {text}\n")

    def _edge(self, text: str):
        """Edge TTS with SSML humanisation via golden rules."""
        import edge_tts

        # Build expressive SSML
        ssml = _humanize_to_ssml(text, self.edge_voice, self.profile)

        async def _synthesize():
            # edge_tts.Communicate accepts raw SSML when text starts with <speak
            communicate = edge_tts.Communicate(
                text=ssml,
                voice=self.edge_voice,
                rate=self.edge_rate,
                pitch=self.edge_pitch,
                volume=self.edge_volume,
            )
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as fh:
                tmp_path = fh.name
            try:
                await communicate.save(tmp_path)
            except Exception:
                # SSML rejected by server — fall back to plain text
                communicate = edge_tts.Communicate(
                    text=text,
                    voice=self.edge_voice,
                    rate=self.edge_rate,
                    pitch=self.edge_pitch,
                    volume=self.edge_volume,
                )
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

        pygame.mixer.init()
        try:
            pygame.mixer.music.load(path)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                if self._stop_event.is_set():
                    pygame.mixer.music.stop()
                    break
                pygame.time.Clock().tick(20)
        finally:
            if pygame.mixer.get_init():
                pygame.mixer.quit()

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

        engine.say(text)
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
