"""voice/listener.py - advanced wake-word and always-on voice listener."""

from __future__ import annotations

import queue
import re
import threading
import time
from difflib import SequenceMatcher

from config.logger import get_logger
from config.settings import (
    USER_NAME,
    VOICE_ALWAYS_ON,
    VOICE_AMBIENT_SECONDS,
    VOICE_COMMAND_TIMEOUT,
    VOICE_CONVERSATION_TIMEOUT,
    VOICE_DYNAMIC_ENERGY,
    VOICE_ENERGY_THRESHOLD,
    VOICE_IDLE_PHRASE_TIME_LIMIT,
    VOICE_PAUSE_THRESHOLD,
    VOICE_PHRASE_TIME_LIMIT,
    VOICE_RETRY_SECONDS,
    VOICE_SILENCE_SECONDS,
    VOICE_WAKE_TIMEOUT,
    VOICE_WAKE_WORDS,
)

log = get_logger("listener")

STOP_WORDS = [
    "sleep jarvis",
    "stop listening",
    "goodbye jarvis",
    "bye jarvis",
    "go to sleep",
    "standby mode",
]
CANCEL_WORDS = ["cancel", "never mind", "forget it", "abort"]
ALWAYS_ON_WORDS = [
    "always listen",
    "always listening mode",
    "enable always listening",
    "enable hands free mode",
    "enable handsfree mode",
    "continuous listening mode",
]
WAKE_MODE_WORDS = [
    "disable always listening",
    "disable hands free mode",
    "disable handsfree mode",
    "wake word mode",
    "normal listening mode",
]


class Listener:
    def __init__(
        self,
        command_queue: queue.Queue,
        status_callback=None,
        wakeword_callback=None,
        speaker=None,
    ):
        self.command_queue = command_queue
        self.status_callback = status_callback
        self.wakeword_callback = wakeword_callback
        self.speaker = speaker

        self.running = True
        self.always_listening = VOICE_ALWAYS_ON
        self.active_mode = VOICE_ALWAYS_ON
        self.recognizer = None
        self.mic = None
        self.available = False
        self.last_error = ""
        self.backend = "none"
        self._conversation_timer = None
        self._next_retry_at = 0.0

        self._wake_words = self._build_wake_words()
        self._init_mic()

    def _build_wake_words(self) -> list[str]:
        words = []
        for phrase in VOICE_WAKE_WORDS:
            clean = phrase.strip().lower()
            if clean and clean not in words:
                words.append(clean)
        return sorted(words, key=len, reverse=True)

    def _init_mic(self):
        try:
            import speech_recognition as sr

            self.recognizer = sr.Recognizer()
            self.recognizer.energy_threshold = VOICE_ENERGY_THRESHOLD
            self.recognizer.dynamic_energy_threshold = VOICE_DYNAMIC_ENERGY
            self.recognizer.pause_threshold = VOICE_PAUSE_THRESHOLD
            self.recognizer.non_speaking_duration = max(0.18, min(0.45, VOICE_PAUSE_THRESHOLD / 2))
            self.recognizer.phrase_threshold = 0.18
            self.mic = sr.Microphone()
            with self.mic as src:
                self.recognizer.adjust_for_ambient_noise(
                    src,
                    duration=VOICE_AMBIENT_SECONDS,
                )
            self.available = True
            self.backend = "speech_recognition"
            previous_error = self.last_error
            self.last_error = ""
            log.info("Microphone ready.")
            if previous_error:
                self._status("listening" if (self.always_listening or self.active_mode) else "sleeping")
        except Exception as exc:
            log.error(f"Mic init failed: {exc}")
            if self._init_sounddevice_fallback():
                return

            self.recognizer = None
            self.mic = None
            self.available = False
            self.backend = "none"
            self.last_error = str(exc)
            self._next_retry_at = time.time() + VOICE_RETRY_SECONDS

    def _init_sounddevice_fallback(self) -> bool:
        try:
            import sounddevice as sd
            import speech_recognition as sr

            self.recognizer = sr.Recognizer()
            self.recognizer.energy_threshold = VOICE_ENERGY_THRESHOLD
            self.recognizer.dynamic_energy_threshold = False
            self.recognizer.pause_threshold = VOICE_PAUSE_THRESHOLD
            self.recognizer.non_speaking_duration = max(0.18, min(0.45, VOICE_PAUSE_THRESHOLD / 2))
            self.recognizer.phrase_threshold = 0.18

            sd.query_devices(kind="input")

            self.mic = "sounddevice"
            self.available = True
            self.backend = "sounddevice"
            self.last_error = ""
            log.info("Using sounddevice fallback microphone backend.")
            return True
        except Exception as fallback_exc:
            self.recognizer = None
            self.mic = None
            self.available = False
            self.backend = "none"
            self.last_error = str(fallback_exc)
            self._next_retry_at = time.time() + VOICE_RETRY_SECONDS
            log.error(f"Sounddevice fallback init failed: {fallback_exc}")
            return False

    def start(self):
        threading.Thread(target=self._loop, daemon=True).start()
        if not self.available:
            log.warning("Listener started in recovery mode: microphone is unavailable.")
        else:
            log.info("Listener started.")

    def stop(self):
        self.running = False
        self._cancel_conversation_timer()

    def keep_active(self):
        """Keep follow-up voice capture open after Jarvis replies."""
        if self.always_listening:
            self.active_mode = True
            self._status("listening")
            return
        if not self.active_mode:
            return
        self._cancel_conversation_timer()
        self._conversation_timer = threading.Timer(
            VOICE_CONVERSATION_TIMEOUT,
            self._timeout_to_sleep,
        )
        self._conversation_timer.daemon = True
        self._conversation_timer.start()

    def wake(self, with_callback: bool = True, acknowledge: bool = True):
        self._cancel_conversation_timer()
        self.active_mode = True
        self._status("listening")
        if with_callback and self.wakeword_callback:
            try:
                self.wakeword_callback(acknowledge=acknowledge)
            except TypeError:
                self.wakeword_callback()

    def sleep(self):
        self._cancel_conversation_timer()
        self.always_listening = False
        self.active_mode = False
        self._status("sleeping")

    def enable_always_listening(self):
        self._cancel_conversation_timer()
        self.always_listening = True
        self.active_mode = True
        self._status("listening")

    def disable_always_listening(self):
        self._cancel_conversation_timer()
        self.always_listening = False
        self.active_mode = False
        self._status("sleeping")

    def _cancel_conversation_timer(self):
        if self._conversation_timer and self._conversation_timer.is_alive():
            self._conversation_timer.cancel()
        self._conversation_timer = None

    def _timeout_to_sleep(self):
        if self.always_listening:
            self.active_mode = True
            self._status("listening")
            return
        if self.active_mode:
            log.info("Conversation timeout - going to sleep.")
            self.active_mode = False
            self._status("sleeping")
            self.command_queue.put("__SLEEP__")

    def _status(self, status: str):
        if self.status_callback:
            self.status_callback(status)

    def _should_pause_for_speaker(self) -> bool:
        return bool(self.speaker and getattr(self.speaker, "is_speaking", False))

    @staticmethod
    def _normalize_spoken_text(text: str) -> str:
        return " ".join(re.findall(r"[a-z0-9]+", (text or "").lower()))

    def _looks_like_speaker_echo(self, text: str) -> bool:
        if not self.speaker or not hasattr(self.speaker, "current_text"):
            return False

        heard = self._normalize_spoken_text(text)
        raw_current = getattr(self.speaker, "current_text", "")
        current = self._normalize_spoken_text(raw_current)
        if not heard or not current:
            return False
        if heard in current or current in heard:
            return True

        for segment in re.split(r"[.!?]+", raw_current):
            segment = self._normalize_spoken_text(segment)
            if not segment:
                continue
            if heard in segment or segment in heard:
                return True
            if SequenceMatcher(None, heard, segment).ratio() >= 0.74:
                return True

        return SequenceMatcher(None, heard, current).ratio() >= 0.82

    def _monitor_barge_in(self):
        text = self._listen_once(timeout=1, phrase_limit=max(2, min(VOICE_IDLE_PHRASE_TIME_LIMIT, 3)))
        if not text or self._looks_like_speaker_echo(text):
            return

        if self.speaker and hasattr(self.speaker, "stop"):
            self.speaker.stop(clear_queue=True)

        if self._handle_local_voice_controls(text):
            return

        voice_open = self.always_listening or self.active_mode
        if not voice_open:
            if not self._contains_wake_word(text):
                return
            remainder = self._strip_wake_word(text)
            self.wake(with_callback=True, acknowledge=not bool(remainder))
            if remainder:
                self.command_queue.put(f"__VOICE__:{remainder}")
                self._status("thinking")
            self.keep_active()
            return

        cleaned = self._strip_wake_word(text) if self._contains_wake_word(text) else text
        if not cleaned:
            self.keep_active()
            self._status("listening")
            return

        self._cancel_conversation_timer()
        self.command_queue.put(f"__VOICE__:{cleaned}")
        self._status("thinking")

    def _listen_once(self, timeout: int, phrase_limit: int) -> str:
        if not self.available or not self.recognizer or not self.mic:
            return ""
        if self.backend == "sounddevice":
            return self._listen_with_sounddevice(timeout=timeout, phrase_limit=phrase_limit)

        import speech_recognition as sr

        try:
            with self.mic as src:
                audio = self.recognizer.listen(
                    src,
                    timeout=timeout,
                    phrase_time_limit=phrase_limit,
                )
            return self.recognizer.recognize_google(audio).lower().strip()
        except (sr.WaitTimeoutError, sr.UnknownValueError):
            return ""
        except Exception as exc:
            log.warning(f"Recognition error: {exc}")
            self.available = False
            self.recognizer = None
            self.mic = None
            self.backend = "none"
            self.last_error = str(exc)
            self._next_retry_at = time.time() + VOICE_RETRY_SECONDS
            return ""

    def _listen_with_sounddevice(self, timeout: int, phrase_limit: int) -> str:
        try:
            import numpy as np
            import sounddevice as sd
            import speech_recognition as sr

            sample_rate = 16000
            block_seconds = 0.12
            block_frames = int(sample_rate * block_seconds)
            max_duration = max(1.0, float(phrase_limit if phrase_limit else timeout))
            start_timeout = max(0.8, float(timeout))
            silence_limit = max(0.28, float(VOICE_SILENCE_SECONDS))
            max_frames = int(max_duration * sample_rate)
            silence_frames = int(silence_limit * sample_rate)
            threshold = self._sounddevice_threshold()

            chunks = []
            pre_roll = []
            pre_roll_limit = max(1, int(0.24 / block_seconds))
            heard_voice = False
            silent_run = 0
            total_frames = 0
            deadline = time.time() + start_timeout
            capture_started_at = None

            with sd.InputStream(
                samplerate=sample_rate,
                channels=1,
                dtype="int16",
                blocksize=block_frames,
            ) as stream:
                while self.running:
                    if not heard_voice and time.time() >= deadline:
                        return ""
                    if heard_voice and capture_started_at and (time.time() - capture_started_at) >= max_duration:
                        break

                    block, _ = stream.read(block_frames)
                    samples = block.reshape(-1).copy()

                    if not heard_voice:
                        pre_roll.append(samples)
                        if len(pre_roll) > pre_roll_limit:
                            pre_roll.pop(0)
                        if not self._chunk_has_voice(samples, threshold):
                            continue
                        heard_voice = True
                        capture_started_at = time.time()
                        chunks.extend(pre_roll)
                        total_frames = sum(len(chunk) for chunk in chunks)
                        silent_run = 0
                        continue

                    chunks.append(samples)
                    total_frames += len(samples)

                    if self._chunk_has_voice(samples, threshold):
                        silent_run = 0
                    else:
                        silent_run += len(samples)
                        if silent_run >= silence_frames:
                            break

                    if total_frames >= max_frames:
                        break

            if not chunks:
                return ""

            samples = np.concatenate(chunks).astype("int16")
            trimmed = self._trim_sounddevice_audio(samples)
            if trimmed is None or len(trimmed) == 0:
                return ""

            audio = sr.AudioData(trimmed.tobytes(), sample_rate, 2)
            return self.recognizer.recognize_google(audio).lower().strip()
        except sr.UnknownValueError:
            return ""
        except Exception as exc:
            log.warning(f"Sounddevice recognition error: {exc}")
            self.available = False
            self.recognizer = None
            self.mic = None
            self.backend = "none"
            self.last_error = str(exc)
            self._next_retry_at = time.time() + VOICE_RETRY_SECONDS
            return ""

    def _sounddevice_threshold(self) -> int:
        recognizer_threshold = int(getattr(self.recognizer, "energy_threshold", VOICE_ENERGY_THRESHOLD) or VOICE_ENERGY_THRESHOLD)
        return max(180, int(recognizer_threshold * 0.72))

    @staticmethod
    def _chunk_has_voice(samples, threshold: int) -> bool:
        if samples is None or len(samples) == 0:
            return False
        normalized = samples.astype("int32")
        peak = int(normalized.max())
        trough = int(normalized.min())
        amplitude = max(abs(peak), abs(trough))
        return amplitude >= threshold

    def _trim_sounddevice_audio(self, samples):
        import numpy as np

        if samples is None or len(samples) == 0:
            return None

        amplitude = np.abs(samples.astype("int32"))
        threshold = max(VOICE_ENERGY_THRESHOLD, 220)
        active_indexes = np.where(amplitude > threshold)[0]
        if active_indexes.size == 0:
            return None

        pad = int(0.25 * 16000)
        start = max(0, int(active_indexes[0]) - pad)
        end = min(len(samples), int(active_indexes[-1]) + pad)
        return samples[start:end].astype("int16")

    def _contains_wake_word(self, text: str) -> bool:
        return any(word in text for word in self._wake_words)

    def _strip_wake_word(self, text: str) -> str:
        for word in self._wake_words:
            if word in text:
                return text.split(word, 1)[-1].strip()
        return text.strip()

    def _retry_mic_if_needed(self):
        if self.available:
            return
        if time.time() < self._next_retry_at:
            return
        self._next_retry_at = time.time() + VOICE_RETRY_SECONDS
        log.info("Retrying microphone initialization.")
        self._init_mic()

    def _handle_local_voice_controls(self, text: str) -> bool:
        if any(phrase in text for phrase in CANCEL_WORDS):
            self.command_queue.put("__CANCEL__")
            return True

        if any(phrase in text for phrase in WAKE_MODE_WORDS):
            self.disable_always_listening()
            self.command_queue.put("__VOICE_WAKE_MODE__")
            return True

        if any(phrase in text for phrase in ALWAYS_ON_WORDS):
            self.enable_always_listening()
            self.command_queue.put("__VOICE_ALWAYS_ON__")
            return True

        if any(phrase in text for phrase in STOP_WORDS):
            self.sleep()
            self.command_queue.put("__SLEEP__")
            return True

        return False

    def _loop(self):
        self._status("listening" if self.always_listening else "sleeping")
        while self.running:
            if self._should_pause_for_speaker():
                self._monitor_barge_in()
                continue

            if not self.available:
                self._retry_mic_if_needed()
                time.sleep(0.5)
                continue

            voice_open = self.always_listening or self.active_mode
            timeout = VOICE_COMMAND_TIMEOUT if voice_open else VOICE_WAKE_TIMEOUT
            phrase_limit = VOICE_PHRASE_TIME_LIMIT if voice_open else VOICE_IDLE_PHRASE_TIME_LIMIT
            self._status("listening" if voice_open else "sleeping")

            text = self._listen_once(timeout=timeout, phrase_limit=phrase_limit)
            if not text:
                continue

            if self._handle_local_voice_controls(text):
                continue

            if not voice_open:
                if not self._contains_wake_word(text):
                    continue
                remainder = self._strip_wake_word(text)
                self.wake(with_callback=True, acknowledge=not bool(remainder))
                if remainder:
                    self.command_queue.put(f"__VOICE__:{remainder}")
                    self._status("thinking")
                self.keep_active()
                continue

            cleaned = self._strip_wake_word(text) if self._contains_wake_word(text) else text
            if not cleaned:
                self.keep_active()
                continue

            self._cancel_conversation_timer()
            self.command_queue.put(f"__VOICE__:{cleaned}")
            self._status("thinking")

    def inject_text(self, text: str):
        """Allow GUI or terminal text input to follow the same voice mode rules."""
        low = text.lower().strip()
        if not low:
            return

        if self._handle_local_voice_controls(low):
            return

        voice_open = self.always_listening or self.active_mode
        if not voice_open and self._contains_wake_word(low):
            self.wake(with_callback=True)
            remainder = self._strip_wake_word(low)
            if remainder:
                self.command_queue.put(remainder)
                self._status("thinking")
            self.keep_active()
            return

        cleaned = self._strip_wake_word(low) if voice_open and self._contains_wake_word(low) else low
        if not cleaned:
            self.keep_active()
            self._status("listening")
            return
        self.command_queue.put(cleaned)
        self._status("thinking")
