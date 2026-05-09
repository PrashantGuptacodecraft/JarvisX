# J.A.R.V.I.S Hand Gesture Control System

![Python](https://img.shields.io/badge/Python-3.9+-blue) ![OpenCV](https://img.shields.io/badge/OpenCV-4.9-green) ![MediaPipe](https://img.shields.io/badge/MediaPipe-0.10-orange) ![License](https://img.shields.io/badge/License-MIT-purple) ![Status](https://img.shields.io/badge/Status-Production-brightgreen)

> A production-grade, zero-placeholder hand gesture control system with Voice+Gesture Fusion, Air Drawing, AR Overlays, and real-time Analytics Dashboard.

---

## Feature Table

| Feature | Module | Status |
|---|---|---|
| 21-landmark hand tracking | `core/hand_tracker.py` | ✅ |
| Joint-angle gesture classification | `core/gesture_classifier.py` | ✅ |
| Dual-layer EMA + vote smoothing | `core/gesture_buffer.py` | ✅ |
| Per-gesture cooldown guard | `core/gesture_guard.py` | ✅ |
| Non-linear accelerated cursor | `control/mouse_controller.py` | ✅ |
| Full keyboard controller | `control/keyboard_controller.py` | ✅ |
| Voice + Gesture Fusion | `core/voice_gesture_fusion.py` | ✅ |
| Air Drawing with shape snap | `core/air_drawing.py` | ✅ |
| Gesture Heatmap Dashboard | `analytics/heatmap_engine.py` | ✅ |
| Flask + SocketIO Analytics | `analytics/dashboard_server.py` | ✅ |
| AR Virtual Camera Overlay | `ui/ar_overlay.py` | ✅ |
| Iron Man–style HUD | `ui/hud_renderer.py` | ✅ |
| 4-Step Calibration Wizard | `calibration/calibration_wizard.py` | ✅ |

---

## Gesture Reference

| Gesture Name | Hand Pose | Action Triggered |
|---|---|---|
| `cursor_move` | Index finger extended alone | Move mouse cursor |
| `left_click` | Index + middle extended, tips close | Left mouse click |
| `double_click` | Index + middle close, quick repeat | Double click |
| `right_click` | Thumb + index pinch | Right mouse click |
| `freeze_cursor` | All 5 fingers open, palm toward camera | Freeze/unfreeze cursor |
| `scroll_up` | Fist, wrist tilted up | Scroll up (speed by tilt) |
| `scroll_down` | Fist, wrist tilted down | Scroll down |
| `swipe_left` | Peace sign swept left | Browser back / Alt+Left |
| `swipe_right` | Peace sign swept right | Browser forward / Alt+Right |
| `swipe_up` | 3 fingers swept up | Maximize window |
| `swipe_down` | 3 fingers swept down | Minimize window |
| `thumbs_up` | Thumb only extended, tip up | Volume up |
| `thumbs_down` | Thumb only extended, tip down | Volume down |
| `ok_sign` | Thumb+index loop, others extended | Enter key |
| `peace_sign` | Index+middle spread wide | Screenshot |
| `rock_sign` | Index+pinky extended | Toggle mode |
| `fist` | All fingers closed | Hold drag / Media stop |
| `drawing_mode` | Index alone held 450ms | Air drawing mode |

---

## Voice Fusion Command Table

| Voice Phrase | Gesture | Combined Action |
|---|---|---|
| "open" | cursor_move | Open file under cursor |
| "close" | fist | Close active window |
| "search" | peace_sign | Open browser search |
| "save" | ok_sign | Ctrl+S |
| "bigger" | swipe_up | Maximize window |
| "undo" | thumbs_down | Ctrl+Z |
| "screenshot" | peace_sign | Save screenshot |
| "jarvis" | rock_sign | Open AI chat |
| "play" | thumbs_up | Media play/pause |
| "stop" | fist | Media stop |
| "next" | swipe_right | Next track |
| "volume" | thumbs_up | Volume up |
| "volume" | thumbs_down | Volume down |
| "new" | peace_sign | New tab Ctrl+T |
| "back" | swipe_left | Browser back |
| "zoom" | ok_sign | Zoom in Ctrl++ |
| "copy" | peace_sign | Ctrl+C |
| "paste" | ok_sign | Ctrl+V |
| "select" | rock_sign | Ctrl+A |
| "delete" | thumbs_down | Delete key |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         CAMERA (cv2)                                │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ raw BGR frames
                    ┌──────────▼──────────┐
                    │   HandTracker        │  MediaPipe Hands
                    │  (hand_tracker.py)   │  21 landmarks × hand
                    └──────────┬──────────┘
                               │ (21,3) numpy array
                    ┌──────────▼──────────┐
                    │  FingerAnalyzer      │  Dot-product joint angles
                    │ (finger_analyzer.py) │  → FingerState (5 fingers)
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │ GestureClassifier    │  18 gesture rules
                    │(gesture_classifier)  │  velocity, pinch, hold
                    └──────────┬──────────┘
                               │ GestureResult (name, conf, xy)
          ┌────────────────────▼──────────────────────┐
          │             GestureBuffer                  │  5/7 vote + EMA
          │          (gesture_buffer.py)               │  dead zone, velocity
          └────────────────────┬──────────────────────┘
                               │ BufferedGesture
                    ┌──────────▼──────────┐
                    │   GestureGuard       │  Per-gesture cooldowns
                    │ (gesture_guard.py)   │  Hold duration enforcement
                    └──────┬──────┬───────┘
                           │      │
              ┌────────────▼┐   ┌▼────────────────┐
              │VoiceGesture  │   │  ActionDispatcher │
              │   Fusion     │   │ (action_disp.py)  │
              │(fusion.py)   │   └────┬──────┬───────┘
              └─────────────┘        │      │
                  Whisper/Google    mouse  keyboard
                  scoring 60/40      │      │
                  JSONL audit log    ▼      ▼
                                 pyautogui pynput

  ┌──────────────────┐   ┌──────────────┐   ┌──────────────────┐
  │  HUDRenderer     │   │ AirDrawing   │   │  AROverlayEngine │
  │ (hud_renderer.py)│   │(air_drawing) │   │ (ar_overlay.py)  │
  │ scan·brackets    │   │ 4 brushes    │   │ pyvirtualcam     │
  │ history·cooldown │   │ shape snap   │   │ circuit+waveform  │
  └──────────────────┘   └──────────────┘   └──────────────────┘

  ┌──────────────────────────────────────────────────────────────┐
  │              Analytics Pipeline                               │
  │  HeatmapEngine (SQLite/SQLAlchemy) → DashboardServer (Flask) │
  │  http://localhost:5050  ←→  SocketIO live push every 2s      │
  └──────────────────────────────────────────────────────────────┘
```

---

## Installation

### Prerequisites
- Python 3.9 or later
- Webcam (built-in or USB, index 0 by default)
- Windows 10/11 (or Ubuntu 20.04+)
- Optional: OBSVirtualCam (Windows) or v4l2loopback (Linux) for AR virtual camera

### Steps

```bash
# 1. Clone or download the project
git clone <repo-url>
cd jarvis_hand_control

# 2. Create virtual environment (recommended)
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

# 3. Run automated setup
python setup.py

# 4. Edit configuration
notepad .env          # Windows
nano .env             # Linux

# 5. Launch
python main.py
# or on Windows:
run.bat
```

### .env Configuration

| Variable | Default | Description |
|---|---|---|
| `CAMERA_INDEX` | `0` | Camera device index |
| `SCREEN_WIDTH` | `1920` | Screen resolution width |
| `SCREEN_HEIGHT` | `1080` | Screen resolution height |
| `SMOOTHING_ALPHA` | `0.35` | EMA cursor smoothing (0=freeze, 1=raw) |
| `DEAD_ZONE_PX` | `10` | Pixels below which cursor doesn't move |
| `FUSION_THRESHOLD` | `0.72` | Min score to fire a fusion command |
| `DASHBOARD_PORT` | `5050` | Analytics dashboard port |
| `WHISPER_MODEL` | `tiny` | Whisper model size (tiny/base/small) |

---

## Usage

### Launch Commands
```bash
python main.py          # Standard launch
python main.py --debug  # With debug logging
run.bat                 # Windows launcher
./run.sh                # Linux/macOS launcher
```

### Modes
| Mode | Activation | Effect |
|---|---|---|
| `normal` | Default | Balanced speed/precision |
| `precision` | rock_sign (once) | 0.55× speed, easier clicking |
| `presentation` | rock_sign (twice) | 1.9× speed, fast navigation |

### Calibration Guide
1. Launch JARVIS — wizard runs automatically if not calibrated
2. **Step 1**: Hold open palm facing camera for 60 frames
3. **Step 2**: Make a tight fist for 30 frames
4. **Step 3**: Point index finger at each screen corner, hold 1.5s
5. **Step 4**: Perform the click gesture 5 times
6. Calibration saved to `config/hand_calibration.json`

---

## Troubleshooting

### Camera not found
```
Error: Cannot open camera index 0
```
- Try `CAMERA_INDEX=1` or `CAMERA_INDEX=2` in `.env`
- Check Device Manager → Imaging Devices (Windows)
- Close any other app using the camera (Teams, Zoom, OBS)

### Virtual camera not showing in Zoom/Teams
- Install **OBSVirtualCam** from [obsproject.com](https://obsproject.com/kb/virtual-camera)
- In Zoom: select "OBS Virtual Camera" as video source
- Set `ar_overlay_enabled = true` in `config/features.json`

### Whisper slow on first run
The first run downloads the Whisper model (~75MB for `tiny`).
Subsequent starts load from cache in `~/.cache/whisper/`. Use `WHISPER_MODEL=tiny` for fastest load.

### Low FPS (< 20)
- Set `model_complexity=0` (already default) in `HandTracker`
- Reduce resolution: `CAP_PROP_FRAME_WIDTH=640`
- Disable AR overlay: `ar_overlay_enabled=false` in features.json
- Close background applications

### Gesture not recognized
- Run calibration wizard: delete `config/hand_calibration.json`, restart
- Ensure good lighting — avoid strong backlight
- Keep hand 40–70cm from camera
- Check `logs/session_*.log` for classification debug output

---

## Project Structure

```
jarvis_hand_control/
├── main.py                        # Threaded production entry point
├── setup.py                       # Automated setup wizard
├── run.bat / run.sh               # Platform launchers
├── requirements.txt               # Pinned dependencies
├── .env.example                   # Configuration template
├── .gitignore
│
├── config/
│   ├── settings.py                # Typed settings dataclass
│   ├── features.json              # Feature toggle flags
│   └── ar_settings.json           # AR overlay configuration
│
├── core/
│   ├── hand_tracker.py            # MediaPipe wrapper
│   ├── finger_analyzer.py         # Joint-angle analysis (dot product)
│   ├── gesture_classifier.py      # 18-gesture classifier
│   ├── gesture_buffer.py          # 5/7-vote + EMA smoothing
│   ├── gesture_guard.py           # Per-gesture cooldowns
│   ├── voice_gesture_fusion.py    # Whisper + gesture fusion
│   ├── air_drawing.py             # Multi-layer air drawing engine
│   ├── drawing_shapes.py          # Shape detection and snapping
│   └── fusion_commands.py         # Voice+gesture command map
│
├── control/
│   ├── mouse_controller.py        # Accelerated mouse control
│   ├── keyboard_controller.py     # Full keyboard actions
│   └── action_dispatcher.py       # Gesture → action routing
│
├── ui/
│   ├── hud_renderer.py            # Iron Man–style HUD
│   ├── ar_effects.py              # Pure AR effect functions
│   ├── ar_overlay.py              # Virtual camera engine
│   └── hud_assets.py              # Visual constants
│
├── analytics/
│   ├── heatmap_engine.py          # SQLAlchemy ORM + heatmap
│   ├── dashboard_server.py        # Flask + SocketIO server
│   └── templates/index.html       # Live dashboard UI
│
├── calibration/
│   ├── calibration_manager.py     # Load/save calibration JSON
│   └── calibration_wizard.py      # 4-step interactive wizard
│
└── tests/
    ├── conftest.py                # Shared fixtures
    ├── test_finger_analyzer.py    # 10 analyzer tests
    ├── test_gesture_buffer.py     # 8 buffer tests
    ├── test_gesture_guard.py      # 12 guard tests
    ├── test_voice_fusion.py       # 7 fusion tests
    ├── test_mouse_controller.py   # 12 mouse tests
    └── test_action_dispatcher.py  # 17 dispatcher tests
```

---

## Contributing

1. Fork the repository
2. Create your feature branch: `git checkout -b feature/amazing-gesture`
3. Follow the existing architecture — all modules expose `update(frame, hand_data, gesture_result)`
4. Add tests in `tests/` for any new classifier logic
5. Run `pytest tests/ -v` — all tests must pass
6. Submit a pull request with a clear description

---

## License

MIT License — Copyright (c) 2025 JARVIS Project Contributors

Permission is hereby granted, free of charge, to any person obtaining a copy of this software to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the software, subject to the following conditions: The above copyright notice shall be included in all copies. THE SOFTWARE IS PROVIDED "AS IS" WITHOUT WARRANTY OF ANY KIND.
