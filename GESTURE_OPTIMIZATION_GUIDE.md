# JARVIS Hand Gesture Control — Optimization Guide

> **Updated: Air Drawing Activation = 3 Fingers (Index+Middle+Ring) held 1.5s**

---

## 🎯 Quick Start: All 18 Gestures

### **Cursor & Click Control**

| Gesture              | Emoji  | How                          | Duration   | Action                        |
| -------------------- | ------ | ---------------------------- | ---------- | ----------------------------- |
| **Cursor Move**      | ☝      | Index finger only            | Continuous | Move mouse                    |
| **Left Click**       | 🤏     | Thumb + index pinch          | Quick      | Left click                    |
| **Right Click**      | ✌ + 📍 | Index + middle + ring        | Quick      | Right click                   |
| **Two-Finger Ready** | ✌      | Index + middle (ready state) | Held       | Cursor moves, release = click |

---

### **Scroll Control**

| Gesture         | Emoji | How                   | Speed                       | Action      |
| --------------- | ----- | --------------------- | --------------------------- | ----------- |
| **Scroll Up**   | 🖐    | Open palm (5 fingers) | Wrist height controls speed | Scroll up   |
| **Scroll Down** | ✊    | Fist (all closed)     | Wrist height controls speed | Scroll down |

**Speed Scaling by Wrist Height:**

- Hand **HIGH** (y < 0.30) = **3x speed** (Fast)
- Hand **MID** (y 0.30-0.55) = **2x speed** (Normal)
- Hand **LOW** (y > 0.55) = **1x speed** (Slow)

---

### **Volume & Media**

| Gesture         | Emoji | How                         | Action    |
| --------------- | ----- | --------------------------- | --------- |
| **Volume Up**   | 👍    | Thumb up only (LEFT hand)   | Volume +3 |
| **Volume Down** | 👎    | Thumb down only (LEFT hand) | Volume -3 |

---

### **Screenshot & Area Select**

| Gesture              | Emoji | Hold Time               | Action                     |
| -------------------- | ----- | ----------------------- | -------------------------- |
| **Quick Screenshot** | 🤘    | Tap                     | Win+Shift+S (snip)         |
| **Area Select**      | 🤘    | **0.6 seconds**         | Enter fullscreen selector  |
|                      |       | Then pinch at 2 corners | Capture region to Pictures |

---

### **✨ Air Drawing Mode — THREE FINGERS GESTURE**

**How to Activate:**

- Hold **3 Fingers Extended (Index + Middle + Ring, Pinky Down)** for **1.5 seconds**
- Fullscreen drawing canvas opens
- **Gesture:** ☝✌👆 (three fingers together)

**Drawing Controls:**
| Gesture | Hold Time | Action |
|---------|-----------|--------|
| ☝ Index only | — | Draw on canvas |
| ✌ Peace sign | Quick release | Lift pen / pause drawing, then start a new line at a different place |
| 👌 Pinch | Hold 0.35s | Cycle brush (Pen → Marker → Spray → Neon → Chalk → Eraser) |
| 🤘 Rock sign | Hold 0.35s | Cycle color (Green → Cyan → Blue → Violet → Orange → Red → White → Yellow) |
| 🖐 Open palm | Quick | Undo last stroke |
| ✊ Fist | Hold 0.8s | Save drawing + Exit (countdown shown) |

---

### **Gesture Quick Reference**

| Feature                  | Gesture              | Duration    | Action                         |
| ------------------------ | -------------------- | ----------- | ------------------------------ |
| **Activate Air Drawing** | **☝✌👆 (3 Fingers)** | **1.5 sec** | ⭐ Index+Middle+Ring extended! |
| Screenshot (Normal)      | 🤘 Rock sign         | Tap         | Win+Shift+S (snip)             |
| Area Screenshot          | 🤘 Rock sign         | 0.6 sec     | Fullscreen selector            |

---

### **Wake Word & System**

| Gesture         | Emoji | How                       | Action                   |
| --------------- | ----- | ------------------------- | ------------------------ |
| **Wake JARVIS** | 🖐    | Open palm with wrist HIGH | Activate voice listening |

---

## ⚙️ Timing Optimization Constants

**Location:** `tools/vision/modules/air_drawing.py`

```python
ENTER_HOLD   = 1.5    # ☝✌👆 Three fingers hold to activate drawing
EXIT_HOLD    = 0.8    # ✊ Fist hold to save + exit
ACTION_HOLD  = 0.35   # 👌🤘 Brush/color change hold
UNDO_CD      = 0.5    # 🖐 Open palm undo cooldown
SNAP_PAUSE   = 0.7    # Shape auto-snap pause
```

**Location:** `tools/vision/gesture_engine.py`

```python
SMOOTH_ALPHA     = 0.35    # Cursor smoothing (0-1, higher = more lag)
DEAD_ZONE        = 5       # Ignore tremors under 5px
MAX_JUMP         = 120     # Prevent teleport jumps
CLICK_COOLDOWN   = 0.50    # Min seconds between clicks
POST_CLICK_FREEZE= 0.18    # Freeze after click fires
PRE_CLICK_FREEZE = 0.08    # Freeze before confirm
PINCH_THRESH     = 0.068   # Thumb-index distance (normalized)
CONFIRM_FRAMES   = 3       # Non-cursor gesture confirmation frames
VOL_FRAMES       = 5       # Volume confirmation (faster)
CLICK_FRAMES     = 2       # Click fires after N frames
SCROLL_INTERVAL  = 0.07    # Seconds between scroll ticks
SCROLL_AMOUNT    = 5       # Scroll units per tick
SHOT_SEL_HOLD    = 0.6     # 🤘 Rock sign hold for screenshot area-select
```

---

## 🚀 Performance Tips

### 1. **Hand Position** (Most Important)

- Keep hand 30-80cm from camera
- Good lighting improves detection
- Avoid shadows on hand

### 2. **Gesture Clarity**

- Make gestures with clear finger separation
- Hold gestures steady (avoid shaking)
- Extend fingers fully (don't curl)

### 3. **Camera Settings** (settings.py / .env)

```env
CAMERA_INDEX=0                  # Change if using external camera
SCREEN_WIDTH=1920
SCREEN_HEIGHT=1080
```

### 4. **MediaPipe Tuning** (gesture_engine.py)

```python
min_hand_detection_confidence=0.65  # Lower = more sensitive, more false positives
min_tracking_confidence=0.55        # Lower = keeps tracking during partial obscure
```

---

## 🛠️ Troubleshooting

### **Gesture Not Detected**

1. Check hand is visible in camera (look at HUD)
2. Increase `min_hand_detection_confidence` → 0.70 (in gesture_engine.py)
3. Ensure good lighting

### **Too Many False Positives**

1. Decrease detection confidence threshold
2. Increase `CONFIRM_FRAMES` (requires N frames of same gesture)
3. Hold gestures more steadily

### **Cursor Jittery**

1. Increase `SMOOTH_ALPHA` (0.35 → 0.50)
2. Increase `DEAD_ZONE` (5 → 15 pixels)

### **Clicks Not Working**

1. Check `CLICK_COOLDOWN` — may be too high (current: 0.50s)
2. Verify pinch distance is exact: thumb tip must touch index tip
3. Check console for "Gesture action error"

### **Air Drawing Not Activating**

1. Ensure `air_drawing: true` in `config/features.json`
2. Hold **3 Fingers (Index+Middle+Ring) for 1.5+ seconds** with pinky down
3. Keep hand steady (avoid shaking)
4. Check console: `log.info("Air drawing ON")`

---

## 📊 What Changed

### Version Update (Latest Optimization)

```diff
ENTER_HOLD = 3.0  → 1.5 seconds
```

**Why?** 3 seconds was too long for natural interaction. 1.5 seconds provides:

- Fast enough for fluid UX
- Slow enough to avoid false triggers
- Similar to commercial gesture systems

---

## 🎮 Pro Tips

1. **Speed Scrolling:** Move wrist to top of screen before scrolling for 3x speed
2. **Precision Drawing:** Use index tip near camera for best accuracy
3. **Quick Clicks:** Pinch click (thumb+index) is fastest and most reliable
4. **Draw Smoothly:** Keep hand steady while drawing; speed doesn't matter
5. **Multi-Hand:** Right hand cursor + left hand volume for expert mode

---

## 📝 Configuration Files

| File                                  | Purpose                | Key Settings                |
| ------------------------------------- | ---------------------- | --------------------------- |
| `config/features.json`                | Enable/disable modules | `air_drawing: true/false`   |
| `config/settings.py`                  | Global constants       | Voice, AI provider, paths   |
| `.env`                                | Environment variables  | Camera index, API keys      |
| `tools/vision/gesture_engine.py`      | Core timings           | Scroll, click, freeze times |
| `tools/vision/modules/air_drawing.py` | Drawing timings        | ENTER_HOLD, EXIT_HOLD       |

---

## 🔗 Related Files

- [USAGE.md](USAGE.md) — Full user guide
- [tools/vision/gesture_engine.py](tools/vision/gesture_engine.py) — Core gesture logic
- [tools/vision/modules/air_drawing.py](tools/vision/modules/air_drawing.py) — Air drawing implementation
- [tools/vision/gesture_controller.py](tools/vision/gesture_controller.py) — JARVIS integration

---

## 📱 Gesture Images (Reference)

```
☝  Index pointing = Cursor
🤏  Thumb+index touching = Left click
✌  Two fingers = Right click / Peace sign / Lift pen
👍  Thumb up = Volume up
👎  Thumb down = Volume down
🖐  All 5 fingers spread = Scroll up / Wake
✊  Fist = Scroll down / Exit drawing
🤘  Index+pinky = Screenshot / Color change
```

---

**Last Updated:** May 10, 2026
**Status:** ✅ All gestures workable with optimized timings
