"""
tools/automation/workflow_recorder.py
Keyboard & Mouse Macro Recorder + Replayer for JarvisX.

Records all keyboard/mouse events via pynput.
Saves as named workflows in memory.manager.
Replays with realistic timing.

Voice: "Jarvis, start recording"  → starts
       "Jarvis, stop recording"   → saves workflow
       "Jarvis, replay morning routine" → replays
"""
from __future__ import annotations
import json
import time
import threading
import logging
from typing import Optional

log = logging.getLogger("workflow_recorder")

# Minimum interval between events when replaying (seconds)
_MIN_REPLAY_INTERVAL = 0.02
_MAX_REPLAY_INTERVAL = 2.0   # cap long pauses


class WorkflowRecorder:
    """
    Records and replays keyboard + mouse workflow macros.

    Usage:
        recorder = WorkflowRecorder(memory_manager)
        recorder.start_recording()     # begin capture
        # ... user does stuff ...
        recorder.stop_recording("morning_routine")   # save with name
        recorder.replay("morning_routine")           # play back
    """

    def __init__(self, memory=None):
        self.memory = memory
        self.available: bool = False
        self._recording = False
        self._events: list[dict] = []
        self._last_event_time: float = 0.0
        self._listener_kb = None
        self._listener_mouse = None
        self._lock = threading.Lock()
        self._init_backend()

    def _init_backend(self):
        try:
            import pynput  # noqa: F401
            self.available = True
            log.info("WorkflowRecorder: pynput ready.")
        except ImportError:
            log.warning(
                "WorkflowRecorder: pynput not installed. "
                "Run: pip install pynput   (workflow recording disabled)"
            )

    # ── Recording ─────────────────────────────────────────────────────────────

    def start_recording(self) -> str:
        """Start recording keyboard + mouse events."""
        if not self.available:
            return "Workflow recording not available (install pynput)."
        if self._recording:
            return "Already recording."
        with self._lock:
            self._events.clear()
            self._last_event_time = time.time()
            self._recording = True
        self._start_listeners()
        log.info("WorkflowRecorder: recording started.")
        return "Recording started. Say 'stop recording' when done."

    def stop_recording(self, name: str = "unnamed") -> str:
        """Stop recording and save as a named workflow."""
        if not self._recording:
            return "Not recording."
        self._recording = False
        self._stop_listeners()
        with self._lock:
            events = list(self._events)
        if not events:
            return "No events recorded."
        # Save to memory
        result = self._save_workflow(name, events)
        log.info(f"WorkflowRecorder: saved '{name}' with {len(events)} event(s).")
        return result

    def is_recording(self) -> bool:
        return self._recording

    # ── Replay ────────────────────────────────────────────────────────────────

    def replay(self, name: str) -> str:
        """Replay a saved workflow by name."""
        if not self.available:
            return "Workflow replay not available (install pynput)."
        events = self._load_workflow(name)
        if not events:
            return f"Workflow '{name}' not found."
        threading.Thread(
            target=self._replay_events, args=(events, name), daemon=True
        ).start()
        return f"Replaying workflow '{name}' ({len(events)} events)."

    def list_workflows(self) -> list[str]:
        """Return names of all saved workflows."""
        if not self.memory or not hasattr(self.memory, "list_workflows"):
            return []
        try:
            return [w["name"] for w in self.memory.list_workflows()]
        except Exception:
            return []

    # ── Internal ──────────────────────────────────────────────────────────────

    def _start_listeners(self):
        from pynput import keyboard, mouse

        def on_key_press(key):
            if not self._recording:
                return
            self._record_event("key_press", {"key": self._key_str(key)})

        def on_key_release(key):
            if not self._recording:
                return
            self._record_event("key_release", {"key": self._key_str(key)})

        def on_mouse_click(x, y, button, pressed):
            if not self._recording:
                return
            self._record_event("mouse_click", {
                "x": x, "y": y,
                "button": str(button),
                "pressed": pressed,
            })

        def on_mouse_scroll(x, y, dx, dy):
            if not self._recording:
                return
            self._record_event("mouse_scroll", {"x": x, "y": y, "dx": dx, "dy": dy})

        self._listener_kb = keyboard.Listener(
            on_press=on_key_press, on_release=on_key_release
        )
        self._listener_mouse = mouse.Listener(
            on_click=on_mouse_click, on_scroll=on_mouse_scroll
        )
        self._listener_kb.start()
        self._listener_mouse.start()

    def _stop_listeners(self):
        for listener in (self._listener_kb, self._listener_mouse):
            if listener and listener.is_alive():
                try:
                    listener.stop()
                except Exception:
                    pass

    def _record_event(self, event_type: str, data: dict):
        now = time.time()
        with self._lock:
            delay = now - self._last_event_time
            self._last_event_time = now
            self._events.append({
                "type": event_type,
                "data": data,
                "delay": min(delay, _MAX_REPLAY_INTERVAL),
            })

    def _replay_events(self, events: list[dict], name: str):
        from pynput import keyboard, mouse
        kb = keyboard.Controller()
        ms = mouse.Controller()
        log.info(f"WorkflowRecorder: replaying '{name}'...")
        for event in events:
            delay = max(_MIN_REPLAY_INTERVAL, event.get("delay", 0.1))
            time.sleep(delay)
            etype = event.get("type", "")
            data = event.get("data", {})
            try:
                if etype == "key_press":
                    kb.press(self._parse_key(data.get("key", "")))
                elif etype == "key_release":
                    kb.release(self._parse_key(data.get("key", "")))
                elif etype == "mouse_click":
                    x, y = int(data.get("x", 0)), int(data.get("y", 0))
                    btn = self._parse_button(data.get("button", ""))
                    ms.position = (x, y)
                    if data.get("pressed"):
                        ms.press(btn)
                    else:
                        ms.release(btn)
                elif etype == "mouse_scroll":
                    ms.scroll(data.get("dx", 0), data.get("dy", 0))
            except Exception as e:
                log.debug(f"WorkflowRecorder replay event error: {e}")
        log.info(f"WorkflowRecorder: replay '{name}' complete.")

    def _save_workflow(self, name: str, events: list[dict]) -> str:
        if self.memory and hasattr(self.memory, "save_workflow"):
            steps = [json.dumps(e) for e in events]
            return self.memory.save_workflow(
                name, steps,
                description=f"Recorded macro: {len(events)} events",
                tags="macro,recorded",
            )
        return f"Workflow '{name}' recorded ({len(events)} events) — memory not available to save."

    def _load_workflow(self, name: str) -> list[dict]:
        if not self.memory or not hasattr(self.memory, "get_workflow"):
            return []
        wf = self.memory.get_workflow(name)
        if not wf:
            return []
        events = []
        for step in wf.get("steps", []):
            try:
                events.append(json.loads(step))
            except Exception:
                pass
        return events

    @staticmethod
    def _key_str(key) -> str:
        try:
            return key.char or str(key)
        except AttributeError:
            return str(key)

    @staticmethod
    def _parse_key(key_str: str):
        from pynput import keyboard
        try:
            return keyboard.Key[key_str.replace("Key.", "")]
        except (KeyError, AttributeError):
            try:
                return keyboard.KeyCode.from_char(key_str)
            except Exception:
                return keyboard.Key.space

    @staticmethod
    def _parse_button(btn_str: str):
        from pynput.mouse import Button
        if "right" in btn_str.lower():
            return Button.right
        if "middle" in btn_str.lower():
            return Button.middle
        return Button.left
