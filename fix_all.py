"""fix_all.py — Fix vision (force Gemini) + fix UI black panel"""
import os, sys
sys.stdout.reconfigure(encoding="utf-8")

BASE = os.path.dirname(__file__)

# ─── FIX 1: Force Gemini for vision in ai_client.py ─────────────────────────
ai_path = os.path.join(BASE, "brain", "ai_client.py")
ai = open(ai_path, "r", encoding="utf-8").read()

OLD_VISION_CHECK = '        # ── Gemini Vision (primary) ──────────────────────────\n        if self.provider == "gemini" and self.client:'
NEW_VISION_CHECK = '''        # ── Gemini Vision (always try first regardless of primary provider) ──
        # Build a dedicated Gemini client for vision even if primary is Groq/etc.
        _gemini_client = self.client if self.provider == "gemini" else None
        if not _gemini_client:
            try:
                from google import genai as _genai
                _gemini_client = _genai.Client(api_key=GEMINI_KEY) if GEMINI_KEY else None
            except Exception:
                _gemini_client = None

        if _gemini_client:'''

if OLD_VISION_CHECK in ai:
    ai = ai.replace(OLD_VISION_CHECK, NEW_VISION_CHECK, 1)
    # Fix the self.client references inside the vision block to use _gemini_client
    ai = ai.replace(
        '                    resp = self.client.models.generate_content(model=model_name, contents=contents)',
        '                    resp = _gemini_client.models.generate_content(model=model_name, contents=contents)',
        1
    )
    open(ai_path, "w", encoding="utf-8").write(ai)
    print("FIX 1: Vision now always tries Gemini first (even if provider=groq)")
elif "_gemini_client" in ai:
    print("FIX 1: Already applied")
else:
    print("FIX 1: WARNING - could not find vision check block")

# ─── FIX 2: Also fix the short path issue (PRASHA~1 → full path) ─────────────
# The brain intercept already handles the path, but normalize it
core_path = os.path.join(BASE, "brain", "core.py")
core = open(core_path, "r", encoding="utf-8").read()

PATH_NORM = '''
        # Normalize short DOS path (PRASHA~1) to full path
        if cam_match:
            import pathlib as _pl
            try:
                img_path = str(_pl.Path(cam_match.group(1).strip()).resolve())
            except Exception:
                img_path = cam_match.group(1).strip()
'''

if "Normalize short DOS path" not in core and "cam_match = _re.match(" in core:
    core = core.replace(
        "        if cam_match:\n            img_path = cam_match.group(1).strip()",
        "        if cam_match:\n            import pathlib as _pl\n            try:\n                img_path = str(_pl.Path(cam_match.group(1).strip()).resolve())\n            except Exception:\n                img_path = cam_match.group(1).strip()"
    )
    open(core_path, "w", encoding="utf-8").write(core)
    print("FIX 2: Short DOS path normalization added")
else:
    print("FIX 2: Already applied or not needed")

# ─── FIX 3: Wrap all tab builders in try/except so one crash can't black out ─
ui_path = os.path.join(BASE, "ui", "interface.py")
ui = open(ui_path, "r", encoding="utf-8").read()

OLD_TABS = """        self._build_chat_tab()
        self._build_terminal_tab()
        self._build_system_tab()
        self._build_memory_tab()
        self._build_camera_tab()"""

NEW_TABS = """        for _tab_builder, _tab_name in [
            (self._build_chat_tab,     "CHAT"),
            (self._build_terminal_tab, "TERMINAL"),
            (self._build_system_tab,   "SYSTEM"),
            (self._build_memory_tab,   "MEMORY"),
            (self._build_camera_tab,   "CAMERA"),
        ]:
            try:
                _tab_builder()
            except Exception as _e:
                import traceback
                traceback.print_exc()
                import tkinter as _tk
                _err_f = _tk.Frame(self._nb, bg="#0a0014")
                self._nb.add(_err_f, text=f"  {_tab_name}  ")
                _tk.Label(_err_f, text=f"{_tab_name} tab error:\\n{_e}",
                          fg="#ff4444", bg="#0a0014").pack(pady=40)"""

if "_tab_builder" not in ui:
    if OLD_TABS in ui:
        ui = ui.replace(OLD_TABS, NEW_TABS, 1)
        print("FIX 3: Tab builders wrapped in try/except")
    else:
        print("FIX 3: WARNING - could not find tab build block")
else:
    print("FIX 3: Already applied")

# ─── FIX 4: Ensure _gesture_btn and _gesture_status_var have safe defaults ───
if "self._gesture_btn = None" not in ui:
    ui = ui.replace(
        "        self._gesture_ctrl  = None   # Set by main.py after build_jarvis\n        self._gesture_active = False",
        "        self._gesture_ctrl   = None\n        self._gesture_active = False\n        self._gesture_btn    = None\n        self._gesture_status_var = None"
    )
    print("FIX 4: Added safe defaults for gesture attrs")
else:
    print("FIX 4: Already applied")

# Make _toggle_gesture_control safe against None _gesture_status_var
if "_gesture_status_var" in ui and "if self._gesture_status_var" not in ui:
    ui = ui.replace(
        '        self._gesture_status_var.set("\\U0001f4f7  Gesture control ACTIVE")',
        '        if self._gesture_status_var: self._gesture_status_var.set("Gesture control ACTIVE")'
    )
    ui = ui.replace(
        '        self._gesture_status_var.set("\\u2014  Gesture control off")',
        '        if self._gesture_status_var: self._gesture_status_var.set("Gesture control off")'
    )

open(ui_path, "w", encoding="utf-8").write(ui)
print("\nAll fixes applied!")
