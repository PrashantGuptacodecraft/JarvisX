"""
tools/vision/gesture_engine.py
Simple, reliable gesture engine — single thread, proven cursor logic.
Uses joint-angle finger detection from core/finger_analyzer.py.
"""
from __future__ import annotations
import logging
import math
import os
import threading
import time
from collections import deque
from typing import Callable, Optional

log = logging.getLogger("gesture_engine")

try:
    from tools.vision.modules import ModuleManager
    _MODULES_AVAILABLE = True
except Exception:
    _MODULES_AVAILABLE = False
    ModuleManager = None


# ── Re-export gesture names (controller compatibility) ────────────────────────
G_CURSOR    = "CURSOR_MOVE"
G_CLICK     = "LEFT_CLICK"
G_RCLICK    = "RIGHT_CLICK"
G_SCROLL_U  = "SCROLL_UP"
G_SCROLL_D  = "SCROLL_DOWN"
G_VOL_UP    = "VOLUME_UP"
G_VOL_DN    = "VOLUME_DOWN"
G_WAKE      = "WAKE_JARVIS"
G_SHOT      = "SCREENSHOT"
G_NONE      = "NONE"
_G_READY    = "_CLICK_READY"   # internal: two fingers up = armed, not exported

_BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MODEL_PATH = os.path.join(_BASE, "models", "hand_landmarker.task")

# ── Tuning ────────────────────────────────────────────────────────────────────
SMOOTH_ALPHA     = 0.30    # EMA cursor speed
DEAD_ZONE        = 6       # px: ignore micro-tremors
MAX_JUMP         = 130     # px: prevent teleport
CLICK_COOLDOWN   = 0.55    # seconds between clicks
POST_CLICK_FREEZE= 0.22    # seconds to freeze cursor after click fires
PRE_CLICK_FREEZE = 0.10    # seconds to freeze cursor when click detected (before confirm)
PINCH_THRESH     = 0.075   # normalised thumb-index distance
CONFIRM_FRAMES   = 4       # non-cursor gesture confirmation frames
VOL_FRAMES       = 7       # volume confirmation frames
CLICK_FRAMES     = 2       # click fires after 2 consistent frames
SCROLL_INTERVAL  = 0.08    # seconds between continuous scroll ticks when held
SCROLL_AMOUNT    = 4       # scroll units per tick


def _dist(a, b) -> float:
    return math.hypot(a.x - b.x, a.y - b.y)


def _classify(lm) -> str:
    """
    Classify hand landmarks into a gesture.
    TWO-FINGER CLICK SYSTEM:
      ☝  index only          = cursor move
      ✌  index + middle      = CLICK_READY (cursor still moves, click armed)
      ☝  close middle again  = LEFT CLICK (handled in engine state machine)
    """
    W = 0
    THUMB_TIP, THUMB_IP    = 4, 3
    IDX_MCP, IDX_TIP, IDX_PIP, IDX_DIP = 5, 8, 6, 7
    MID_TIP, MID_PIP       = 12, 10
    RNG_TIP, RNG_PIP       = 16, 14
    PKY_TIP, PKY_PIP       = 20, 18

    # finger EXTENDED: tip clearly above MCP (knuckle) — very reliable
    def ext(tip, mcp):
        return lm[tip].y < lm[mcp].y - 0.02

    # finger BENT: tip at or below MCP — reliable fist check
    def bent(tip, mcp):
        return lm[tip].y >= lm[mcp].y - 0.01

    idx   = ext(IDX_TIP, 5)   # index extended
    mid   = ext(MID_TIP, 9)   # middle extended
    ring  = ext(RNG_TIP, 13)  # ring extended
    pinky = ext(PKY_TIP, 17)  # pinky extended

    # PIP-based for two-finger click (finer granularity)
    idx_pip   = lm[IDX_TIP].y < lm[IDX_PIP].y - 0.018
    mid_pip   = lm[MID_TIP].y < lm[MID_PIP].y - 0.018

    # Fist: ALL 4 fingertips below/at their MCP knuckles
    idx_bent  = bent(IDX_TIP, 5)
    mid_bent  = bent(MID_TIP, 9)
    ring_bent = bent(RNG_TIP, 13)
    pky_bent  = bent(PKY_TIP, 17)
    is_fist   = idx_bent and mid_bent and ring_bent and pky_bent

    thumb_h  = lm[THUMB_TIP].x > lm[THUMB_IP].x + 0.03
    thumb_up = lm[THUMB_TIP].y < lm[W].y - 0.10
    thumb_dn = lm[THUMB_TIP].y > lm[W].y + 0.05

    # Rock sign = screenshot (must check before fist)
    if idx and pinky and not mid and not ring:
        return G_SHOT

    # Fist = scroll DOWN (check early, before palm, using reliable bent test)
    if is_fist:
        return G_SCROLL_D

    # Volume (thumb only, all fingers bent)
    if thumb_up and not idx and not mid and not ring and not pinky:
        return G_VOL_UP
    if thumb_dn and not idx and not mid and not ring and not pinky:
        return G_VOL_DN

    # Open palm = scroll up (4+ fingers extended via MCP test)
    if sum([idx, mid, ring, pinky]) >= 3:
        return G_SCROLL_U

    # Right click = index + middle + ring
    if idx and mid and ring and not pinky:
        return G_RCLICK

    # TWO-FINGER CLICK-READY: index + middle up, others down
    # Cursor still moves — closing middle fires click (handled in engine)
    if idx and mid and not ring and not pinky:
        return _G_READY

    # Cursor = only index up
    if idx and not mid and not ring and not pinky:
        return G_CURSOR

    # Wake
    if sum([thumb_h, idx, mid, ring, pinky]) >= 4 and lm[W].y < 0.35:
        return G_WAKE

    return G_NONE


class GestureEngine:
    """
    Reliable single-thread gesture engine.
    Cursor: index tip → EMA smooth → move mouse every frame.
    Actions: N-frame confirmation buffer before firing.
    """

    def __init__(self, action_callback: Callable[[str], None],
                 frame_callback: Optional[Callable] = None,
                 cam_index: int = 0) -> None:
        self.action_cb = action_callback
        self.frame_cb  = frame_callback
        self.cam_index = cam_index
        self._running  = False
        self._thread: Optional[threading.Thread] = None
        self._paused   = False

        # Cursor EMA state
        self._sx = 0.0
        self._sy = 0.0
        self._px = 0.0
        self._py = 0.0
        self._init = False

        # Click timing & freeze
        self._last_click      = 0.0
        self._freeze_until    = 0.0   # hard freeze: no cursor movement
        self._click_detected_t = 0.0  # when click gesture first seen (pre-freeze)

        # Gesture confirmation buffer
        self._buf: list[str] = []
        self._last_g = G_NONE

        # Two-finger click state: True when index+middle seen (READY)
        # Drops to G_CURSOR next frame = CLICK fires
        self._armed = False

        # Continuous scroll: track last scroll time for repeat-while-held
        self._last_scroll = 0.0

        # Screen size
        try:
            import pyautogui
            self._sw, self._sh = pyautogui.size()
        except Exception:
            self._sw, self._sh = 1920, 1080

        # Gesture history for HUD
        self.gesture_history: deque = deque(maxlen=6)

        # Feature modules (air_drawing, heatmap, VGF, AR)
        self._module_mgr = ModuleManager() if _MODULES_AVAILABLE else None

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self, command_queue=None) -> bool:
        if self._running:
            return True
        if not os.path.exists(MODEL_PATH):
            log.error("Model not found: %s", MODEL_PATH)
            return False
        try:
            import mediapipe, cv2  # noqa
        except ImportError as e:
            log.error("Missing deps: %s", e)
            return False
        self._running = True
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="gesture-engine"
        )
        self._thread.start()
        log.info("GestureEngine started")
        return True

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)

    def toggle(self, cam_index: int = 0) -> bool:
        if self._running:
            self.stop()
            return False
        self.cam_index = cam_index
        return self.start()

    def pause(self):  self._paused = True
    def resume(self): self._paused = False

    def set_mode(self, mode: str) -> None:
        log.info("Mode: %s", mode)

    # ── Main loop ─────────────────────────────────────────────────────────────

    def _loop(self) -> None:
        import cv2
        import mediapipe as mp

        HandLandmarker        = mp.tasks.vision.HandLandmarker
        HandLandmarkerOptions = mp.tasks.vision.HandLandmarkerOptions
        RunningMode           = mp.tasks.vision.RunningMode
        BaseOptions           = mp.tasks.BaseOptions
        MpImage               = mp.Image
        MpFmt                 = mp.ImageFormat

        opts = HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=MODEL_PATH),
            running_mode=RunningMode.IMAGE,
            num_hands=1,
            min_hand_detection_confidence=0.60,
            min_hand_presence_confidence=0.50,
            min_tracking_confidence=0.50,
        )

        # Try DirectShow first (faster on Windows), fall back to default
        cap = cv2.VideoCapture(self.cam_index, cv2.CAP_DSHOW)
        if not cap.isOpened():
            cap = cv2.VideoCapture(self.cam_index)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        cap.set(cv2.CAP_PROP_FPS, 30)

        with HandLandmarker.create_from_options(opts) as landmarker:
            while self._running:
                t0 = time.time()
                ret, frame = cap.read()
                if not ret:
                    time.sleep(0.04)
                    continue

                frame   = cv2.flip(frame, 1)
                h, w    = frame.shape[:2]
                gesture = G_NONE
                result  = None   # BUG1 FIX: reset each frame
                lm      = None   # BUG1 FIX: reset each frame

                if not self._paused:
                    try:
                        rgb    = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        result = landmarker.detect(
                            MpImage(image_format=MpFmt.SRGB, data=rgb)
                        )
                        if result.hand_landmarks:
                            lm = result.hand_landmarks[0]
                            gesture = _classify(lm)

                            # ── Cursor anchor logic ───────────────────────
                            # State machine: _G_READY -> G_CURSOR = CLICK
                            if gesture == '_CLICK_READY':
                                # Two fingers up: cursor moves via index+mid midpoint
                                self._armed = True
                                if time.time() >= self._freeze_until:
                                    mx = (lm[8].x + lm[12].x) / 2
                                    my = (lm[8].y + lm[12].y) / 2
                                    self._update_cursor(mx, my)
                                self._click_detected_t = 0.0
                            elif gesture == G_CURSOR:
                                if self._armed:
                                    # READY -> CURSOR transition = LEFT CLICK!
                                    self._armed = False
                                    if time.time() >= self._freeze_until:
                                        self._fire(G_CLICK)
                                self._click_detected_t = 0.0
                                if time.time() >= self._freeze_until:
                                    self._update_cursor(lm[8].x, lm[8].y)
                            elif gesture == G_CLICK:
                                self._armed = False
                                if self._click_detected_t == 0.0:
                                    self._click_detected_t = time.time()
                                    self._freeze_until = time.time() + PRE_CLICK_FREEZE
                                if time.time() < self._freeze_until:
                                    pass
                                else:
                                    self._update_cursor(lm[5].x, lm[5].y)
                            else:
                                self._armed = False
                                self._click_detected_t = 0.0

                            self._draw_skeleton(frame, lm, w, h)
                    except Exception as e:
                        log.debug("Detection error: %s", e)

                    # ── Gesture confirmation buffer ────────────────────────
                    if gesture == G_CLICK:
                        need = CLICK_FRAMES
                    elif gesture in (G_VOL_UP, G_VOL_DN):
                        need = VOL_FRAMES
                    else:
                        need = CONFIRM_FRAMES

                    self._buf.append(gesture)
                    if len(self._buf) > need:
                        self._buf.pop(0)

                    # _G_READY and cursor are pass-through
                    _pass = (G_NONE, G_CURSOR, '_CLICK_READY')

                    # ── Continuous scroll while gesture held ───────────────
                    if gesture in (G_SCROLL_U, G_SCROLL_D):
                        now_s = time.time()
                        if now_s - self._last_scroll >= SCROLL_INTERVAL:
                            self._last_scroll = now_s
                            try:
                                import pyautogui as _pa
                                # Wrist-height speed control (one hand only):
                                # Hand HIGH in frame (y < 0.30)  = FAST scroll (3x)
                                # Hand MID  in frame (y 0.30-0.55) = NORMAL  (1.5x)
                                # Hand LOW  in frame (y > 0.55)  = SLOW scroll (1x)
                                if result.hand_landmarks:
                                    wrist_y = result.hand_landmarks[0][0].y
                                    if wrist_y < 0.30:
                                        speed_mult = 3
                                    elif wrist_y < 0.55:
                                        speed_mult = 2
                                    else:
                                        speed_mult = 1
                                else:
                                    speed_mult = 1
                                amt = SCROLL_AMOUNT * speed_mult
                                if gesture == G_SCROLL_D:
                                    amt = -amt
                                _pa.scroll(int(amt))
                            except Exception:
                                pass
                        # Skip normal confirm buffer for scroll
                        self._last_g = gesture
                        self._buf.clear()
                    elif (len(self._buf) == need
                            and all(g == gesture for g in self._buf)
                            and gesture not in _pass
                            and gesture != self._last_g):
                        self._last_g = gesture
                        self._fire(gesture)
                    elif gesture in _pass and gesture != self._last_g:
                        self._last_g = gesture
                        self._buf.clear()
                    elif gesture not in (G_SCROLL_U, G_SCROLL_D):
                        self._last_scroll = 0.0  # reset scroll when gesture changes

                # Feature modules update (only when not paused)
                if self._module_mgr is not None and not self._paused:
                    _lm = result.hand_landmarks[0] if (result and result.hand_landmarks) else None
                    _hd = {'landmarks': _lm, 'handedness': 'right'}
                    _gr = {'name': gesture, 'confidence': 1.0,
                           'cursor_x': int(self._sx), 'cursor_y': int(self._sy)}
                    frame, _fused = self._module_mgr.update(frame, _hd, _gr)
                    if _fused:
                        try: self.action_cb(_fused)
                        except Exception: pass

                # HUD + frame callback
                self._draw_hud(frame, gesture, w, h)
                if self.frame_cb:
                    import cv2 as cv
                    self.frame_cb(cv.cvtColor(frame, cv.COLOR_BGR2RGB), gesture)

                # Throttle to ~30 fps
                elapsed = time.time() - t0
                time.sleep(max(0, 0.033 - elapsed))

        cap.release()

    # ── Cursor update ─────────────────────────────────────────────────────────

    def _update_cursor(self, nx: float, ny: float) -> None:
        """Map normalized landmark to screen, EMA smooth, move mouse."""
        # Map with margin crop (ignores extreme edges of frame)
        tx = self._remap(nx, 0.10, 0.90, 0, self._sw)
        ty = self._remap(ny, 0.10, 0.85, 0, self._sh)
        tx = max(0.0, min(tx, self._sw - 1))
        ty = max(0.0, min(ty, self._sh - 1))

        if not self._init:
            self._sx = tx; self._sy = ty
            self._px = tx; self._py = ty
            self._init = True

        # Jump cap
        dx, dy = tx - self._sx, ty - self._sy
        d = math.hypot(dx, dy)
        if d > MAX_JUMP:
            tx = self._sx + dx / d * MAX_JUMP
            ty = self._sy + dy / d * MAX_JUMP

        # EMA smooth
        self._sx = self._sx * (1 - SMOOTH_ALPHA) + tx * SMOOTH_ALPHA
        self._sy = self._sy * (1 - SMOOTH_ALPHA) + ty * SMOOTH_ALPHA

        # Dead zone
        if math.hypot(self._sx - self._px, self._sy - self._py) > DEAD_ZONE:
            self._px = self._sx
            self._py = self._sy
            self._move_mouse(int(self._sx), int(self._sy))

    # ── Gesture fire ──────────────────────────────────────────────────────────

    def _fire(self, gesture: str) -> None:
        now = time.time()
        if gesture == G_CLICK and (now - self._last_click) < CLICK_COOLDOWN:
            return
        if gesture == G_CLICK:
            self._last_click = now
            # Freeze cursor after click so it stays on the target
            self._freeze_until = now + POST_CLICK_FREEZE
            self._click_detected_t = 0.0
        self.gesture_history.append((gesture, now))
        log.info("Gesture: %s", gesture)
        try:
            self.action_cb(gesture)
        except Exception as e:
            log.error("action_cb: %s", e)

    # ── Drawing ───────────────────────────────────────────────────────────────

    def _draw_skeleton(self, frame, lm, w: int, h: int) -> None:
        import cv2
        PAIRS = [(0,1),(1,2),(2,3),(3,4),(0,5),(5,6),(6,7),(7,8),
                 (0,9),(9,10),(10,11),(11,12),(0,13),(13,14),(14,15),(15,16),
                 (0,17),(17,18),(18,19),(19,20),(5,9),(9,13),(13,17),(5,17)]
        pts = [(int(p.x * w), int(p.y * h)) for p in lm]
        for a, b in PAIRS:
            cv2.line(frame, pts[a], pts[b], (255, 255, 255), 1, cv2.LINE_AA)
        for tip in [4, 8, 12, 16, 20]:
            cv2.circle(frame, pts[tip], 6, (0, 255, 136), -1, cv2.LINE_AA)
        cv2.circle(frame, pts[0], 5, (255, 200, 0), -1, cv2.LINE_AA)

    def _draw_hud(self, frame, gesture: str, w: int, h: int) -> None:
        import cv2
        COLOR = {
            G_CURSOR: (0, 212, 255), G_CLICK: (0, 255, 100),
            G_RCLICK: (255, 180, 0), G_SCROLL_U: (100, 255, 100),
            G_SCROLL_D: (100, 100, 255), G_VOL_UP: (200, 255, 200),
            G_VOL_DN: (200, 200, 255), G_SHOT: (255, 80, 200),
            G_WAKE: (255, 200, 0),
        }.get(gesture, (80, 80, 80))

        label = gesture.replace("_", " ")
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.85, 2)
        cv2.rectangle(frame, (8, 8), (20 + tw, 22 + th), (0, 0, 0), -1)
        cv2.putText(frame, label, (13, 14 + th),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.85, COLOR, 2, cv2.LINE_AA)

        L = 26
        for (x, y, dx, dy) in [(6,6,1,1),(w-6,6,-1,1),(6,h-6,1,-1),(w-6,h-6,-1,-1)]:
            cv2.line(frame, (x,y), (x+dx*L, y), (0, 200, 255), 2)
            cv2.line(frame, (x,y), (x, y+dy*L), (0, 200, 255), 2)

    @staticmethod
    def _remap(v, lo, hi, out_lo, out_hi) -> float:
        if hi == lo:
            return out_lo
        return out_lo + (v - lo) / (hi - lo) * (out_hi - out_lo)

    def _move_mouse(self, x: int, y: int) -> None:
        try:
            import pyautogui
            pyautogui.moveTo(x, y, duration=0)
        except Exception:
            pass
