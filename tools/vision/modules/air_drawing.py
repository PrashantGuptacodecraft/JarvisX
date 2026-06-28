"""
tools/vision/modules/air_drawing.py  — Ultra-Advanced Air Drawing v3
Fullscreen OpenCV window, accurate interpolated drawing, distinct gesture zones.

ACTIVATION: ☝✌📍 Three fingers held 1.5s  → fullscreen drawing window opens
IN DRAW MODE:
  ☝ Index only        = DRAW
  ✌ Peace sign        = LIFT PEN
  👌 Pinch            = Next BRUSH  (hold 0.3s to confirm, no false triggers)
  🤘 Rock sign        = Next COLOR  (hold 0.3s to confirm)
  🖐 Open palm        = UNDO
  👎 Thumb down 0.6s   = TOGGLE AUTO-CORRECT
  ✊ Fist hold 0.8s   = SAVE + EXIT (countdown shown)
"""
from __future__ import annotations
import cv2, math, numpy as np, os, time, logging
from collections import deque
from typing import Optional

log = logging.getLogger("air_drawing")

# ── Palette BGR ───────────────────────────────────────────────────────────────
PALETTE = [
    (0,255,100),(0,220,255),(255,100,0),(140,0,255),
    (0,140,255),(0,0,255),(255,255,255),(0,200,255),
]
PALETTE_NAMES = ["Green","Cyan","Blue","Violet","Orange","Red","White","Yellow"]
BRUSHES        = ["Pen","Marker","Spray","Neon","Chalk","Eraser"]
BRUSH_SIZES    = {"Pen":3,"Marker":12,"Spray":20,"Neon":4,"Chalk":9,"Eraser":35}

# ── Timing ────────────────────────────────────────────────────────────────────
ENTER_HOLD   = 1.5   # Three fingers hold time to activate drawing
EXIT_HOLD    = 0.8   # Fist hold time to save & exit
TOGGLE_HOLD  = 0.6   # Thumb-down hold time to toggle auto-correct
ACTION_HOLD  = 0.35  # Brush/color change hold time
UNDO_CD      = 0.5   # Undo cooldown

_SAVE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))))),
    "data", "drawings"
)
_WIN = "JARVIS Air Drawing"          # OpenCV window name


def _ext(lm, tip, mcp):
    return lm[tip].y < lm[mcp].y - 0.025

def _dist(a, b):
    return math.hypot(a.x - b.x, a.y - b.y)

def _classify_draw(lm) -> str:
    idx   = _ext(lm,  8, 5)
    mid   = _ext(lm, 12, 9)
    ring  = _ext(lm, 16,13)
    pinky = _ext(lm, 20,17)
    thumb_bent = lm[4].y >= lm[3].y - 0.01  # thumb tip below IP
    thumb_down = lm[4].y > lm[0].y + 0.05  # thumb tip below wrist
    if not any([idx,mid,ring,pinky]) and thumb_down: return "AUTO_TOGGLE"
    all_bent = not any([idx,mid,ring,pinky]) and thumb_bent
    if all_bent:                                  return "EXIT"
    if idx and mid and ring and pinky:            return "UNDO"
    if idx and pinky and not mid and not ring:    return "COLOR"
    if _dist(lm[4],lm[8]) < 0.07 and not mid and not ring and not pinky: return "BRUSH"
    if idx and mid and not ring and not pinky:    return "LIFT"
    if idx and not mid and not ring and not pinky: return "DRAW"
    return "NONE"


class _Stroke:
    def __init__(self, color, brush, size):
        self.color = color; self.brush = brush; self.size = size
        self.points: list[tuple[int,int]] = []


class AirDrawing:
    def __init__(self):
        self._canvas:  Optional[np.ndarray] = None
        self._active   = False
        self._color_i  = 0
        self._brush_i  = 0
        self._strokes: list[_Stroke] = []
        self._cur:     Optional[_Stroke]    = None
        self._prev_pt: Optional[tuple]      = None
        self._buf:     deque = deque(maxlen=6)   # smoothing buffer
        self._pen_up:  bool  = True             # true when pen is lifted / paused
        self._saved_msg: str = ""
        self._saved_msg_t: float = 0.0

        # Entry
        self._palm_t   = 0.0
        # Exit
        self._fist_t   = 0.0
        self._fist_started = False
        # Auto-correct toggle
        self._toggle_t = 0.0
        self._toggle_started = False
        self._auto_correct = True
        # Action hold (brush/color) — must be held ACTION_HOLD before firing
        self._action_g  = ""
        self._action_t  = 0.0
        self._action_fired = False
        # Undo
        self._last_undo = 0.0
        # Shape snap
        self._last_draw_t = 0.0
        self._shape_label = ""
        self._shape_label_t = 0.0
        # Fullscreen window size — use defaults, will detect on first draw
        self._fw = 1280
        self._fh = 720
        self._win_created = False
        self._last_win_check = 0.0
        os.makedirs(_SAVE_DIR, exist_ok=True)
        # AI integration (injected by gesture controller after init)
        self._ai_client = None
        self._memory    = None
        log.info("AirDrawing v3 ready — ☝✌📍 Three fingers 1.5s to activate")

    def set_ai_client(self, ai_client):
        """Inject AI client for canvas analysis on save."""
        self._ai_client = ai_client

    def set_memory(self, memory):
        """Inject memory manager for episode storage."""
        self._memory = memory

    # ── Module API ────────────────────────────────────────────────────────────
    def update(self, frame: np.ndarray, hand_data: dict,
               gesture_result: dict) -> None:
        lm  = hand_data.get("landmarks")
        now = time.time()

        if not self._active:
            self._check_entry(frame, lm, now)
            return

        # ── Fullscreen window management ──────────────────────────────────────
        now = time.time()
        if not self._win_created or (now - self._last_win_check > 0.5):
            self._last_win_check = now
            try:
                if cv2.getWindowProperty(_WIN, cv2.WND_PROP_VISIBLE) < 1:
                    self._open_window()
            except Exception:
                if not self._win_created:
                    self._open_window()

        # Build fullscreen canvas for display
        h, w = frame.shape[:2]
        if self._canvas is None or self._canvas.shape[:2] != (self._fh, self._fw):
            self._canvas = np.zeros((self._fh, self._fw, 4), np.uint8)

        # Scale camera frame to fullscreen
        display = cv2.resize(frame, (self._fw, self._fh))

        if lm is None:
            self._blend(display)
            self._hud(display, "NONE")
            cv2.imshow(_WIN, display)
            cv2.waitKey(1)
            return

        g = _classify_draw(lm)

        # ── AUTO-CORRECT TOGGLE: thumb-down ──────────────────────────────────────
        if g == "AUTO_TOGGLE":
            if self._toggle_t == 0.0:
                self._toggle_t = now
                self._toggle_started = True
            hold = now - self._toggle_t
            self._draw_countdown(display, hold, TOGGLE_HOLD, "TOGGLING AUTO…", (220,200,0))
            if hold >= TOGGLE_HOLD:
                self._auto_correct = not self._auto_correct
                self._saved_msg = "Auto correction " + ("ON" if self._auto_correct else "OFF")
                self._saved_msg_t = now
                self._toggle_t = 0.0
                self._toggle_started = False
            self._blend(display)
            cv2.imshow(_WIN, display); cv2.waitKey(1)
            return
        elif g == "EXIT":
            if self._fist_t == 0.0:
                self._fist_t = now
                self._fist_started = True
            hold = now - self._fist_t
            self._draw_countdown(display, hold, EXIT_HOLD, "SAVING…", (0,80,255))
            if hold >= EXIT_HOLD:
                self._save(display)
                self._active = False
                self._fist_t = 0.0
                self._fist_started = False
                try: cv2.destroyWindow(_WIN)
                except Exception: pass
            self._blend(display)
            cv2.imshow(_WIN, display); cv2.waitKey(1)
            return
        else:
            self._toggle_t = 0.0
            self._toggle_started = False
            self._fist_t = 0.0
            self._fist_started = False

        # ── ACTION gestures: require hold of ACTION_HOLD seconds ──────────────
        if g in ("BRUSH","COLOR","UNDO"):
            if g != self._action_g:
                self._action_g = g; self._action_t = now; self._action_fired = False
            elif not self._action_fired and (now - self._action_t) >= ACTION_HOLD:
                self._fire_action(g, display)
                self._action_fired = True
        else:
            self._action_g = ""; self._action_t = 0.0; self._action_fired = False

        # ── DRAW / LIFT ───────────────────────────────────────────────────────
        if g == "DRAW":
            if self._pen_up:
                self._buf.clear()
                self._prev_pt = None
                self._pen_up = False
            # Map landmark to fullscreen coords
            tx = int(lm[8].x * self._fw)
            ty = int(lm[8].y * self._fh)
            self._buf.append((tx, ty))
            self._last_draw_t = now

            if len(self._buf) >= 2:
                # Weighted average — heavier on recent points for responsiveness
                weights = list(range(1, len(self._buf)+1))
                wx = int(sum(p[0]*w for p,w in zip(self._buf,weights)) / sum(weights))
                wy = int(sum(p[1]*w for p,w in zip(self._buf,weights)) / sum(weights))
                pt = (wx, wy)

                if self._cur is None:
                    col   = PALETTE[self._color_i]
                    brush = BRUSHES[self._brush_i]
                    sz    = BRUSH_SIZES[brush]
                    self._cur = _Stroke(col, brush, sz)

                if self._prev_pt and self._cur:
                    # Interpolate intermediate points for dense lines (no gaps at fast moves)
                    self._interpolate_paint(self._canvas, self._prev_pt, pt, self._cur)
                    self._cur.points.append(pt)
                self._prev_pt = pt

        elif g == "LIFT":
            self._commit_stroke(now)
            self._pen_up = True
        else:
            if g not in ("BRUSH","COLOR","UNDO"):
                self._commit_stroke(now)
            self._pen_up = True

        self._blend(display)
        self._hud(display, g)
        cv2.imshow(_WIN, display)
        cv2.waitKey(1)

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _check_entry(self, frame, lm, now):
        if lm is None:
            self._palm_t = 0.0; return
        idx   = _ext(lm,  8, 5)
        mid   = _ext(lm, 12, 9)
        ring  = _ext(lm, 16,13)
        pinky = _ext(lm, 20,17)
        # Three fingers: index + middle + ring extended (pinky down)
        three_fingers = idx and mid and ring and not pinky
        if three_fingers:
            if self._palm_t == 0.0: self._palm_t = now
            hold = now - self._palm_t
            h, w = frame.shape[:2]
            angle = int(360 * min(hold/ENTER_HOLD, 1.0))
            cx, cy = w//2, h//2
            cv2.ellipse(frame,(cx,cy),(60,60),-90,0,angle,(0,220,255),4,cv2.LINE_AA)
            cv2.putText(frame,"☝✌📍 Hold to Draw",(cx-100,cy+80),
                        cv2.FONT_HERSHEY_SIMPLEX,0.8,(0,220,255),2,cv2.LINE_AA)
            if hold >= ENTER_HOLD:
                self._palm_t = 0.0
                self._canvas  = np.zeros((self._fh, self._fw, 4), np.uint8)
                self._strokes.clear(); self._cur = None; self._prev_pt = None
                self._buf.clear()
                self._active  = True
                self._open_window()
                log.info("Air drawing ON")
        else:
            self._palm_t = 0.0

    def _open_window(self):
        try:
            cv2.namedWindow(_WIN, cv2.WINDOW_NORMAL)
            cv2.setWindowProperty(_WIN, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
            cv2.setWindowProperty(_WIN, cv2.WND_PROP_TOPMOST, 1)
            self._win_created = True
        except Exception as e:
            log.warning("Window creation issue: %s", e)
            self._win_created = False

    def _fire_action(self, g: str, display: np.ndarray):
        now = time.time()
        # If the user changes brush/color while a stroke is open,
        # commit the current stroke so the new selection applies immediately.
        if self._cur is not None:
            self._commit_stroke(now)
        if g == "BRUSH":
            self._brush_i = (self._brush_i + 1) % len(BRUSHES)
            self._prev_pt = None; self._buf.clear()
            log.info("Brush → %s", BRUSHES[self._brush_i])
        elif g == "COLOR":
            self._color_i = (self._color_i + 1) % len(PALETTE)
            self._prev_pt = None; self._buf.clear()
            log.info("Color → %s", PALETTE_NAMES[self._color_i])
        elif g == "UNDO":
            if now - self._last_undo > UNDO_CD:
                self._last_undo = now
                if self._strokes:
                    self._strokes.pop()
                    self._redraw()

    def _commit_stroke(self, now: float):
        if self._cur and len(self._cur.points) > 1:
            self._snap(self._cur)
            self._strokes.append(self._cur)
        self._cur = None; self._prev_pt = None; self._buf.clear()

    def _interpolate_paint(self, canvas, p1, p2, stroke):
        """Dense interpolation: fill gaps when hand moves fast."""
        dx, dy = p2[0]-p1[0], p2[1]-p1[1]
        steps  = max(1, int(math.hypot(dx, dy) / max(1, stroke.size//2)))
        for i in range(steps+1):
            t = i / steps
            px = int(p1[0] + dx*t)
            py = int(p1[1] + dy*t)
            self._paint_dot(canvas, (px,py), stroke)

    def _paint_dot(self, canvas, pt, stroke):
        col, brush, size = stroke.color, stroke.brush, stroke.size
        bgra = (*col, 255)
        if brush == "Eraser":
            cv2.circle(canvas, pt, size, (0,0,0,0), -1)
            return
        if brush == "Pen":
            cv2.circle(canvas, pt, size, bgra, -1, cv2.LINE_AA)
        elif brush == "Marker":
            overlay = canvas.copy()
            cv2.circle(overlay, pt, size, (*col,130), -1, cv2.LINE_AA)
            cv2.addWeighted(overlay,0.5,canvas,0.5,0,canvas)
        elif brush == "Spray":
            rng = np.random.default_rng()
            for _ in range(28):
                ox = int(rng.normal(0, size*0.5))
                oy = int(rng.normal(0, size*0.5))
                px = max(0,min(canvas.shape[1]-1, pt[0]+ox))
                py = max(0,min(canvas.shape[0]-1, pt[1]+oy))
                canvas[py,px] = bgra
        elif brush == "Neon":
            cv2.circle(canvas, pt, size*4, (*col,50), -1, cv2.LINE_AA)
            cv2.circle(canvas, pt, size,   bgra,      -1, cv2.LINE_AA)
            cv2.circle(canvas, pt, max(1,size//2), (255,255,255,200), -1, cv2.LINE_AA)
        elif brush == "Chalk":
            rng = np.random.default_rng()
            for _ in range(10):
                ox = int(rng.integers(-size//2, size//2))
                oy = int(rng.integers(-size//2, size//2))
                a  = int(rng.integers(100,220))
                px = max(0,min(canvas.shape[1]-1, pt[0]+ox))
                py = max(0,min(canvas.shape[0]-1, pt[1]+oy))
                canvas[py,px] = (*col,a)

    def _redraw(self):
        self._canvas[:] = 0
        for s in self._strokes:
            for i in range(1, len(s.points)):
                self._interpolate_paint(self._canvas, s.points[i-1], s.points[i], s)

    def _snap(self, stroke):
        pts = np.array(stroke.points, dtype=np.int32)
        if len(pts) < 8: return
        try:
            contour = pts
            if not np.array_equal(pts[0], pts[-1]):
                contour = np.vstack([pts, pts[0]])
            hull = cv2.convexHull(contour)
            area = cv2.contourArea(hull)
            peri = cv2.arcLength(hull, True)
            if peri == 0 or area == 0: return
            compact = 4*math.pi*area / (peri**2)
            col  = stroke.color; t = max(2,stroke.size)
            bgra = (*col,255)

            approx = cv2.approxPolyDP(hull, max(0.02*peri, 10), True)
            num_sides = len(approx)
            rect = cv2.minAreaRect(hull)
            rect_area = rect[1][0] * rect[1][1] if rect[1][0] and rect[1][1] else 0
            fill_ratio = rect_area and area / rect_area or 0

            if num_sides == 3 and area > 160:
                self._set_shape_label("TRIANGLE")
                self._redraw_except_last()
                cv2.polylines(self._canvas, [approx], True, bgra, t, cv2.LINE_AA)
                log.info("Shape → TRIANGLE")

            elif self._looks_like_rectangle(approx, fill_ratio):
                self._set_shape_label("RECTANGLE")
                box = cv2.boxPoints(rect)
                box = np.int0(box)
                self._redraw_except_last()
                cv2.drawContours(self._canvas, [box], 0, bgra, t)
                log.info("Shape → RECTANGLE")

            elif num_sides > 7 and compact > 0.85 and fill_ratio > 0.55:
                self._set_shape_label("CIRCLE")
                (cx,cy),r = cv2.minEnclosingCircle(hull)
                self._redraw_except_last()
                cv2.circle(self._canvas,(int(cx),int(cy)),int(r),bgra,t,cv2.LINE_AA)
                log.info("Shape → CIRCLE")

            elif num_sides == 4:
                self._set_shape_label("QUADRILATERAL")
                self._redraw_except_last()
                cv2.polylines(self._canvas, [approx], True, bgra, t, cv2.LINE_AA)
                log.info("Shape → QUADRILATERAL")

            elif len(pts) >= 10:
                w, h = rect[1]
                if w == 0 or h == 0: return
                aspect = max(w,h) / min(w,h)
                if aspect > 10 and area / (w*h) < 0.35:
                    self._set_shape_label("LINE")
                    p1, p2 = tuple(map(int, pts[0])), tuple(map(int, pts[-1]))
                    self._redraw_except_last()
                    cv2.line(self._canvas, p1, p2, bgra, t, cv2.LINE_AA)
                    log.info("Shape → LINE")
            else:
                self._shape_label = ""
        except Exception as e:
            log.debug("Snap err: %s", e)

    def _is_rectangle(self, approx):
        if len(approx) != 4: return False
        points = approx.reshape(4, 2)
        vectors = []
        for i in range(4):
            p1 = points[i]
            p2 = points[(i+1)%4]
            vectors.append((p2[0]-p1[0], p2[1]-p1[1]))
        angles = []
        for i in range(4):
            v1 = vectors[i]
            v2 = vectors[(i+1)%4]
            dot = v1[0]*v2[0] + v1[1]*v2[1]
            mag1 = math.hypot(v1[0], v1[1])
            mag2 = math.hypot(v2[0], v2[1])
            if mag1 == 0 or mag2 == 0: return False
            cos_angle = dot / (mag1 * mag2)
            angle = math.acos(max(-1, min(1, cos_angle)))
            angles.append(math.degrees(angle))
        for a in angles:
            if not 75 < a < 105: return False
        return True

    def _looks_like_rectangle(self, approx, fill_ratio):
        if len(approx) == 4 and self._is_rectangle(approx):
            return True
        if len(approx) in (5, 6) and fill_ratio > 0.65:
            return self._has_rectangular_angles(approx)
        return False

    def _has_rectangular_angles(self, approx):
        points = approx.reshape(-1, 2)
        if len(points) < 4:
            return False
        vectors = []
        for i in range(len(points)):
            p1 = points[i]
            p2 = points[(i+1) % len(points)]
            vectors.append((p2[0]-p1[0], p2[1]-p1[1]))
        for i in range(len(vectors)):
            v1 = vectors[i]
            v2 = vectors[(i+1) % len(vectors)]
            mag1 = math.hypot(v1[0], v1[1])
            mag2 = math.hypot(v2[0], v2[1])
            if mag1 == 0 or mag2 == 0:
                return False
            cos_angle = (v1[0]*v2[0] + v1[1]*v2[1]) / (mag1 * mag2)
            angle = math.degrees(math.acos(max(-1.0, min(1.0, cos_angle))))
            if not 65 < angle < 115:
                return False
        return True

    def _redraw_except_last(self):
        self._canvas[:]=0
        for s in self._strokes[:-1]:
            for i in range(1, len(s.points)):
                self._interpolate_paint(self._canvas, s.points[i-1], s.points[i], s)

    def _blend(self, frame):
        if self._canvas is None: return
        a = self._canvas[:,:,3:4].astype(np.float32)/255.0
        np.copyto(frame,
                  (frame.astype(np.float32)*(1-a) +
                   self._canvas[:,:,:3].astype(np.float32)*a).astype(np.uint8))

    def _set_shape_label(self, label: str):
        self._shape_label = label
        self._shape_label_t = time.time()

    def _detect_screen_size(self) -> tuple[int, int]:
        try:
            import pyautogui
            return pyautogui.size()
        except Exception:
            try:
                import ctypes
                user32 = ctypes.windll.user32
                return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
            except Exception:
                return 1280, 720

    def _save(self, frame):
        ts   = time.strftime("%Y%m%d_%H%M%S")
        path = os.path.join(_SAVE_DIR, f"drawing_{ts}.png")
        if self._cur is not None:
            self._commit_stroke(time.time())
        canvas = np.ones((self._fh, self._fw, 3), np.uint8) * 255
        if self._canvas is not None:
            alpha = self._canvas[:, :, 3:4].astype(np.float32) / 255.0
            canvas = (canvas.astype(np.float32) * (1.0 - alpha) +
                      self._canvas[:, :, :3].astype(np.float32) * alpha).astype(np.uint8)
        cv2.imwrite(path, canvas)
        log.info("Saved: %s", path)
        self._saved_msg = f"Saved: {os.path.basename(path)}"
        self._saved_msg_t = time.time()
        # ── AI canvas analysis (background thread) ────────────────────────────
        self._ai_analyse_drawing(path)

    def _draw_countdown(self, frame, hold, total, text, color):
        fw, fh = frame.shape[1], frame.shape[0]
        angle  = int(360 * min(hold/total, 1.0))
        cx, cy = fw//2, fh//2
        cv2.ellipse(frame,(cx,cy),(70,70),-90,0,angle,color,6,cv2.LINE_AA)
        cv2.putText(frame, text,(cx-60,cy+10),
                    cv2.FONT_HERSHEY_SIMPLEX,1.0,color,2,cv2.LINE_AA)

    def _hud(self, frame, g: str):
        fw, fh = frame.shape[1], frame.shape[0]
        col    = PALETTE[self._color_i]
        brush  = BRUSHES[self._brush_i]
        sz     = BRUSH_SIZES[brush]

        # Top banner
        cv2.rectangle(frame,(0,0),(fw,42),(0,0,0),-1)
        cv2.putText(frame,"  ✌ LIFT/PAUSE  |  👌 BRUSH  |  🤘 COLOR  |  🖐 UNDO  |  👎hold AUTO  |  ✊hold EXIT",
                    (10,28),cv2.FONT_HERSHEY_SIMPLEX,0.6,(0,220,255),1,cv2.LINE_AA)

        # Top-right: brush swatch + name
        bx = fw - 180
        cv2.circle(frame,(bx,65),sz+5,col,-1,cv2.LINE_AA)
        cv2.putText(frame,brush,(bx+22,62),
                    cv2.FONT_HERSHEY_SIMPLEX,0.65,col,2,cv2.LINE_AA)
        cv2.putText(frame,PALETTE_NAMES[self._color_i],(bx+22,84),
                    cv2.FONT_HERSHEY_SIMPLEX,0.48,col,1,cv2.LINE_AA)

        # Bottom: state + strokes
        state     = "● DRAWING" if g=="DRAW" else "○ PEN UP"
        state_col = (0,255,100) if g=="DRAW" else (100,100,100)
        cv2.putText(frame, state,(12,fh-14),
                    cv2.FONT_HERSHEY_SIMPLEX,0.7,state_col,2,cv2.LINE_AA)
        cv2.putText(frame,f"Strokes:{len(self._strokes)}",(fw-140,fh-14),
                    cv2.FONT_HERSHEY_SIMPLEX,0.5,(180,180,180),1,cv2.LINE_AA)
        mode_text = "AUTO CORRECT" if self._auto_correct else "MANUAL DRAW"
        cv2.putText(frame, mode_text, (fw-340,fh-14),
                    cv2.FONT_HERSHEY_SIMPLEX,0.5,(0,220,255) if self._auto_correct else (180,180,180),1,cv2.LINE_AA)

        # Action hold progress bar (shows when holding brush/color/undo)
        if self._action_g and self._action_t:
            prog = min((time.time()-self._action_t)/ACTION_HOLD, 1.0)
            bw   = int(fw * prog)
            cv2.rectangle(frame,(0,fh-6),(bw,fh),(0,200,255),-1)

        # Save confirmation text
        if self._saved_msg and time.time() - self._saved_msg_t < 2.0:
            text = self._saved_msg
            (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.65, 2)
            cv2.rectangle(frame, (fw-20-tw, 50), (fw-10, 50+th+8), (0,0,0), -1)
            cv2.putText(frame, text, (fw-18-tw, 50+th),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0,255,100), 2, cv2.LINE_AA)
        elif time.time() - self._saved_msg_t >= 2.0:
            self._saved_msg = ""

        # Shape detection overlay
        if self._shape_label and time.time() - self._shape_label_t < 2.0:
            label = f"DETECTED: {self._shape_label}"
            (lw, lh), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2)
            cv2.rectangle(frame, ((fw-lw)//2 - 12, 50), ((fw+lw)//2 + 12, 50+lh+10), (0,0,0), -1)
            cv2.putText(frame, label, ((fw-lw)//2, 50+lh),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0,220,255), 2, cv2.LINE_AA)

    def clear(self):
        if self._canvas is not None: self._canvas[:] = 0
        self._strokes.clear(); self._cur = None; self._prev_pt = None

    def _ai_analyse_drawing(self, saved_path: str):
        """Background: send saved drawing to AI and store description as episode."""
        import threading
        def _run():
            if not self._ai_client:
                return
            try:
                desc = self._ai_client.chat_with_image(
                    "Describe this air drawing in one sentence. "
                    "What did the user draw? Be specific about shapes, symbols, or words visible.",
                    saved_path,
                )
                desc = (desc or "").strip()
                if desc:
                    log.info("AI drawing analysis: %s", desc)
                    # Update the save message with AI insight
                    self._saved_msg = f"Saved ✓  AI: {desc[:60]}"
                    self._saved_msg_t = time.time()
                    # Store in episodic memory
                    if self._memory and hasattr(self._memory, 'add_episode'):
                        self._memory.add_episode(
                            description=f"Air drawing saved: {desc}",
                            source="air_drawing",
                            tags="drawing,vision,canvas",
                        )
            except Exception as e:
                log.debug("AI drawing analysis failed: %s", e)
        threading.Thread(target=_run, daemon=True, name="air-drawing-ai").start()
