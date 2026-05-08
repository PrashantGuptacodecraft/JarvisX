"""
tools/vision/gesture_engine.py
Ultra-smooth hand gesture engine — MediaPipe Tasks HandLandmarker API.
Improvements:
  • Smoother cursor: lower alpha + dead-zone + velocity cap
  • Accurate volume: explicit thumb-up/thumb-down angle check
  • More reliable click: pinch or curl, plus cursor lock during click
"""
from collections import deque
import threading
import time
import math
import logging
import os

log = logging.getLogger("gesture_engine")

_BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MODEL_PATH = os.path.join(_BASE, "models", "hand_landmarker.task")

# ── Gesture names ──────────────────────────────────────────────────────────────
G_CURSOR   = "CURSOR_MOVE"
G_CLICK    = "LEFT_CLICK"
G_RCLICK   = "RIGHT_CLICK"
G_SCROLL_U = "SCROLL_UP"
G_SCROLL_D = "SCROLL_DOWN"
G_VOL_UP   = "VOLUME_UP"
G_VOL_DN   = "VOLUME_DOWN"
G_WAKE     = "WAKE_JARVIS"
G_SHOT     = "SCREENSHOT"
G_NONE     = "NONE"

# ── Tuning constants ───────────────────────────────────────────────────────────
SMOOTH_ALPHA       = 0.375  # user-tuned: fast response, dead-zone handles jitter
DEAD_ZONE          = 6      # pixels: ignore micro-tremors
MAX_JUMP           = 120    # pixels: cap single-frame jump
CLICK_COOLDOWN     = 0.65   # seconds between clicks
GESTURE_HOLD       = 5      # frames non-cursor gesture must persist
CLICK_HOLD         = 3      # click fires faster (3 frames) for responsiveness
VOL_HOLD           = 8      # volume gestures need longer confirmation
CLICK_LOCK_SEC     = 0.22   # freeze cursor after click fires
CURSOR_HISTORY     = 8      # history for median-snap click target
PRE_CLICK_FREEZE   = 0.10   # freeze cursor when curl intent detected
PINCH_THRESHOLD    = 0.07   # normalised dist: thumb+index = pinch click
DWELL_RADIUS       = 18     # pixels: auto-lock if hand stays within this
DWELL_FRAMES       = 7      # frames hand must stay still to trigger dwell-lock


def _dist(a, b) -> float:
    return math.hypot(a.x - b.x, a.y - b.y)


def _classify(lm) -> str:
    """
    Classify 21 hand landmarks into a gesture.

    Landmark IDs (MediaPipe):
      0=Wrist  4=Thumb tip  3=Thumb IP
      5=Index MCP  8=Index tip  6=Index PIP  7=Index DIP
      12=Mid tip  10=Mid PIP
      16=Ring tip  14=Ring PIP
      20=Pinky tip  18=Pinky PIP
    """
    WRIST                       = 0
    THUMB_TIP, THUMB_IP         = 4, 3
    IDX_MCP, IDX_TIP, IDX_PIP, IDX_DIP = 5, 8, 6, 7
    MID_TIP,  MID_PIP           = 12, 10
    RNG_TIP,  RNG_PIP           = 16, 14
    PKY_TIP,  PKY_PIP           = 20, 18

    # ── Finger-up helpers ─────────────────────────────────────────────────────
    def up(tip, pip): return lm[tip].y < lm[pip].y - 0.02   # small threshold

    idx   = up(IDX_TIP, IDX_PIP)
    mid   = up(MID_TIP, MID_PIP)
    ring  = up(RNG_TIP, RNG_PIP)
    pinky = up(PKY_TIP, PKY_PIP)

    # Thumb: horizontal on mirrored feed (tip.x > ip.x means pointing right → "up")
    thumb_up_h   = lm[THUMB_TIP].x > lm[THUMB_IP].x + 0.03
    # Vertical thumb UP: tip clearly above wrist
    thumb_up_v   = lm[THUMB_TIP].y < lm[WRIST].y - 0.10
    # Vertical thumb DOWN: tip clearly below MCP (knuckle)
    thumb_dn_v   = lm[THUMB_TIP].y > lm[WRIST].y + 0.05

    fingers_up = sum([thumb_up_h, idx, mid, ring, pinky])

    # ── ROCK SIGN: index + pinky up ──────────────────────────────────────────
    if idx and pinky and not mid and not ring:
        return G_SHOT

    # ── VOLUME UP: thumb pointing clearly upward, all others closed ──────────
    if thumb_up_v and not idx and not mid and not ring and not pinky:
        return G_VOL_UP

    # ── VOLUME DOWN: thumb pointing clearly downward, all others closed ───────
    if thumb_dn_v and not idx and not mid and not ring and not pinky:
        return G_VOL_DN

    # ── OPEN PALM: all 5 clearly up ──────────────────────────────────────────
    if fingers_up == 5:
        return G_SCROLL_U

    # ── FIST: all fingers down (scroll down) ─────────────────────────────────
    if not idx and not mid and not ring and not pinky and not thumb_up_h:
        return G_SCROLL_D

    # ── TWO FINGERS: index + middle (right click) ────────────────────────────
    if idx and mid and not ring and not pinky:
        return G_RCLICK

    # ── PINCH CLICK (Method 1 — PRIMARY, most reliable) ─────────────────────
    # Thumb tip + Index tip come close together while index is NOT fully extended
    # Cursor anchor shifts to wrist during pinch so position doesn't drift at all
    pinch_dist = _dist(lm[THUMB_TIP], lm[IDX_TIP])
    if pinch_dist < PINCH_THRESHOLD and not mid and not ring and not pinky:
        return G_CLICK

    # ── CURL CLICK (Method 2 — backup, for when pinch is hard) ──────────────
    # Index tip drops below its DIP joint = finger bending inward
    index_curled = lm[IDX_TIP].y > lm[IDX_DIP].y + 0.025
    if index_curled and not mid and not ring and not pinky:
        return G_CLICK

    # Pre-click intent: index tip approaching DIP (starting to curl)
    # → freeze cursor early before click fully registers
    index_curling = 0.0 < (lm[IDX_DIP].y - lm[IDX_TIP].y) < 0.025
    if index_curling and not mid and not ring and not pinky:
        return "PRE_CLICK"  # internal: freeze cursor now, don't fire click yet

    # ── CURSOR: only index up (pointing) ─────────────────────────────────────
    if idx and not mid and not ring and not pinky:
        return G_CURSOR

    # ── WAKE: 4+ fingers up + wrist high in frame ────────────────────────────
    if fingers_up >= 4 and lm[WRIST].y < 0.35:
        return G_WAKE

    return G_NONE


class GestureEngine:
    def __init__(self, action_callback, frame_callback=None, cam_index: int = 0):
        self.action_cb  = action_callback
        self.frame_cb   = frame_callback
        self.cam_index  = cam_index
        self._running   = False
        self._thread    = None
        self._paused    = False

        # Smoothed cursor state
        self._smooth_x  = 0.0
        self._smooth_y  = 0.0
        self._prev_sx   = 0.0
        self._prev_sy   = 0.0
        self._initialized = False

        self._last_click          = 0.0
        self._freeze_cursor_until = 0.0   # hard freeze: cursor does not move
        self._pre_click_detected  = False  # softer freeze: we noticed curl starting
        self._frozen_x            = 0.0   # where we locked before click
        self._frozen_y            = 0.0

        self._gesture_buf: list[str] = []
        self._last_gesture = G_NONE
        self._recent_cursor = deque(maxlen=CURSOR_HISTORY)  # for median-snap

        # Dwell-lock state: if hand stays in DWELL_RADIUS for DWELL_FRAMES, lock
        self._dwell_frames  = 0
        self._dwell_cx      = 0.0
        self._dwell_cy      = 0.0
        self._dwell_locked  = False

        try:
            import pyautogui
            self._sw, self._sh = pyautogui.size()
        except Exception:
            self._sw, self._sh = 1920, 1080

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def start(self) -> bool:
        if self._running:
            return True
        if not os.path.exists(MODEL_PATH):
            log.error(f"Hand model not found: {MODEL_PATH}")
            return False
        try:
            import mediapipe, cv2  # noqa
        except ImportError as e:
            log.error(f"Missing deps: {e}")
            return False
        self._running = True
        self._thread  = threading.Thread(target=self._loop, daemon=True, name="gesture-engine")
        self._thread.start()
        log.info("Gesture engine started")
        return True

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)

    def pause(self):  self._paused = True
    def resume(self): self._paused = False

    # ── Main loop ──────────────────────────────────────────────────────────────

    def _loop(self):
        import cv2
        import mediapipe as mp

        HandLandmarker        = mp.tasks.vision.HandLandmarker
        HandLandmarkerOptions = mp.tasks.vision.HandLandmarkerOptions
        RunningMode           = mp.tasks.vision.RunningMode
        BaseOptions           = mp.tasks.BaseOptions
        MpImage               = mp.Image
        MpImageFormat         = mp.ImageFormat

        options = HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=MODEL_PATH),
            running_mode=RunningMode.IMAGE,
            num_hands=1,
            min_hand_detection_confidence=0.65,
            min_hand_presence_confidence=0.55,
            min_tracking_confidence=0.55,
        )

        cap = cv2.VideoCapture(self.cam_index, cv2.CAP_DSHOW)
        if not cap.isOpened():
            cap = cv2.VideoCapture(self.cam_index)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

        with HandLandmarker.create_from_options(options) as landmarker:
            while self._running:
                ret, frame = cap.read()
                if not ret:
                    time.sleep(0.05)
                    continue

                frame = cv2.flip(frame, 1)
                h, w  = frame.shape[:2]
                rgb   = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                gesture = G_NONE

                if not self._paused:
                    try:
                        result = landmarker.detect(
                            MpImage(image_format=MpImageFormat.SRGB, data=rgb)
                        )
                        if result.hand_landmarks:
                            lm = result.hand_landmarks[0]
                            gesture = _classify(lm)

                            # ── Pre-click intent → freeze cursor early ───────
                            if gesture == "PRE_CLICK" and not self._pre_click_detected:
                                self._pre_click_detected = True
                                self._freeze_cursor_until = time.time() + PRE_CLICK_FREEZE
                                self._snap_to_median()   # snap to stable position now
                                gesture = G_CURSOR       # don't buffer PRE_CLICK

                            # ── Smooth cursor (only when not frozen) ─────────
                            if gesture in (G_CURSOR, G_RCLICK):
                                self._pre_click_detected = False
                                self._update_cursor(lm, gesture)

                            # Draw skeleton
                            self._draw_landmarks(frame, lm, w, h)

                    except Exception as e:
                        log.debug(f"Landmark error: {e}")

                    # ── Gesture debounce ──────────────────────────────────────
                    # Click uses shorter hold for faster response
                    if buf_gesture == G_CLICK:
                        hold = CLICK_HOLD
                    elif buf_gesture in (G_VOL_UP, G_VOL_DN):
                        hold = VOL_HOLD
                    else:
                        hold = GESTURE_HOLD
                    buf_gesture = gesture if gesture != "PRE_CLICK" else G_CURSOR

                    self._gesture_buf.append(buf_gesture)
                    if len(self._gesture_buf) > hold:
                        self._gesture_buf.pop(0)

                    if (
                        len(self._gesture_buf) == hold
                        and all(g == buf_gesture for g in self._gesture_buf)
                        and buf_gesture not in (G_NONE, G_CURSOR)
                        and buf_gesture != self._last_gesture
                    ):
                        self._last_gesture = buf_gesture
                        self._fire_action(buf_gesture)
                    elif buf_gesture in (G_NONE, G_CURSOR) and buf_gesture != self._last_gesture:
                        self._last_gesture = buf_gesture
                        self._gesture_buf.clear()

                # HUD
                self._draw_hud(frame, gesture)
                if self.frame_cb:
                    self.frame_cb(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB), gesture)

                time.sleep(0.030)   # ~33 fps

        cap.release()

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _draw_landmarks(self, frame, lm, w: int, h: int):
        import cv2
        CONNECTIONS = [
            (0,1),(1,2),(2,3),(3,4),
            (0,5),(5,6),(6,7),(7,8),
            (0,9),(9,10),(10,11),(11,12),
            (0,13),(13,14),(14,15),(15,16),
            (0,17),(17,18),(18,19),(19,20),
            (5,9),(9,13),(13,17),(5,17),
        ]
        pts = [(int(p.x * w), int(p.y * h)) for p in lm]
        for a, b in CONNECTIONS:
            cv2.line(frame, pts[a], pts[b], (0, 212, 255), 2)
        # Highlight fingertips
        for tip in [4, 8, 12, 16, 20]:
            cv2.circle(frame, pts[tip], 7, (0, 255, 136), -1)
        # Wrist
        cv2.circle(frame, pts[0], 5, (255, 200, 0), -1)

    def _draw_hud(self, frame, gesture: str):
        import cv2
        h, w = frame.shape[:2]
        gcolor = {
            G_CURSOR:   (0, 212, 255),
            G_CLICK:    (255, 255, 0),
            G_RCLICK:   (255, 180, 0),
            G_SCROLL_U: (0, 255, 136),
            G_SCROLL_D: (0, 180, 100),
            G_VOL_UP:   (100, 255, 100),
            G_VOL_DN:   (100, 100, 255),
            G_SHOT:     (255, 80, 200),
            G_WAKE:     (255, 200, 0),
        }.get(gesture, (80, 80, 80))

        label = gesture.replace("_", " ")
        # Gesture label with background pill
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.9, 2)
        cv2.rectangle(frame, (8, 8), (18 + tw, 18 + th + 8), (0, 0, 0), -1)
        cv2.putText(frame, label, (13, 13 + th),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, gcolor, 2, cv2.LINE_AA)

        # Corner HUD brackets
        L = 28
        for (x, y, dx, dy) in [(6,6,1,1),(w-6,6,-1,1),(6,h-6,1,-1),(w-6,h-6,-1,-1)]:
            cv2.line(frame, (x,y), (x+dx*L,y), (0,212,255), 2)
            cv2.line(frame, (x,y), (x,y+dy*L), (0,212,255), 2)

    def _update_cursor(self, lm, gesture: str):
        if time.time() < self._freeze_cursor_until:
            return

        anchor_x, anchor_y = self._cursor_anchor(lm, gesture)
        tx = self._remap(anchor_x, 0.05, 0.95, 0, self._sw)
        ty = self._remap(anchor_y, 0.05, 0.85, 0, self._sh)
        tx = min(max(tx, 0), self._sw - 1)
        ty = min(max(ty, 0), self._sh - 1)

        if not self._initialized:
            self._smooth_x = tx
            self._smooth_y = ty
            self._prev_sx = tx
            self._prev_sy = ty
            self._initialized = True
            self._recent_cursor.append((int(tx), int(ty)))

        dx = tx - self._smooth_x
        dy = ty - self._smooth_y
        dist = math.hypot(dx, dy)
        if dist > MAX_JUMP:
            tx = self._smooth_x + dx / dist * MAX_JUMP
            ty = self._smooth_y + dy / dist * MAX_JUMP

        new_x = self._smooth_x * (1 - SMOOTH_ALPHA) + tx * SMOOTH_ALPHA
        new_y = self._smooth_y * (1 - SMOOTH_ALPHA) + ty * SMOOTH_ALPHA
        self._smooth_x = new_x
        self._smooth_y = new_y

        move_x = abs(new_x - self._prev_sx)
        move_y = abs(new_y - self._prev_sy)
        if move_x > DEAD_ZONE or move_y > DEAD_ZONE:
            px = int(new_x)
            py = int(new_y)
            self._prev_sx = new_x
            self._prev_sy = new_y
            self._recent_cursor.append((px, py))

            # ── Dwell-lock: freeze if cursor barely moved ─────────────────
            dist_from_dwell = math.hypot(px - self._dwell_cx, py - self._dwell_cy)
            if dist_from_dwell < DWELL_RADIUS:
                self._dwell_frames += 1
                if self._dwell_frames >= DWELL_FRAMES:
                    self._dwell_locked = True
                    # Stay at dwell centroid — don't move mouse
                    return
            else:
                self._dwell_frames = 0
                self._dwell_cx = px
                self._dwell_cy = py
                self._dwell_locked = False

            self._move_mouse(px, py)

    def _cursor_anchor(self, lm, gesture: str) -> tuple[float, float]:
        if gesture == G_RCLICK:
            return ((lm[8].x + lm[12].x) / 2.0, (lm[8].y + lm[12].y) / 2.0)
        if gesture == G_CLICK:
            # Index MCP (knuckle base, lm[5]) barely moves during pinch or curl
            # = rock-stable click position, zero drift
            return (lm[5].x, lm[5].y)
        return (lm[8].x, lm[8].y)

    @staticmethod
    def _remap(value: float, in_min: float, in_max: float, out_min: float, out_max: float) -> float:
        if in_max == in_min:
            return out_min
        ratio = (value - in_min) / (in_max - in_min)
        return out_min + ratio * (out_max - out_min)

    def _snap_to_median(self):
        """Snap cursor to the median of recent positions — most stable point."""
        if not self._recent_cursor:
            return
        xs = sorted(p[0] for p in self._recent_cursor)
        ys = sorted(p[1] for p in self._recent_cursor)
        n = len(xs)
        mx = (xs[n//2 - 1] + xs[n//2]) // 2 if n % 2 == 0 else xs[n//2]
        my = (ys[n//2 - 1] + ys[n//2]) // 2 if n % 2 == 0 else ys[n//2]
        self._frozen_x = float(mx)
        self._frozen_y = float(my)
        self._smooth_x = self._frozen_x
        self._smooth_y = self._frozen_y
        self._prev_sx  = self._frozen_x
        self._prev_sy  = self._frozen_y
        self._move_mouse(mx, my)

    def _stabilize_click_target(self):
        """Re-snap to median right before click fires."""
        self._snap_to_median()

    def _fire_action(self, gesture: str):
        now = time.time()
        if gesture == G_CLICK and (now - self._last_click) < CLICK_COOLDOWN:
            return
        if gesture in (G_CLICK, G_RCLICK):
            self._stabilize_click_target()
            self._freeze_cursor_until = now + CLICK_LOCK_SEC
        if gesture == G_CLICK:
            self._last_click = now
        log.info(f"Gesture fired: {gesture}")
        try:
            self.action_cb(gesture)
        except Exception as e:
            log.error(f"Action error: {e}")

    def _move_mouse(self, x: int, y: int):
        try:
            import pyautogui
            pyautogui.moveTo(x, y, duration=0)
        except Exception:
            pass
