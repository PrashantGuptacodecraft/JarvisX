"""core_loop.py - Command processor: queue -> brain -> speaker -> GUI."""

import os
import tempfile
import queue
import threading

from config.logger import get_logger
from config.settings import JARVIS_NAME, USER_NAME
from shared_core import publish_safe

log = get_logger("core_loop")

WAKE_REPLY = "Listening."
SLEEP_REPLY = f"Going to standby. Say 'Hello {JARVIS_NAME}' whenever you need me."
ALWAYS_LISTEN_REPLY = f"Always listening mode enabled, {USER_NAME}. You can speak commands without the wake word."
WAKE_MODE_REPLY = f"Wake word mode enabled, {USER_NAME}. Say 'Hello {JARVIS_NAME}' when you need me."


# ── Camera command phrase sets (class-level to avoid rebuilding every call) ──
_CAM_SNAP_PHRASES = [
    "click a photo", "take a photo", "take photo", "click photo",
    "capture photo", "take a picture", "click a picture",
    "take picture", "capture image", "take snapshot",
]
_CAM_QUESTION_PHRASES = [
    "what do you see", "what can you see", "look at me",
    "what's in camera", "what is in camera", "describe what you see",
    "what the object", "what in picture", "what object",
    "my expression", "my face", "how do i look", "my hair",
    "suggest hairstyle", "suggest hair", "analyze my face",
    "what am i wearing", "what other things", "what around",
]


class CoreLoop:
    def __init__(self, command_queue: queue.Queue, brain, speaker, gui=None, memory=None):
        self.queue = command_queue
        self.brain = brain
        self.speaker = speaker
        self.gui = gui
        self.memory = memory
        self.listener = None
        self._reply_token = 0
        self._reply_lock = threading.Lock()

    def start(self):
        threading.Thread(target=self._loop, daemon=True).start()
        log.info("Core loop started.")

    def _loop(self):
        while True:
            try:
                cmd = self.queue.get(timeout=1)
                self._process(cmd)
            except queue.Empty:
                continue
            except Exception as exc:
                log.error(f"Core loop error: {exc}")

    def _process(self, command: str):
        voice_source = False
        already_displayed = False  # True when GUI already showed the user bubble
        if command.startswith("__VOICE__:"):
            voice_source = True
            command = command[len("__VOICE__:"):].strip()
        elif command.startswith("__TEXT__:"):
            # Typed from GUI chat box — display was already done by _on_submit
            already_displayed = True
            command = command[len("__TEXT__:"):].strip()
        command = command.strip()
        if not command:
            return

        turn_token = self._claim_reply_token()
        self._interrupt_speech()

        if command == "__WAKE__":
            self.on_wake()
            return
        if command == "__VOICE_ALWAYS_ON__":
            if self.gui:
                self.gui.set_status("listening")
            self._deliver_reply(ALWAYS_LISTEN_REPLY, turn_token)
            return
        if command == "__VOICE_WAKE_MODE__":
            if self.gui:
                self.gui.set_status("sleeping")
            self._deliver_reply(WAKE_MODE_REPLY, turn_token)
            return
        if command == "__SLEEP__":
            if self.gui:
                self.gui.set_status("sleeping")
            self._deliver_reply(SLEEP_REPLY, turn_token)
            return
        if command == "__CANCEL__":
            if self.brain:
                self.brain.pending = None
            self._deliver_reply(f"Cancelled, {USER_NAME}.", turn_token)
            return


        # ── Camera voice command intercept ──────────────────────────────
        # (phrase lists are module-level constants _CAM_SNAP_PHRASES / _CAM_QUESTION_PHRASES)
        cmd_low = command.lower()
        _cam_frame_path = os.path.join(
            tempfile.gettempdir(), "jarvis_cam_ask.jpg"
        )
        _has_live_frame = os.path.exists(_cam_frame_path)

        # Snapshot request via voice → capture frame from GUI camera
        if any(ph in cmd_low for ph in _CAM_SNAP_PHRASES):
            if self.gui and hasattr(self.gui, "_cam_last_img") and self.gui._cam_last_img:
                self.gui._cam_last_img.save(_cam_frame_path)
                self.brain._last_cam_image = _cam_frame_path
                _has_live_frame = True
                response = f"Got it — I've captured the photo, {USER_NAME}. What would you like to know about it?"
                if self.gui:
                    self.gui.add_jarvis_message(response)
                self._deliver_reply(response, turn_token)
                return
            elif self.gui and not (hasattr(self.gui, "_cam_running") and self.gui._cam_running):
                response = f"The camera isn't open yet, {USER_NAME}. Click the CAMERA tab and press START CAMERA first."
                if self.gui:
                    self.gui.add_jarvis_message(response)
                self._deliver_reply(response, turn_token)
                return

        # Camera question via voice → use last frame for vision
        if any(ph in cmd_low for ph in _CAM_QUESTION_PHRASES) and _has_live_frame:
            # Auto-capture latest frame if camera is running
            if self.gui and hasattr(self.gui, "_cam_last_img") and self.gui._cam_last_img:
                self.gui._cam_last_img.save(_cam_frame_path)
                self.brain._last_cam_image = _cam_frame_path
            if hasattr(self.brain, "_last_cam_image") and self.brain._last_cam_image:
                if self.gui:
                    self.gui.set_status("thinking")
                try:
                    response = self.brain.ai.chat_with_image(command, self.brain._last_cam_image, voice_mode=voice_source)
                except Exception as exc:
                    log.error(f"Vision query error: {exc}")
                    response = f"I couldn't analyze the camera image, {USER_NAME}: {exc}"
                if self.memory:
                    self.memory.add_history(command, response)
                if self.gui:
                    self.gui.add_jarvis_message(response)
                self._deliver_reply(response, turn_token)
                return
        # ── End camera voice intercept ───────────────────────────────────
        if self.gui:
            self.gui.set_status("thinking")
            if not already_displayed:   # voice commands: show recognized text
                self.gui.add_user_message(command)

        log.info(f"Processing: {command}")
        # Event Bus (Phase A): publish the intent. Additive + crash-proof (publish_safe).
        publish_safe("cognition.intent",
                     {"text": command, "voice": voice_source},
                     source="core_loop", correlation_id=str(turn_token))
        try:
            response = self.brain.process(command, voice_mode=voice_source)
        except Exception as exc:
            log.error(f"Brain error: {exc}")
            response = f"Something went wrong, {USER_NAME}: {exc}"

        if not response:
            response = f"Done, {USER_NAME}."

        # Event Bus (Phase A): publish the action result.
        publish_safe("action.result",
                     {"text": response, "voice": voice_source},
                     source="core_loop", correlation_id=str(turn_token))

        if self.memory:
            self.memory.add_history(command, response)
        if self.gui:
            self.gui.add_jarvis_message(response)

        self._deliver_reply(response, turn_token)

    def _claim_reply_token(self) -> int:
        with self._reply_lock:
            self._reply_token += 1
            return self._reply_token

    def _interrupt_speech(self):
        if self.speaker and hasattr(self.speaker, "stop") and getattr(self.speaker, "is_speaking", False):
            self.speaker.stop(clear_queue=True)

    def _deliver_reply(self, text: str, token: int):
        if self.gui:
            self.gui.set_status("speaking")

        if self.speaker:
            self.speaker.speak(
                text,
                blocking=False,
                interrupt=False,
                on_complete=lambda interrupted=False, reply_token=token: self._finish_reply(reply_token),
            )
            return

        log.info("[%s] %s", JARVIS_NAME, text)
        self._finish_reply(token)

    def _finish_reply(self, token: int):
        with self._reply_lock:
            if token != self._reply_token:
                return

        if self.listener and hasattr(self.listener, "keep_active"):
            self.listener.keep_active()

        if self.gui:
            if self.listener and (
                getattr(self.listener, "always_listening", False)
                or getattr(self.listener, "active_mode", False)
            ):
                self.gui.set_status("listening")
            else:
                self.gui.set_status("sleeping")

    def _speak(self, text: str):
        if self.speaker:
            self.speaker.speak(text)
        else:
            log.info("[%s] %s", JARVIS_NAME, text)

    def on_wake(self, acknowledge: bool = True):
        if self.gui:
            self.gui.set_status("listening")
        if acknowledge:
            if self.gui:
                self.gui.add_jarvis_message(WAKE_REPLY)
            if not (self.speaker and hasattr(self.speaker, "acknowledge") and self.speaker.acknowledge()):
                self._speak(WAKE_REPLY)
        if self.listener and hasattr(self.listener, "keep_active"):
            self.listener.keep_active()
