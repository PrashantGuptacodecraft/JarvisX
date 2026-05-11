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
G_SHOT_SEL  = "SCREENSHOT_SELECT"  # area-select screenshot mode
G_NONE      = "NONE"
_G_READY    = "_CLICK_READY"   # internal: two fingers up = armed, not exported
_G_PINCH    = "_PINCH"         # internal: thumb+index pinch = click

_BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MODEL_PATH = os.path.join(_BASE, "models", "hand_landmarker.task")

# ── Tuning ────────────────────────────────────────────────────────────────────
SMOOTH_ALPHA     = 0.35    # EMA cursor smoothing
DEAD_ZONE        = 5       # px: ignore micro-tremors
MAX_JUMP         = 120     # px: prevent teleport
CLICK_COOLDOWN   = 0.50    # seconds between clicks
POST_CLICK_FREEZE= 0.18    # seconds to freeze cursor after click fires
PRE_CLICK_FREEZE = 0.08    # seconds to freeze cursor before confirm
PINCH_THRESH     = 0.068   # normalised thumb-index distance for pinch click
CONFIRM_FRAMES   = 3       # non-cursor gesture confirmation frames
VOL_FRAMES       = 5       # volume confirmation frames (faster response)
CLICK_FRAMES     = 2       # click fires after 2 consistent frames
SCROLL_INTERVAL  = 0.07    # seconds between scroll ticks
SCROLL_AMOUNT    = 5       # scroll units per tick
SHOT_SEL_HOLD    = 0.6     # seconds to hold rock-sign to enter screenshot-select mode


def _dist(a, b) -> float:
    return math.hypot(a.x - b.x, a.y - b.y)


def _classify(lm) -> str:
    """
    Gesture classifier — pinch-based click system:
      ☝  index only              = CURSOR_MOVE
      🤏  thumb+index pinch      = LEFT_CLICK (most reliable)
      ✌  index+middle up        = _CLICK_READY (two-finger ready state)
      ✌→☝ close middle          = LEFT_CLICK  (two-finger fallback)
      🤘  index+pinky (rock)    = SCREENSHOT_SELECT mode
      👍  thumb up only         = VOLUME_UP
      👎  thumb down only       = VOLUME_DOWN
      🖐  open palm (4 fingers) = SCROLL_UP
      ✊  fist                  = SCROLL_DOWN
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

    # Pinch = thumb tip close to index tip → most reliable click
    pinch_dist = _dist(lm[THUMB_TIP], lm[IDX_TIP])
    if pinch_dist < PINCH_THRESH and not mid and not ring and not pinky:
        return _G_PINCH

    # Rock sign = screenshot-select (index + pinky, others bent)
    if idx and pinky and not mid and not ring:
        return G_SHOT

    # Fist = scroll DOWN (check early)
    if is_fist:
        return G_SCROLL_D

    # Volume (thumb only, all 4 fingers strictly bent — check BEFORE open palm)
    if thumb_up and not idx and not mid and not ring and not pinky:
        return G_VOL_UP
    if thumb_dn and not idx and not mid and not ring and not pinky:
        return G_VOL_DN

    # Open palm = scroll up (all 4 fingers extended)
    if sum([idx, mid, ring, pinky]) >= 4:
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
        self._last_click       = 0.0
        self._freeze_until     = 0.0
        self._click_detected_t = 0.0

        # Gesture confirmation buffer
        self._buf: list[str] = []
        self._last_g = G_NONE

        # Two-finger click state fallback
        self._armed = False

        # Pinch click state
        self._pinch_frames = 0      # consecutive pinch frames seen
        self._pinch_fired  = False  # did this pinch already fire?

        # Screenshot area-select state
        self._shot_mode    = False  # True when in area-select mode
        self._shot_start   = None   # (x,y) screen coords of first corner
        self._shot_overlay = None   # current drag end point
        self._rock_since   = 0.0    # time rock-sign first held

        # Continuous scroll
        self._last_scroll = 0.0

        # Screen size
        try:
            import pyautogui
            self._sw, self._sh = pyautogui.size()
        except Exception:
            self._sw, self._sh = 1920, 1080

        # Gesture history for HUD
        self.gesture_history: deque = deque(maxlen=6)

        # Feature modules — created fresh in start() so features.json is current
        self._module_mgr = None
        self._air_drawing_ref = None   # direct ref for toggle_draw_mode()

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
        # Reload modules fresh so features.json changes are picked up
        if _MODULES_AVAILABLE:
            self._module_mgr = ModuleManager()
            # Keep a direct reference to AirDrawing if loaded
            for mod in self._module_mgr._modules:
                if mod.__class__.__name__ == "AirDrawing":
                    self._air_drawing_ref = mod
                    # Inject AI client + memory for canvas analysis
                    if hasattr(self, "_ai_client") and self._ai_client:
                        mod.set_ai_client(self._ai_client)
                    if hasattr(self, "_memory") and self._memory:
                        mod.set_memory(self._memory)
                    break
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

    def toggle_draw_mode(self) -> bool:
        """Activate or deactivate Air Drawing Mode directly (no gesture needed).
        Returns True if draw mode is now ON, False if OFF.
        """
        if self._air_drawing_ref is None:
            log.warning("AirDrawing module not loaded — check features.json air_drawing:true")
            return False
        ad = self._air_drawing_ref
        if ad._active:
            ad._active = False
            try:
                import cv2 as _cv
                _cv.destroyWindow("JARVIS Air Drawing")
            except Exception:
                pass
            log.info("Air Drawing deactivated via toggle")
            return False
        else:
            import numpy as np
            ad._canvas = np.zeros((ad._fh, ad._fw, 4), np.uint8)
            ad._strokes.clear()
            ad._cur = None
            ad._prev_pt = None
            ad._buf.clear()
            ad._active = True
            ad._open_window()
            log.info("Air Drawing activated via toggle")
            return True

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
            num_hands=2,
            min_hand_detection_confidence=0.65,
            min_hand_presence_confidence=0.55,
            min_tracking_confidence=0.55,
        )

        # Try DirectShow first (faster on Windows), fall back to default
        cap = cv2.VideoCapture(self.cam_index, cv2.CAP_DSHOW)
        if not cap.isOpened():
            cap = cv2.VideoCapture(self.cam_index)
        # 1280x720 gives better landmark accuracy for air drawing
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
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

                            now_t = time.time()
                            # ── Screenshot area-select mode ───────────────
                            if self._shot_mode:
                                # In select mode: pinch = set corner, move = drag
                                if gesture == _G_PINCH:
                                    sx = int(self._sx)
                                    sy = int(self._sy)
                                    if self._shot_start is None:
                                        self._shot_start = (sx, sy)
                                    else:
                                        # Second pinch = capture region
                                        self._do_region_screenshot(
                                            self._shot_start, (sx, sy))
                                        self._shot_mode  = False
                                        self._shot_start = None
                                elif gesture == G_CURSOR:
                                    self._update_cursor(lm[8].x, lm[8].y)
                                    self._shot_overlay = (int(self._sx), int(self._sy))
                                continue  # skip normal processing in select mode

                            # ── Pinch = left click (most reliable) ────────
                            if gesture == _G_PINCH:
                                self._pinch_frames += 1
                                self._armed = False
                                if (self._pinch_frames >= 2
                                        and not self._pinch_fired
                                        and now_t >= self._freeze_until):
                                    self._pinch_fired = True
                                    self._fire(G_CLICK)
                            else:
                                # Reset pinch when released
                                if self._pinch_fired or self._pinch_frames > 0:
                                    self._pinch_frames = 0
                                    self._pinch_fired  = False

                            # ── Rock-sign held → enter screenshot select ──
                            if gesture == G_SHOT:
                                if self._air_drawing_ref is not None and self._air_drawing_ref._active:
                                    self._rock_since = 0.0
                                elif self._rock_since == 0.0:
                                    self._rock_since = now_t
                                elif now_t - self._rock_since >= SHOT_SEL_HOLD:
                                    # Held long enough → area-select mode
                                    self._shot_mode  = True
                                    self._shot_start = None
                                    self._rock_since = 0.0
                                    log.info("Screenshot area-select mode ON")
                            else:
                                self._rock_since = 0.0

                            # ── Two-finger armed state (fallback click) ───
                            if gesture == '_CLICK_READY':
                                self._armed = True
                                if now_t >= self._freeze_until:
                                    mx = (lm[8].x + lm[12].x) / 2
                                    my = (lm[8].y + lm[12].y) / 2
                                    self._update_cursor(mx, my)
                            elif gesture == G_CURSOR:
                                if self._armed and now_t >= self._freeze_until:
                                    self._armed = False
                                    self._fire(G_CLICK)
                                elif not self._armed:
                                    self._armed = False
                                if now_t >= self._freeze_until:
                                    self._update_cursor(lm[8].x, lm[8].y)
                            else:
                                self._armed = False

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
        if self._air_drawing_ref is not None and self._air_drawing_ref._active:
            if gesture in (G_SHOT, G_SHOT_SEL):
                log.debug("Ignored screenshot gesture while Air Drawing active: %s", gesture)
                return
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

    def _do_region_screenshot(self, p1: tuple, p2: tuple) -> None:
        """Capture screen region between two corner points and save."""
        try:
            import pyautogui, datetime, os
            x1, y1 = min(p1[0], p2[0]), min(p1[1], p2[1])
            x2, y2 = max(p1[0], p2[0]), max(p1[1], p2[1])
            w_r, h_r = max(10, x2-x1), max(10, y2-y1)
            img = pyautogui.screenshot(region=(x1, y1, w_r, h_r))
            ts  = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            path = os.path.join(os.path.expanduser("~"), "Pictures",
                                f"jarvis_region_{ts}.png")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            img.save(path)
            log.info("Region screenshot saved: %s", path)
            self.action_cb(G_SHOT_SEL)  # notify controller
        except Exception as e:
            log.error("Region screenshot failed: %s", e)

    def _draw_hud(self, frame, gesture: str, w: int, h: int) -> None:
        import cv2
        # Draw screenshot selection rectangle overlay
        if self._shot_mode and self._shot_start and self._shot_overlay:
            # Convert screen coords back to frame coords for display
            sx0 = int(self._shot_start[0]  / self._sw * w)
            sy0 = int(self._shot_start[1]  / self._sh * h)
            sx1 = int(self._shot_overlay[0]/ self._sw * w)
            sy1 = int(self._shot_overlay[1]/ self._sh * h)
            cv2.rectangle(frame, (sx0,sy0), (sx1,sy1), (0,255,255), 2)
            cv2.putText(frame, "PINCH to capture", (10, h-20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,255), 2)
        if self._shot_mode:
            cv2.putText(frame, "SELECT MODE", (w//2-70, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0,255,255), 2)

        COLOR = {
            G_CURSOR: (0, 212, 255), G_CLICK: (0, 255, 100),
            G_RCLICK: (255, 180, 0), G_SCROLL_U: (100, 255, 100),
            G_SCROLL_D: (100, 100, 255), G_VOL_UP: (200, 255, 200),
            G_VOL_DN: (200, 200, 255), G_SHOT: (255, 80, 200),
            G_SHOT_SEL: (0, 255, 255), G_WAKE: (255, 200, 0),
            _G_PINCH: (0, 255, 50),
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
