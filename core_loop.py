"""core_loop.py - Command processor: queue -> brain -> speaker -> GUI."""

import queue
import threading

from config.logger import get_logger
from config.settings import JARVIS_NAME, USER_NAME

log = get_logger("core_loop")

WAKE_REPLY = "Listening."
SLEEP_REPLY = f"Going to standby. Say 'Hello {JARVIS_NAME}' whenever you need me."
ALWAYS_LISTEN_REPLY = f"Always listening mode enabled, {USER_NAME}. You can speak commands without the wake word."
WAKE_MODE_REPLY = f"Wake word mode enabled, {USER_NAME}. Say 'Hello {JARVIS_NAME}' when you need me."


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
        if command.startswith("__VOICE__:"):
            voice_source = True
            command = command[len("__VOICE__:"):].strip()
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

        if self.gui:
            self.gui.set_status("thinking")
            self.gui.add_user_message(command)

        log.info(f"Processing: {command}")
        try:
            response = self.brain.process(command, voice_mode=voice_source)
        except Exception as exc:
            log.error(f"Brain error: {exc}")
            response = f"Something went wrong, {USER_NAME}: {exc}"

        if not response:
            response = f"Done, {USER_NAME}."

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

        print(f"\n[{JARVIS_NAME}]: {text}\n")
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
            print(f"\n[{JARVIS_NAME}]: {text}\n")

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
