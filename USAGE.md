# JARVIS Hand Gesture Control System — Complete Usage Guide

> **How to perform every gesture, voice command, drawing action,
> and system task — with step-by-step instructions.**

---

## Table of Contents

1. [First-Time Setup](#1-first-time-setup)
2. [Launching JARVIS](#2-launching-jarvis)
3. [Camera Window & HUD](#3-camera-window--hud)
4. [Hand Position Basics](#4-hand-position-basics)
5. [All 18 Gestures — How to Perform](#5-all-18-gestures--how-to-perform)
6. [Voice + Gesture Fusion Commands](#6-voice--gesture-fusion-commands)
7. [Air Drawing Mode](#7-air-drawing-mode)
8. [Calibration Wizard](#8-calibration-wizard)
9. [Switching Modes](#9-switching-modes)
10. [Analytics Dashboard](#10-analytics-dashboard)
11. [AR Virtual Camera](#11-ar-virtual-camera)
12. [Keyboard Shortcuts Inside JARVIS](#12-keyboard-shortcuts-inside-jarvis)
13. [Troubleshooting Quick Reference](#13-troubleshooting-quick-reference)

---

## 1. First-Time Setup

Run this **once** before launching for the first time:

```
cd jarvis_hand_control
python setup.py
```

What it does automatically:
- Checks your Python version (needs 3.9+)
- Creates all folders (`logs/`, `data/`, `drawings/`, etc.)
- Installs all packages from `requirements.txt`
- Copies `.env.example` → `.env`
- Downloads the Whisper voice model (~75 MB, one time only)
- Checks if OBSVirtualCam is installed (for AR overlay)

After setup, open `.env` and check these settings:

| Setting | What to change |
|---|---|
| `CAMERA_INDEX` | Change to `1` or `2` if built-in cam is not index 0 |
| `SCREEN_WIDTH` / `SCREEN_HEIGHT` | Set to your monitor resolution |
| `DASHBOARD_PORT` | Change `5050` if that port is busy |
| `WHISPER_MODEL` | `tiny` = fastest, `base` = more accurate |

---

## 2. Launching JARVIS

### Windows
```
Double-click  run.bat
```
or in terminal:
```
cd jarvis_hand_control
python main.py
```

### Linux / macOS
```bash
cd jarvis_hand_control
bash run.sh
```

### What happens at startup
1. ASCII banner prints in terminal
2. Settings and feature flags load
3. Camera opens (green skeleton appears on hand)
4. If no calibration exists → **Calibration Wizard starts automatically**
5. Voice microphone begins listening in background
6. Analytics dashboard launches at `http://localhost:5050`
7. HUD (heads-up display) appears in camera window

### Shutting down
- Press **Q** inside the camera window
- Or press **Ctrl+C** in the terminal
- JARVIS saves session data and closes cleanly

---

## 3. Camera Window & HUD

When JARVIS is running you will see a camera window with overlaid graphics:

```
┌─────────────────────────────────────────────────────────┐
│ ┐                                         FPS: 28.4   └ │  ← corner brackets
│                                                          │
│                                     HISTORY             │  ← gesture history
│        [HAND SKELETON HERE]          left_click 2s      │    sidebar
│                                      scroll_up  5s      │
│   LEFT CLICK                         swipe_left 9s      │
│   92%                                                    │
│                                                          │
│ └                                                      ┘ │
│  🎤 "save"  ▓▓▓▓▒▒▒▒▒▒▒▒▒▒  0.81  [cooldown arcs] ↗   │
└─────────────────────────────────────────────────────────┘
```

| HUD Element | Meaning |
|---|---|
| Corner brackets (cyan L-shapes) | System active indicator |
| Scanning horizontal line | Live feed active |
| Gesture name + % | Current detected gesture and confidence |
| Right sidebar | Last 5 gestures with time-ago |
| Bottom-left mic icon | Green = voice detected, gray = silent |
| Bottom-left bar | Fusion score (voice × gesture) |
| Bottom-right arcs | Per-gesture cooldown progress |
| Top-right FPS | Frames per second |
| Hand skeleton | Green dots = fingertips, white lines = connections |

---

## 4. Hand Position Basics

**Before performing any gesture:**

✅ **DO:**
- Keep hand 40–70 cm from camera
- Face your palm toward the camera
- Ensure good lighting (no strong backlight behind you)
- Move gestures slowly and deliberately until calibrated
- Hold each gesture steady for ~0.5 seconds to confirm

❌ **DON'T:**
- Wave hand very fast (smoothing buffer needs 5–7 frames)
- Perform gestures at extreme camera angles
- Cover the camera with another object
- Use in very dark conditions

---

## 5. All 18 Gestures — How to Perform

Each gesture requires being held steady for at least 5 consistent frames (~0.2s at 30fps).

---

### Gesture 1: Cursor Move
**What it does:** Moves the mouse cursor

**How to perform:**
1. Extend only your **index finger** — point it straight up
2. Curl all other fingers into a loose fist
3. Move your hand — the cursor follows your index fingertip
4. **Tip:** Move slowly for precision, fast for large jumps

```
Hand shape:   ☝️  (one finger pointing up)
```

---

### Gesture 2: Left Click
**What it does:** Clicks the left mouse button

**How to perform:**
1. Extend both **index** and **middle fingers** (peace-like, but tips together)
2. Bring the two fingertips **close together** (within ~30px)
3. Hold for 0.3s → click fires
4. Separate fingers to reset

```
Hand shape:   ✌️  but tips pinched together
```

---

### Gesture 3: Double Click
**What it does:** Double-clicks (opens files, selects words)

**How to perform:**
1. Perform the **Left Click** gesture
2. Release (separate fingers)
3. Perform **Left Click** again within **0.4 seconds**
4. JARVIS detects the rapid repeat and fires a double-click

---

### Gesture 4: Right Click
**What it does:** Opens context menus

**How to perform:**
1. Bring **thumb tip and index tip together** in a pinch
2. Curl **middle, ring, pinky** fingers closed
3. Hold the pinch for 0.3s → right-click fires

```
Hand shape:   👌 but only thumb+index touching, others curled
```

---

### Gesture 5: Freeze Cursor
**What it does:** Locks the cursor in place (toggle)

**How to perform:**
1. Open all 5 fingers fully flat
2. Face your **palm toward the camera**
3. Hold for 0.5s → cursor freezes
4. Repeat the same gesture to unfreeze

```
Hand shape:   🖐️  (open palm facing camera)
```

---

### Gesture 6: Scroll Up
**What it does:** Scrolls the page upward

**How to perform:**
1. Make a **fist** (all fingers curled closed)
2. **Tilt your wrist upward** (rotate so knuckles point up)
3. The more you tilt, the faster the scroll (1–10 speed)
4. Return wrist to neutral to stop

```
Hand shape:   ✊  tilted so top of fist faces away from you
Tilt more = scroll faster
```

---

### Gesture 7: Scroll Down
**What it does:** Scrolls the page downward

**How to perform:**
1. Make a **fist**
2. **Tilt your wrist downward** (rotate so knuckles point down)
3. Tilt more = faster scroll
4. Return wrist to neutral to stop

```
Hand shape:   ✊  tilted forward/downward
```

---

### Gesture 8: Swipe Left
**What it does:** Browser back / Alt+Left arrow

**How to perform:**
1. Hold **index + middle fingers extended** (V-shape / peace)
2. Keep them spread apart
3. Move your entire hand **quickly to the left**
4. Velocity must exceed threshold (~130px/s) to fire

```
Hand shape:   ✌️  moving ← fast
```

---

### Gesture 9: Swipe Right
**What it does:** Browser forward / Alt+Right arrow

**How to perform:**
1. Hold **index + middle fingers extended** (V-shape)
2. Move your entire hand **quickly to the right**

```
Hand shape:   ✌️  moving → fast
```

---

### Gesture 10: Swipe Up
**What it does:** Maximize the active window

**How to perform:**
1. Extend **index, middle, and ring fingers** (3 fingers up)
2. Keep pinky curled
3. Move your hand **quickly upward**

```
Hand shape:   three fingers up, moving ↑ fast
```

---

### Gesture 11: Swipe Down
**What it does:** Minimize the active window

**How to perform:**
1. Extend **index, middle, and ring fingers**
2. Move your hand **quickly downward**

```
Hand shape:   three fingers up, moving ↓ fast
```

---

### Gesture 12: Thumbs Up
**What it does:** Volume Up (2 steps)

**How to perform:**
1. Extend only your **thumb** pointing upward
2. Curl all other four fingers into your palm
3. Thumb tip must be clearly above your wrist
4. Hold steady for 0.25s → fires

```
Hand shape:   👍  (classic thumbs up)
```

---

### Gesture 13: Thumbs Down
**What it does:** Volume Down (2 steps)

**How to perform:**
1. Extend only your **thumb** pointing downward
2. Curl all four fingers into palm
3. Thumb tip must be clearly below your wrist
4. Hold steady → fires

```
Hand shape:   👎  (classic thumbs down)
```

---

### Gesture 14: OK Sign
**What it does:** Press Enter key

**How to perform:**
1. Bring **thumb and index tip together** to form a circle/loop
2. Extend **middle, ring, and pinky** fingers out
3. Hold the circle for 0.4s → Enter fires

```
Hand shape:   👌  (OK sign)
```

---

### Gesture 15: Peace Sign
**What it does:** Take a screenshot (saved to `data/screenshots/`)

**How to perform:**
1. Extend **index and middle fingers** in a wide V
2. Keep them **spread apart** (more than 60 normalised-px)
3. Curl **ring and pinky** closed
4. Hold for 0.6s → screenshot captured and saved

```
Hand shape:   ✌️  with fingers spread wide apart
```

---

### Gesture 16: Rock Sign
**What it does:** Toggle between Normal / Precision / Presentation modes

**How to perform:**
1. Extend **index finger and pinky finger** out
2. Curl **middle and ring fingers** into palm (like "horns")
3. Hold for 0.5s → mode cycles: Normal → Precision → Presentation → Normal

```
Hand shape:   🤘  (rock horns)
```

---

### Gesture 17: Fist (Hold / Drag)
**What it does:** Click-and-hold (for dragging), or media stop when fused with voice

**How to perform:**
1. Curl **all five fingers** closed tightly
2. Hold → mouse button presses down (drag mode active)
3. Move hand to drag objects
4. Open hand to release mouse button
5. **Wrist tilt** while fisting = scroll (see Gestures 6 & 7)

```
Hand shape:   ✊  (tight fist)
```

---

### Gesture 18: Drawing Mode
**What it does:** Activates air drawing on screen

**How to perform:**
1. Extend only your **index finger** (same as cursor move)
2. **Hold still** for **0.45 seconds**
3. An expanding ring animation confirms entry
4. Now move — your fingertip draws on screen
5. To exit: make a **fist and hold for 0.6 seconds** (save countdown circle appears)

```
Hand shape:   ☝️  held steady for 0.45s
```

---

## 6. Voice + Gesture Fusion Commands

JARVIS listens to your microphone in the background. When you **say a keyword AND hold a gesture at the same time**, it fires a high-level command.

**How to use:**
1. **Say the keyword** (clearly, within 1.2 seconds)
2. **Hold the matching gesture** at the same time
3. The fusion score bar (bottom-left) fills up — if it reaches the threshold, the command fires
4. JARVIS speaks the feedback phrase in the HUD

| Say this | + Hold this gesture | = Action |
|---|---|---|
| **"open"** | Cursor Move | Open file under cursor |
| **"close"** | Fist | Close active window |
| **"search"** | Peace Sign | Open browser search |
| **"save"** | OK Sign | Ctrl+S (Save) |
| **"bigger"** | Swipe Up | Maximize window |
| **"undo"** | Thumbs Down | Ctrl+Z |
| **"screenshot"** | Peace Sign | Save screenshot |
| **"jarvis"** | Rock Sign | Open AI chat |
| **"play"** | Thumbs Up | Play/Pause media |
| **"stop"** | Fist | Stop media |
| **"next"** | Swipe Right | Next track |
| **"volume"** | Thumbs Up | Volume up |
| **"volume"** | Thumbs Down | Volume down |
| **"new"** | Peace Sign | New browser tab |
| **"back"** | Swipe Left | Browser back |
| **"zoom"** | OK Sign | Zoom in |
| **"copy"** | Peace Sign | Ctrl+C |
| **"paste"** | OK Sign | Ctrl+V |
| **"select"** | Rock Sign | Ctrl+A (Select all) |
| **"delete"** | Thumbs Down | Delete key |

**Tips for better recognition:**
- Speak clearly in a quiet room
- Say the keyword first, then hold the gesture
- The voice window is **1.2 seconds** — don't wait too long between speaking and gesturing
- Use `WHISPER_MODEL=base` in `.env` for better accuracy (slower startup)

---

## 7. Air Drawing Mode

### Entering Drawing Mode
1. Extend index finger alone
2. Hold completely still for **0.45 seconds**
3. Animated expanding ring confirms you are in drawing mode

### Drawing
- Move your index finger — strokes appear on screen
- Drawing canvas overlays on top of the camera feed

### Changing Brush
- Make the **Rock Sign** gesture → cycles: Pen → Marker → Spray → Eraser → Pen

### Changing Color
- Make **Right Click** gesture → cycles through 8 colors:
  Green → Cyan → Blue → Violet → Orange → Red → White → Yellow

### Brush Modes

| Brush | Effect |
|---|---|
| **Pen** | Thin precise line, pressure from Z depth |
| **Marker** | Thick semi-transparent stroke |
| **Spray** | Scattered dots, spray-can effect |
| **Eraser** | Clears 30px circle from canvas |

### Shape Snapping (Automatic)
When you **stop drawing for 0.7 seconds**, JARVIS analyzes your stroke:
- Circle detected → snaps to perfect circle (white flash confirms)
- Rectangle detected → snaps to perfect bounding box
- Line detected → snaps to straight line
- Freeform → kept as-is

### Layers (Left Hand)
If dual-hand mode is enabled (`dual_hand_enabled: true` in `features.json`):
- Left hand pinch → Add new layer
- Left hand swipe up → Switch to layer above
- Left hand swipe down → Switch to layer below
- Left hand spread → Merge all layers

### Saving and Exiting
1. Make a **fist** with your drawing hand
2. Hold fist for **0.6 seconds** — a clock countdown circle fills on screen
3. On completion:
   - Drawing saved as PNG to `drawings/drawing_TIMESTAMP.png`
   - Replay data saved as JSON to `drawings/replay_TIMESTAMP.json`
   - Canvas clears

### Replaying a Drawing
```python
# In Python or a script:
from core.air_drawing import AirDrawingEngine
engine = AirDrawingEngine()
engine.replay("drawings/replay_20250509_120000.json")
```

---

## 8. Calibration Wizard

Calibration makes JARVIS accurately track **your specific hand size** and **your camera angle**.

### When it runs
- Automatically on first launch (no `config/hand_calibration.json` exists)
- Manually: delete that file and restart JARVIS

### Step 1 — Hand Size (60 frames, ~2 seconds)
**Instruction shown on screen:** *"Open palm facing camera"*
1. Hold your open hand flat in front of the camera
2. Face all fingers toward the camera
3. Keep still — a progress bar fills at the bottom
4. Done when bar reaches 100%

### Step 2 — Closed Fist (30 frames, ~1 second)
**Instruction:** *"Make a tight fist"*
1. Curl all fingers closed tightly
2. Keep fist steady — progress bar fills
3. JARVIS learns your hand compression ratio

### Step 3 — Corner Mapping (4 corners)
**Instruction:** *"Point to TOP-LEFT corner"* (then TR, BL, BR)

For each corner:
1. Point your **index finger** toward that corner of your SCREEN
2. Hold completely **still for 1.5 seconds**
3. A countdown arc fills in the bottom-right of the camera window
4. Flash confirmation: *"✔ TOP-LEFT RECORDED"*
5. Repeat for all 4 corners

This maps your hand's movement range to the full screen area.

### Step 4 — Click Calibration (5 clicks)
**Instruction:** *"Perform click gesture 5 times"*
1. Perform the **Left Click** gesture (index + middle tips together)
2. Open fingers back to reset
3. Repeat 5 times
4. JARVIS measures the average pinch distance for YOUR hand

### After calibration
- Data saved to `config/hand_calibration.json`
- JARVIS restarts the main pipeline automatically
- Press **ESC** at any time during calibration to abort

---

## 9. Switching Modes

Perform the **Rock Sign** gesture to cycle through control modes:

| Mode | Cursor Speed | Best For |
|---|---|---|
| **Normal** | 1× (default) | Everyday use |
| **Precision** | 0.55× (slower) | Clicking small targets, design work |
| **Presentation** | 1.9× (faster) | Navigating across large monitors |

The current mode is shown **top-left** of the HUD:
- No label = Normal mode
- `PRECISION` (green) = Precision mode
- `PRESENTATION` (yellow) = Presentation mode

---

## 10. Analytics Dashboard

### Opening the Dashboard
It opens automatically in your browser at startup.
To open manually:
```
http://localhost:5050
```

### Dashboard Panels

| Panel | Location | Shows |
|---|---|---|
| Total Gestures Today | Top-left card | Count of all gestures this session |
| Economy Score % | Top-2nd card | Gestures per minute (efficiency) |
| Session Duration | Top-3rd card | Time since JARVIS launched |
| Avg Confidence | Top-right card | Mean classifier confidence across session |
| **Gesture Heatmap** | Middle-left | Hot zones on screen where you gesture most |
| **Gesture Distribution** | Middle-right | Doughnut chart — which gestures you use |
| **Fatigue Curve** | Bottom-left | Line chart — gesture rate over session |
| **Hourly Count** | Bottom-right | Bar chart — activity per hour of day |
| Session Comparison | Bottom | Compare two past sessions by ID |

### Live Updates
- Stats and heatmap update **every 2 seconds** via WebSocket (no page refresh needed)
- Heatmap refreshes every **3 seconds**
- Distribution and fatigue refresh every **5 seconds**

### Exporting a Weekly Report (PDF)
```python
from analytics.heatmap_engine import HeatmapEngine
engine = HeatmapEngine()
engine.initialize("data/gestures.db")
path = engine.export_weekly_report()
print(f"Report saved: {path}")
# Saved to reports/weekly_YYYY-MM-DD.pdf
```

---

## 11. AR Virtual Camera

The AR overlay streams a processed video feed to a virtual camera device that video-call apps (Zoom, Teams, OBS) can pick up.

### Enabling AR Overlay
In `config/features.json`:
```json
{
  "ar_overlay_enabled": true
}
```

### Requirements
- **Windows:** Install [OBSVirtualCam](https://obsproject.com/kb/virtual-camera)
- **Linux:** `sudo modprobe v4l2loopback devices=1 video_nr=10`

### What appears in the AR feed
- Circuit-board scrolling background pattern
- Pulse rings at each hand position
- Waveform bars (microphone amplitude) at bottom
- Air-drawing strokes with glow effect
- JARVIS name badge with scanning line
- Full-frame scan line overlay

### Using in Zoom / Teams
1. Enable AR in `features.json`
2. Launch JARVIS
3. In Zoom → Settings → Video → Camera → select **"OBS Virtual Camera"**
4. Your gesture-controlled AR feed appears to meeting participants

### Adjusting AR settings
Edit `config/ar_settings.json`:
```json
{
  "circuit_pattern_opacity": 0.15,
  "pulse_ring_enabled": true,
  "waveform_bars_enabled": true,
  "background_effects_intensity": 70,
  "fps_target": 30
}
```

---

## 12. Keyboard Shortcuts Inside JARVIS

While the camera window is focused:

| Key | Action |
|---|---|
| **Q** | Quit JARVIS (graceful shutdown) |
| Any other key | Passed through to OS normally |

During Calibration Wizard:
| Key | Action |
|---|---|
| **ESC** | Abort calibration (returns to uncalibrated state) |

---

## 13. Troubleshooting Quick Reference

### Camera shows black screen
```
Check: Another app is using the camera (Teams, Zoom, browser)
Fix:   Close other camera apps, then restart JARVIS
Also:  Try CAMERA_INDEX=1 in .env
```

### Gestures fire incorrectly
```
Check: Hand calibration may be outdated
Fix:   Delete config/hand_calibration.json → restart → redo wizard
Also:  Improve lighting, avoid backlit backgrounds
```

### Voice commands not working
```
Check: Microphone permissions in Windows/macOS settings
Check: logs/session_*.log for "sounddevice error"
Fix:   pip install sounddevice
Also:  Speak more clearly; use WHISPER_MODEL=base in .env
```

### Low FPS (under 20)
```
Fix 1: Ensure ar_overlay_enabled is false in features.json
Fix 2: Reduce camera resolution in .env (FRAME_WIDTH=640)
Fix 3: Close other GPU-heavy applications
Fix 4: model_complexity is already 0 (fastest) by default
```

### Cursor jumps wildly
```
Fix 1: Run calibration wizard (Step 3 — corner mapping)
Fix 2: Increase DEAD_ZONE_PX in .env (try 15 or 20)
Fix 3: Decrease SMOOTHING_ALPHA in .env (try 0.20 for smoother)
```

### Dashboard won't open
```
Fix 1: Check DASHBOARD_PORT in .env (default 5050)
Fix 2: pip install flask flask-socketio
Fix 3: Open manually: http://localhost:5050
Fix 4: Check logs/session_*.log for Flask errors
```

### Drawing strokes appear in wrong position
```
Fix:   Redo calibration (Step 3 — corner mapping)
       Your camera angle may have changed since last calibration
```

### "Cannot open camera index 0"
```
Fix 1: Plug in your webcam and try again
Fix 2: Set CAMERA_INDEX=1 or CAMERA_INDEX=2 in .env
Fix 3: On Linux: ls /dev/video* to find your camera device number
```

### Crash report generated
```
Location: logs/crash_TIMESTAMP.txt
Contains: Full traceback + settings + Python version
Share this file when reporting bugs
```

---

## Log Files Location

| File | Contents |
|---|---|
| `logs/session_TIMESTAMP.log` | Full runtime log per session |
| `logs/crash_TIMESTAMP.txt` | Crash report (only on error) |
| `logs/fusion_log.jsonl` | Every voice+gesture fusion attempt |
| `logs/action_log.jsonl` | Every dispatched action with latency |
| `data/gestures.db` | SQLite database (all gesture events) |
| `drawings/` | Saved air drawings (PNG + JSON replay) |
| `data/screenshots/` | Screenshots taken by peace sign gesture |
| `reports/` | Weekly PDF analytics reports |

---

*JARVIS Hand Gesture Control System — Production Build v2.0*
