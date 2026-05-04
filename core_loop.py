"""core_loop.py — Command processor: queue → brain → speaker → GUI."""
import queue, threading
from config.settings import USER_NAME, JARVIS_NAME
from config.logger import get_logger
log = get_logger("core_loop")

WAKE_REPLY  = f"Hey {USER_NAME}, I'm here — what do you need?"
SLEEP_REPLY = f"Going to standby. Say 'Hello {JARVIS_NAME}' whenever you need me."
ALWAYS_LISTEN_REPLY = f"Always listening mode enabled, {USER_NAME}. You can speak commands without the wake word."
WAKE_MODE_REPLY = f"Wake word mode enabled, {USER_NAME}. Say 'Hello {JARVIS_NAME}' when you need me."


class CoreLoop:
    def __init__(self, command_queue: queue.Queue, brain, speaker, gui=None, memory=None):
        self.queue   = command_queue
        self.brain   = brain
        self.speaker = speaker
        self.gui     = gui
        self.memory  = memory
        self.listener = None   # Set by main after listener is created

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
            except Exception as e:
                log.error(f"Core loop error: {e}")

    def _process(self, command: str):
        command = command.strip()
        if command == "__WAKE__":
            self.on_wake()
            return
        if command == "__VOICE_ALWAYS_ON__":
            if self.gui:
                self.gui.set_status("listening")
            self._speak(ALWAYS_LISTEN_REPLY)
            return
        if command == "__VOICE_WAKE_MODE__":
            if self.gui:
                self.gui.set_status("sleeping")
            self._speak(WAKE_MODE_REPLY)
            return
        if command == "__SLEEP__":
            if self.gui:
                self.gui.set_status("sleeping")
            self._speak(SLEEP_REPLY)
            return
        if command == "__CANCEL__":
            if self.brain:
                self.brain.pending = None
            self._speak(f"Cancelled, {USER_NAME}.")
            return
        if not command:
            return

        if self.gui:
            self.gui.set_status("thinking")
            self.gui.add_user_message(command)

        log.info(f"Processing: {command}")
        try:
            response = self.brain.process(command)
        except Exception as e:
            log.error(f"Brain error: {e}")
            response = f"Something went wrong, {USER_NAME}: {e}"

        if not response:
            response = f"Done, {USER_NAME}."

        if self.memory:
            self.memory.add_history(command, response)
        if self.gui:
            self.gui.add_jarvis_message(response)
            self.gui.set_status("speaking")

        self._speak(response)

        # Stay in active conversation mode after every reply
        if self.listener and hasattr(self.listener, "keep_active"):
            self.listener.keep_active()

        if self.gui:
            if self.listener and (getattr(self.listener, "always_listening", False) or getattr(self.listener, "active_mode", False)):
                self.gui.set_status("listening")
            else:
                self.gui.set_status("sleeping")

    def _speak(self, text: str):
        if self.speaker:
            self.speaker.speak(text)
        else:
            print(f"\n[{JARVIS_NAME}]: {text}\n")

    def on_wake(self):
        if self.gui:
            self.gui.set_status("listening")
            self.gui.add_jarvis_message(WAKE_REPLY)
        self._speak(WAKE_REPLY)
        if self.listener and hasattr(self.listener, "keep_active"):
            self.listener.keep_active()
