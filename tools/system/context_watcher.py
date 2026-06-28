"""
tools/system/context_watcher.py
Runs a background thread to monitor the active Windows GUI window.
Injects the current context into the Brain memory so Jarvis knows what the user is looking at.
"""
import threading
import time
import ctypes
from config.logger import get_logger
from shared_core import publish_safe

log = get_logger("system.context")

class ContextWatcher:
    def __init__(self, brain):
        self.brain = brain
        self._running = False
        self._thread = None
        self.current_window = ""

    def _get_active_window_title(self) -> str:
        try:
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            buff = ctypes.create_unicode_buffer(length + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, buff, length + 1)
            return buff.value
        except Exception:
            return ""

    def _watch_loop(self):
        log.info("ContextWatcher started.")
        while self._running:
            title = self._get_active_window_title()
            if title and title != self.current_window:
                self.current_window = title
                # Inject into brain memory (legacy path — unchanged)
                if not hasattr(self.brain, "volatile_memory"):
                    self.brain.volatile_memory = {}
                self.brain.volatile_memory["active_window"] = title
                # Event Bus (Phase A): publish the perception. Additive + crash-proof.
                publish_safe("perception.os.active_window",
                             {"title": title}, source="context_watcher")
            time.sleep(2.0)  # Check every 2 seconds

    def start(self):
        if self._running: return
        self._running = True
        self._thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)
