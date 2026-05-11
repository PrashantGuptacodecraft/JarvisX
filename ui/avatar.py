"""
ui/avatar.py
Animated face avatar with lip sync for JarvisX.
Renders a 2D animated face: eyes, eyebrows, mouth — synced to TTS phonemes.
"""
from __future__ import annotations
import threading, time, math, logging
from typing import Optional

log = logging.getLogger("avatar")

_BG="#020D14"; _C_CYAN="#00DCFF"; _C_GOLD="#FFB800"; _C_WHITE="#E0F8FF"

_PHONEME_MOUTH = {
    "A": 0.9, "E": 0.7, "I": 0.5, "O": 0.85, "U": 0.6,
    "M": 0.05, "B": 0.05, "P": 0.05,
}

_EXPRESSIONS = {
    "idle":      {"brow_raise": 0.0, "brow_furrow": 0.0, "eye_open": 0.8, "mouth": 0.05},
    "speaking":  {"brow_raise": 0.1, "brow_furrow": 0.0, "eye_open": 0.9, "mouth": 0.5},
    "thinking":  {"brow_raise": 0.0, "brow_furrow": 0.4, "eye_open": 0.5, "mouth": 0.0},
    "happy":     {"brow_raise": 0.3, "brow_furrow": 0.0, "eye_open": 1.0, "mouth": 0.8},
    "concerned": {"brow_raise": 0.0, "brow_furrow": 0.7, "eye_open": 0.7, "mouth": 0.2},
}

_W, _H = 220, 240


class AvatarFace:
    """
    Animated 2D face avatar rendered on a tkinter canvas.
    Displays expression states and lip-syncs to speech words.
    """

    def __init__(self):
        self._root   = None
        self._canvas = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._expression = "idle"
        self._mouth_open = 0.05
        self._blink_t    = 0.0
        self._anim_tick  = 0
        self._target_mouth = 0.05
        self._lock = threading.Lock()

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True, name="avatar")
        self._thread.start()

    def stop(self): self._running = False

    def set_expression(self, expression: str):
        with self._lock:
            self._expression = expression if expression in _EXPRESSIONS else "idle"

    def on_word(self, word: str):
        """Called for each TTS word to animate mouth."""
        if not word:
            return
        vowels = [c for c in word.upper() if c in _PHONEME_MOUTH]
        if vowels:
            with self._lock:
                self._target_mouth = max(m for m in [_PHONEME_MOUTH.get(v, 0.3) for v in vowels])
        else:
            with self._lock:
                self._target_mouth = 0.1

    def on_speaking_start(self):
        self.set_expression("speaking")

    def on_speaking_stop(self):
        self.set_expression("idle")
        with self._lock:
            self._target_mouth = 0.05

    def on_thinking(self):
        self.set_expression("thinking")

    def _run(self):
        import tkinter as tk
        self._root = tk.Tk()
        self._root.title("JarvisX Avatar")
        self._root.overrideredirect(True)
        self._root.attributes("-topmost", True, "-alpha", 0.93)
        self._root.configure(bg=_BG)
        sw = self._root.winfo_screenwidth()
        self._root.geometry(f"{_W}x{_H}+{sw - _W - 20}+20")
        self._canvas = tk.Canvas(self._root, width=_W, height=_H, bg=_BG, highlightthickness=0)
        self._canvas.pack()
        self._blink_t = time.time() + 3.0
        self._root.after(50, self._update)
        self._root.mainloop()

    def _update(self):
        if not self._running: return
        try:
            self._anim_tick += 1
            with self._lock:
                expr = _EXPRESSIONS.get(self._expression, _EXPRESSIONS["idle"])
                target = self._target_mouth
            # Smooth mouth transition
            self._mouth_open += (target - self._mouth_open) * 0.35
            self._draw(expr)
        except Exception as e:
            log.debug(f"Avatar draw error: {e}")
        if self._root: self._root.after(50, self._update)

    def _draw(self, expr: dict):
        c = self._canvas; c.delete("all")
        cx, cy = _W // 2, _H // 2 - 10

        # Face circle
        r = 80
        c.create_oval(cx-r, cy-r, cx+r, cy+r, fill="#040F18", outline=_C_CYAN, width=2)

        # Blink
        blink = 1.0
        if time.time() > self._blink_t:
            blink_progress = (time.time() - self._blink_t) * 6
            if blink_progress < 0.5:
                blink = max(0.0, 1.0 - blink_progress * 2)
            elif blink_progress < 1.0:
                blink = min(1.0, (blink_progress - 0.5) * 2)
            else:
                self._blink_t = time.time() + 2.5 + math.sin(self._anim_tick * 0.1) * 1.5

        eye_open = expr["eye_open"] * blink
        ey = cy - 20

        for ex in (cx - 28, cx + 28):
            ew, eh = 16, max(2, int(18 * eye_open))
            c.create_oval(ex-ew, ey-eh, ex+ew, ey+eh, fill="#020D14", outline=_C_CYAN, width=2)
            # Iris
            ir = max(1, int(8 * eye_open))
            c.create_oval(ex-ir, ey-ir, ex+ir, ey+ir, fill=_C_CYAN, outline="")
            # Pupil
            pr = max(1, ir // 2)
            c.create_oval(ex-pr, ey-pr, ex+pr, ey+pr, fill="#020D14", outline="")

            # Eyebrow
            br_y = ey - 25 - int(expr["brow_raise"] * 8)
            fur = int(expr["brow_furrow"] * 5)
            if ex < cx:  # left brow tilts right when furrowed
                c.create_line(ex-14, br_y+fur, ex+14, br_y-fur, fill=_C_CYAN, width=2)
            else:
                c.create_line(ex-14, br_y-fur, ex+14, br_y+fur, fill=_C_CYAN, width=2)

        # Mouth
        my = cy + 35
        mw = 40
        mh = max(2, int(22 * self._mouth_open))
        c.create_arc(cx-mw, my-mh, cx+mw, my+mh*0.5,
                     start=180, extent=180, style="chord",
                     fill="#020D14", outline=_C_CYAN, width=2)

        # Name tag
        with self._lock:
            expr_name = self._expression
        c.create_text(cx, _H - 20, text=f"J.A.R.V.I.S  [{expr_name}]",
                      fill=_C_CYAN, font=("Consolas", 8))

        # Outer ring decoration
        c.create_oval(cx-r-6, cy-r-6, cx+r+6, cy+r+6,
                      outline=_C_GOLD, width=1)
        angle = (self._anim_tick * 2) % 360
        c.create_arc(cx-r-6, cy-r-6, cx+r+6, cy+r+6,
                     start=angle, extent=45, outline=_C_CYAN, width=2, style="arc")
