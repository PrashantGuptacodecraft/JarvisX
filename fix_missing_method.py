"""fix_missing_method.py — add the missing _toggle_gesture_control method"""
import os, sys
sys.stdout.reconfigure(encoding="utf-8")

path = os.path.join(os.path.dirname(__file__), "ui", "interface.py")
c = open(path, "r", encoding="utf-8").read()

METHOD = '''
    def _toggle_gesture_control(self):
        """Toggle gesture recognition on/off."""
        if not self._gesture_ctrl:
            self.show_notification("Gesture Control",
                "Gesture controller not initialized.\\nRestart JARVIS to enable it.")
            return

        active = self._gesture_ctrl.toggle(cam_index=0)
        self._gesture_active = active

        if active:
            if self._gesture_btn:
                self._gesture_btn.configure(text="\\U0001f590  GESTURE ON", bg=GREEN, fg=BG0)
            if self._gesture_status_var:
                self._gesture_status_var.set("Gesture control ACTIVE")
            self._open_camera_tab()
            if not self._cam_running:
                self._start_camera()
        else:
            if self._gesture_btn:
                self._gesture_btn.configure(text="\\U0001f590  GESTURE CTRL", bg=BG2, fg=TEXT2)
            if self._gesture_status_var:
                self._gesture_status_var.set("Gesture control off")

'''

TARGET = "    def _open_camera_tab(self):"
if "_toggle_gesture_control" not in c:
    c = c.replace(TARGET, METHOD + TARGET, 1)
    open(path, "w", encoding="utf-8").write(c)
    print("FIXED: _toggle_gesture_control method added")
else:
    print("Method already present")
