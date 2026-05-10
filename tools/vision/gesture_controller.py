"""
tools/vision/gesture_controller.py
JARVIS-integrated gesture controller.
Bridges GestureEngine actions → command_queue / system actions.
"""
import logging
import time

from tools.vision.gesture_engine import (
    GestureEngine,
    G_CURSOR, G_CLICK, G_RCLICK, G_SCROLL_U, G_SCROLL_D,
    G_VOL_UP, G_VOL_DN, G_WAKE, G_SHOT, G_SHOT_SEL, G_NONE,
)

log = logging.getLogger("gesture_controller")


GESTURE_LABELS = {
    G_CURSOR:   "☝  Cursor Move",
    G_CLICK:    "🤏  Left Click",
    G_RCLICK:   "✌  Right Click",
    G_SCROLL_U: "🤚  Scroll Up",
    G_SCROLL_D: "✊  Scroll Down",
    G_VOL_UP:   "👍  Volume Up",
    G_VOL_DN:   "👎  Volume Down",
    G_WAKE:     "🖐  Wake JARVIS",
    G_SHOT:     "🤘  Screenshot",
    G_SHOT_SEL: "🤘  Area Screenshot",
    G_NONE:     "—  No Gesture",
}

GESTURE_DESCRIPTIONS = {
    G_CURSOR:   "☝  Index finger only",
    G_CLICK:    "🤏  Pinch (thumb+index) or curl index",
    G_RCLICK:   "✌  Index+middle+ring (peace+ring)",
    G_SCROLL_U: "🖐  Open palm (4 fingers) — scroll up",
    G_SCROLL_D: "✊  Fist (all fingers closed)",
    G_VOL_UP:   "👍  Thumb up only",
    G_VOL_DN:   "👎  Thumb down only",
    G_SHOT:     "🤘  Rock sign (index+pinky) — quick tap for screenshot",
    G_SHOT_SEL: "🤘  Rock sign held 0.6s → area select",
    G_WAKE:     "🖐  Open palm with wrist high — wake JARVIS",
    G_NONE:     "—  No Gesture",
}

GESTURE_LEGEND = [
    ("☝  Index finger only",  "Move cursor"),
    ("🤏  Pinch thumb+index or curl index",  "Left click"),
    ("✌  Index + middle",     "Right click"),
    ("🤚  Open palm (5 fingers)", "Scroll up"),
    ("✊  Fist (all closed)",  "Scroll down"),
    ("👍  Thumb up only",      "Volume up"),
    ("👎  All fingers closed (fist-down)", "Volume down"),
    ("🤘  Index + pinky up",   "Screenshot"),
    ("🖐  All up + wrist high","Activate JARVIS"),
]


class GestureController:
    """
    Manages the GestureEngine lifecycle and dispatches actions
    to system controls and the JARVIS command queue.
    """

    def __init__(self, command_queue=None, gui=None):
        self.command_queue = command_queue
        self.gui = gui
        self._engine: GestureEngine | None = None
        self._active = False
        self._last_gesture_label = "—  No Gesture"

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def is_active(self) -> bool:
        return self._active

    def start(self, cam_index: int = 0) -> bool:
        """Start gesture recognition. Returns True on success."""
        if self._active:
            return True
        self._engine = GestureEngine(
            action_callback=self._on_gesture,
            frame_callback=self._on_frame,
            cam_index=cam_index,
        )
        ok = self._engine.start()
        if ok:
            self._active = True
            log.info("Gesture control ACTIVE")
            if self.gui and hasattr(self.gui, "show_notification"):
                self.gui.show_notification(
                    "Gesture Control ON",
                    "Hand gestures are now active!\n"
                    "Show your hand to the camera to start.",
                )
        return ok

    def stop(self):
        """Stop gesture recognition."""
        self._active = False
        if self._engine:
            self._engine.stop()
            self._engine = None
        log.info("Gesture control STOPPED")

    def toggle(self, cam_index: int = 0) -> bool:
        """Toggle on/off. Returns new state (True = active)."""
        if self._active:
            self.stop()
            return False
        return self.start(cam_index=cam_index)

    def toggle_draw_mode(self) -> bool:
        """Activate/deactivate Air Drawing Mode directly via button or voice.
        Starts gesture engine automatically if not already running.
        Returns True if draw mode is now ON.
        """
        if not self._active:
            # Start gesture engine first if not running
            self.start(cam_index=0)
        if self._engine and hasattr(self._engine, "toggle_draw_mode"):
            on = self._engine.toggle_draw_mode()
            if self.gui and hasattr(self.gui, "show_notification"):
                if on:
                    self.gui.show_notification(
                        "✏ Air Drawing ON",
                        "Fullscreen canvas open.\n"
                        "☝ Index = Draw  ✌ Peace = Lift pen\n"
                        "✊ Fist (hold) = Save & Exit",
                    )
                else:
                    self.gui.show_notification("Air Drawing OFF", "Canvas closed and saved.")
            return on
        log.warning("toggle_draw_mode: engine not available")
        return False

    # ── Callbacks ─────────────────────────────────────────────────────────────

    def _on_gesture(self, gesture: str):
        """Dispatches a confirmed gesture to the appropriate action."""
        log.info(f"Executing gesture: {gesture}")

        try:
            import pyautogui
            pyautogui.FAILSAFE = True

            if gesture == G_CLICK:
                self._perform_mouse_click(pyautogui, button="left")

            elif gesture == G_RCLICK:
                self._perform_mouse_click(pyautogui, button="right")

            elif gesture == G_SCROLL_U:
                pyautogui.scroll(5)

            elif gesture == G_SCROLL_D:
                pyautogui.scroll(-5)

            elif gesture == G_VOL_UP:
                pyautogui.press("volumeup")
                pyautogui.press("volumeup")
                pyautogui.press("volumeup")

            elif gesture == G_VOL_DN:
                pyautogui.press("volumedown")
                pyautogui.press("volumedown")
                pyautogui.press("volumedown")

            elif gesture == G_SHOT:
                # Quick tap = Win+Shift+S snip
                pyautogui.hotkey("win", "shift", "s")

            elif gesture == G_SHOT_SEL:
                # Region screenshot completed by engine — notify via JARVIS
                if self.command_queue:
                    self.command_queue.put("Screenshot saved.")

            elif gesture == G_WAKE:
                if self.command_queue:
                    self.command_queue.put("__WAKE__")
                else:
                    pyautogui.hotkey("ctrl", "space")   # fallback

        except Exception as e:
            log.error(f"Gesture action error ({gesture}): {e}")

        # Update GUI label
        if self.gui and hasattr(self.gui, "_gesture_status_var"):
            label = GESTURE_LABELS.get(gesture, gesture)
            try:
                self.gui._gesture_status_var.set(label)
            except Exception:
                pass

    def _perform_mouse_click(self, pyautogui_module, button: str = "left"):
        """Use a short press/release instead of an ultra-fast raw click."""
        pos = pyautogui_module.position()
        pyautogui_module.mouseDown(button=button)
        time.sleep(0.07)
        pyautogui_module.mouseUp(button=button)
        pyautogui_module.moveTo(pos.x, pos.y, duration=0)

    def _on_frame(self, rgb_frame, gesture: str):
        """Push annotated gesture frame to the camera canvas."""
        if not self.gui:
            return

        label = GESTURE_LABELS.get(gesture, gesture)
        if label != self._last_gesture_label:
            self._last_gesture_label = label
            if hasattr(self.gui, "_gesture_status_var"):
                try:
                    self.gui._gesture_status_var.set(label)
                except Exception:
                    pass

        if hasattr(self.gui, "root") and hasattr(self.gui, "_update_camera_frame"):
            try:
                self.gui.root.after(0, self.gui._update_camera_frame, rgb_frame)
            except Exception:
                pass
