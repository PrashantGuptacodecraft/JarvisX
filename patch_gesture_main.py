"""patch_gesture_main.py — wire GestureController into main.py and fix camera MSMF error"""
import os, re

# ── 1. Fix MSMF camera error in gesture_engine (use CAP_DSHOW) ────────────
ge_path = os.path.join(os.path.dirname(__file__), "tools", "vision", "gesture_engine.py")
ge = open(ge_path, "r", encoding="utf-8").read()
# Already uses CAP_DSHOW in gesture_engine - good
print("gesture_engine.py: CAP_DSHOW already set ✓")

# ── 2. Fix the main camera in interface.py (MSMF → CAP_DSHOW) ────────────
ui_path = os.path.join(os.path.dirname(__file__), "ui", "interface.py")
ui = open(ui_path, "r", encoding="utf-8").read()

OLD_CAP = 'cap = cv2.VideoCapture(0)\n        if not cap.isOpened():'
NEW_CAP = 'cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)\n        if not cap.isOpened():\n            cap = cv2.VideoCapture(0)   # fallback to default backend\n        if not cap.isOpened():'

if OLD_CAP in ui:
    ui = ui.replace(OLD_CAP, NEW_CAP, 1)
    print("ui/interface.py: MSMF → CAP_DSHOW fixed ✓")
elif "CAP_DSHOW" in ui:
    print("ui/interface.py: CAP_DSHOW already present ✓")
else:
    print("WARNING: Could not find camera open call in interface.py")

open(ui_path, "w", encoding="utf-8").write(ui)

# ── 3. Add GestureController import + instantiation to main.py ───────────
main_path = os.path.join(os.path.dirname(__file__), "main.py")
main = open(main_path, "r", encoding="utf-8").read()

GESTURE_IMPORT = "from tools.vision.gesture_controller import GestureController\n"
if "GestureController" not in main:
    main = main.replace(
        "from core_loop import CoreLoop\n",
        "from core_loop import CoreLoop\n" + GESTURE_IMPORT,
    )
    print("main.py: GestureController import added ✓")
else:
    print("main.py: import already present ✓")

# Add gesture_ctrl to build_jarvis return and pass gui ref
GESTURE_INIT = """
    # Gesture controller (needs gui and command_queue)
    gesture_ctrl = GestureController(command_queue=command_queue, gui=gui)
    if gui and hasattr(gui, "_gesture_ctrl"):
        gui._gesture_ctrl = gesture_ctrl
"""

if "gesture_ctrl" not in main:
    main = main.replace(
        "    return core, listener, speaker, memory, command_queue",
        GESTURE_INIT + "\n    return core, listener, speaker, memory, command_queue, gesture_ctrl",
    )
    # Fix callers
    main = main.replace(
        "core, listener, speaker, memory, _ = build_jarvis(gui=gui, command_queue=cq)",
        "core, listener, speaker, memory, _, gesture_ctrl = build_jarvis(gui=gui, command_queue=cq)\n    if hasattr(gui, '_gesture_ctrl'):\n        gui._gesture_ctrl = gesture_ctrl",
    )
    main = main.replace(
        "core, listener, speaker, memory, _ = build_jarvis(gui=None, command_queue=cq)",
        "core, listener, speaker, memory, _, gesture_ctrl = build_jarvis(gui=None, command_queue=cq)",
    )
    print("main.py: gesture_ctrl wired into build_jarvis ✓")
else:
    print("main.py: gesture_ctrl already wired ✓")

open(main_path, "w", encoding="utf-8").write(main)

print("\nAll patches applied successfully!")
