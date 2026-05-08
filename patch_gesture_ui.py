"""patch_gesture_ui.py — add GESTURE CONTROL toggle button and live gesture status to UI"""
import os

ui_path = os.path.join(os.path.dirname(__file__), "ui", "interface.py")
ui = open(ui_path, "r", encoding="utf-8").read()

# ── 1. Add _gesture_ctrl attribute initialization ─────────────────────────
OLD_INIT = '        self._cam_running   = False\n        self._cam_cap       = None\n        self._cam_photo_ref = None\n        self._cam_last_img  = None   # PIL Image of last frame'
NEW_INIT = (
    '        self._cam_running   = False\n'
    '        self._cam_cap       = None\n'
    '        self._cam_photo_ref = None\n'
    '        self._cam_last_img  = None   # PIL Image of last frame\n'
    '        self._cam_last_frame_raw = None\n'
    '        self._gesture_ctrl  = None   # Set by main.py after build_jarvis\n'
    '        self._gesture_active = False'
)
if "_gesture_ctrl  = None" not in ui:
    ui = ui.replace(OLD_INIT, NEW_INIT, 1)
    print("Step 1: gesture attrs added ✓")
else:
    print("Step 1: already present ✓")

# ── 2. Add GESTURE CONTROL button to sidebar (after CAMERA button) ────────
OLD_BTN = '        btn(parent, "\U0001f4f7  CAMERA",   PURPLE, TEXT1, self._open_camera_tab)'
NEW_BTN = (
    '        btn(parent, "\U0001f4f7  CAMERA",   PURPLE, TEXT1, self._open_camera_tab)\n'
    '        self._gesture_btn = btn(parent, "\U0001f590  GESTURE CTRL", BG2, TEXT2, self._toggle_gesture_control)'
)
if "_toggle_gesture_control" not in ui:
    if OLD_BTN in ui:
        ui = ui.replace(OLD_BTN, NEW_BTN, 1)
        print("Step 2: GESTURE CTRL button added ✓")
    else:
        print("Step 2: WARNING - could not find CAMERA button to insert after")
else:
    print("Step 2: already present ✓")

# ── 3. Add gesture status var display in camera tab (after cam_status_var) ─
OLD_STATUS = (
    '        # Status label\n'
    '        self._cam_status_var = tk.StringVar(value="Camera offline")\n'
    '        tk.Label(f, textvariable=self._cam_status_var,\n'
    '                 font=self._fonts["body_sm"], fg=PURPLE, bg=BG0\n'
    '                ).grid(row=3, column=0, pady=(0, 4))'
)
NEW_STATUS = (
    '        # Status labels\n'
    '        self._cam_status_var = tk.StringVar(value="Camera offline")\n'
    '        tk.Label(f, textvariable=self._cam_status_var,\n'
    '                 font=self._fonts["body_sm"], fg=PURPLE, bg=BG0\n'
    '                ).grid(row=3, column=0, pady=(0, 2))\n'
    '\n'
    '        self._gesture_status_var = tk.StringVar(value="\u2014  Gesture control off")\n'
    '        tk.Label(f, textvariable=self._gesture_status_var,\n'
    '                 font=self._fonts["body_sm"], fg=GREEN, bg=BG0\n'
    '                ).grid(row=4, column=0, pady=(0, 4))\n'
    '\n'
    '        # Gesture legend\n'
    '        legend_f = tk.Frame(f, bg=BG0)\n'
    '        legend_f.grid(row=5, column=0, sticky="ew", padx=12, pady=(0, 8))\n'
    '        tk.Label(legend_f, text="GESTURE LEGEND", font=self._fonts["section"],\n'
    '                 fg=TEXT2, bg=BG0).pack(anchor="w")\n'
    '        gestures = [\n'
    '            ("\u261d  Index only",       "Move cursor"),\n'
    '            ("\U0001f90f  Pinch",              "Left click"),\n'
    '            ("\u270c  Index+Middle",     "Right click"),\n'
    '            ("\U0001f91a  Open palm",          "Scroll up"),\n'
    '            ("\u270a  Fist",               "Scroll down"),\n'
    '            ("\U0001f44d  Thumb up",           "Volume up"),\n'
    '            ("\U0001f44e  Thumb down",         "Volume down"),\n'
    '            ("\U0001f918  Rock sign",           "Screenshot"),\n'
    '            ("\U0001f590  All up + wrist high", "Wake JARVIS"),\n'
    '        ]\n'
    '        for g, action in gestures:\n'
    '            row_f = tk.Frame(legend_f, bg=BG0)\n'
    '            row_f.pack(fill="x", pady=1)\n'
    '            tk.Label(row_f, text=g, font=self._fonts["body_sm"],\n'
    '                     fg=TEXT1, bg=BG0, width=22, anchor="w").pack(side="left")\n'
    '            tk.Label(row_f, text=action, font=self._fonts["body_sm"],\n'
    '                     fg=CYAN, bg=BG0).pack(side="left")'
)

if "_gesture_status_var" not in ui:
    if OLD_STATUS in ui:
        ui = ui.replace(OLD_STATUS, NEW_STATUS, 1)
        print("Step 3: gesture status + legend added ✓")
    else:
        print("Step 3: WARNING - could not find status label block")
else:
    print("Step 3: already present ✓")

# ── 4. Add _toggle_gesture_control method ────────────────────────────────
GESTURE_METHOD = '''
    def _toggle_gesture_control(self):
        """Toggle gesture recognition on/off."""
        if not self._gesture_ctrl:
            self.show_notification("Gesture Control",
                "Gesture controller not initialized.\\nRestart JARVIS to enable it.")
            return

        active = self._gesture_ctrl.toggle(cam_index=0)
        self._gesture_active = active

        if active:
            self._gesture_btn.configure(text="\\U0001f590  GESTURE ON", bg=GREEN, fg=BG0)
            self._gesture_status_var.set("\\U0001f4f7  Gesture control ACTIVE")
            # Also open camera tab and start camera if not running
            self._open_camera_tab()
            if not self._cam_running:
                self._start_camera()
        else:
            self._gesture_btn.configure(text="\\U0001f590  GESTURE CTRL", bg=BG2, fg=TEXT2)
            self._gesture_status_var.set("\\u2014  Gesture control off")

'''

if "_toggle_gesture_control" not in ui:
    # Insert before _open_camera_tab
    TARGET = "    def _open_camera_tab(self):"
    if TARGET in ui:
        ui = ui.replace(TARGET, GESTURE_METHOD + TARGET, 1)
        print("Step 4: _toggle_gesture_control method added ✓")
    else:
        print("Step 4: WARNING - could not find _open_camera_tab to insert before")
else:
    print("Step 4: already present ✓")

open(ui_path, "w", encoding="utf-8").write(ui)
print("\nUI gesture patch complete!")
