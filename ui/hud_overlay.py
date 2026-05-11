"""
ui/hud_overlay.py
Iron Man-Style Transparent HUD Overlay for JarvisX.

Creates a transparent, click-through window overlaid on the desktop.
Displays: CPU, RAM, network speed, Jarvis status, emotion indicator,
          scanning arc animations, orbital ring effects.

Toggle: gesture or voice "Jarvis, show HUD" / "Jarvis, hide HUD"
"""
from __future__ import annotations
import threading
import time
import math
import logging
from typing import Optional

log = logging.getLogger("hud_overlay")

# HUD color scheme (Iron Man palette)
_C_CYAN    = "#00DCFF"
_C_GOLD    = "#FFB800"
_C_RED     = "#FF3C3C"
_C_GREEN   = "#00FF88"
_C_DIM     = "#1A3A4A"
_C_BG      = "#020D14"
_C_WHITE   = "#E0F8FF"

# Emotion → color
_EMOTION_COLORS = {
    "happy":   _C_GREEN,
    "neutral": _C_CYAN,
    "sad":     "#5599FF",
    "angry":   _C_RED,
    "fear":    "#FF8800",
    "disgust": "#AA44FF",
    "surprise": _C_GOLD,
}


class HUDOverlay:
    """
    Transparent tkinter window rendering Iron Man-style HUD over the desktop.
    Runs in its own thread with a 200ms refresh cycle.
    """

    def __init__(self, status_provider=None, emotion_provider=None, prediction_provider=None):
        self.status_provider   = status_provider    # callable → str
        self.emotion_provider  = emotion_provider   # callable → (emotion, stress)
        self.prediction_provider = prediction_provider  # callable → list[str]

        self._visible = False
        self._root    = None
        self._canvas  = None
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        # Live metrics
        self._cpu    = 0.0
        self._ram    = 0.0
        self._net_up = 0.0
        self._net_dn = 0.0
        self._status = "sleeping"
        self._emotion = "neutral"
        self._stress = 0.0
        self._prediction = ""
        self._anim_tick = 0
        self._scan_angle = 0.0

    # ── Public API ──────────────────────────────────────────────────────────────

    def show(self):
        """Show the HUD overlay."""
        with self._lock:
            if self._visible:
                return
            self._visible = True
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._run, daemon=True, name="hud-overlay")
            self._thread.start()
        else:
            if self._root:
                try:
                    self._root.after(0, self._root.deiconify)
                except Exception:
                    pass

    def hide(self):
        """Hide the HUD overlay."""
        with self._lock:
            self._visible = False
        if self._root:
            try:
                self._root.after(0, self._root.withdraw)
            except Exception:
                pass

    def toggle(self):
        if self._visible:
            self.hide()
        else:
            self.show()

    def is_visible(self) -> bool:
        return self._visible

    # ── Tkinter Thread ──────────────────────────────────────────────────────────

    def _run(self):
        import tkinter as tk
        try:
            self._root = tk.Tk()
            self._root.title("JarvisX HUD")
            self._root.overrideredirect(True)          # no title bar
            self._root.attributes("-topmost", True)    # always on top
            self._root.attributes("-alpha", 0.88)      # slight transparency
            self._root.configure(bg=_C_BG)
            self._root.attributes("-transparentcolor", _C_BG)

            # Position: bottom-right corner
            sw = self._root.winfo_screenwidth()
            sh = self._root.winfo_screenheight()
            W, H = 340, 220
            x = sw - W - 20
            y = sh - H - 60
            self._root.geometry(f"{W}x{H}+{x}+{y}")

            self._canvas = tk.Canvas(
                self._root, width=W, height=H,
                bg=_C_BG, highlightthickness=0,
            )
            self._canvas.pack()

            # Start metric collector
            self._metric_thread = threading.Thread(
                target=self._collect_metrics, daemon=True
            )
            self._metric_thread.start()

            self._root.after(200, self._update)
            self._root.mainloop()
        except Exception as e:
            log.error(f"HUD overlay error: {e}")

    def _update(self):
        """Redraw the HUD canvas every 200ms."""
        if not self._visible:
            if self._root:
                try:
                    self._root.withdraw()
                    self._root.after(500, self._update)
                except Exception:
                    pass
            return

        try:
            self._fetch_providers()
            self._draw()
            self._anim_tick += 1
            self._scan_angle = (self._scan_angle + 3) % 360
        except Exception as e:
            log.debug(f"HUD draw error: {e}")

        if self._root:
            self._root.after(200, self._update)

    def _fetch_providers(self):
        """Pull fresh data from provider callbacks."""
        if self.status_provider:
            try:
                self._status = self.status_provider() or "sleeping"
            except Exception:
                pass
        if self.emotion_provider:
            try:
                em, st = self.emotion_provider()
                self._emotion = em
                self._stress = st
            except Exception:
                pass
        if self.prediction_provider:
            try:
                preds = self.prediction_provider()
                self._prediction = preds[0] if preds else ""
            except Exception:
                pass

    def _draw(self):
        """Render the full HUD."""
        c = self._canvas
        c.delete("all")
        W, H = 340, 220

        # ── Background border ──────────────────────────────────────────────────
        c.create_rectangle(2, 2, W-2, H-2, outline=_C_CYAN, width=1)
        c.create_rectangle(6, 6, W-6, H-6, outline=_C_DIM, width=1)

        # ── Corner brackets (Iron Man style) ──────────────────────────────────
        sz = 14
        for (px, py, dx, dy) in [(2,2,1,1),(W-2,2,-1,1),(2,H-2,1,-1),(W-2,H-2,-1,-1)]:
            c.create_line(px, py, px+dx*sz, py, fill=_C_GOLD, width=2)
            c.create_line(px, py, px, py+dy*sz, fill=_C_GOLD, width=2)

        # ── Status orb (animated) ─────────────────────────────────────────────
        ox, oy = 44, 44
        r = 28
        status_color = {
            "listening": _C_GREEN,
            "thinking":  _C_GOLD,
            "speaking":  _C_CYAN,
            "sleeping":  _C_DIM,
            "private":   "#AA00FF",
        }.get(self._status, _C_CYAN)

        # Pulsing outer ring
        pulse = 0.5 + 0.5 * math.sin(self._anim_tick * 0.3)
        ring_r = int(r + 6 + 4 * pulse)
        c.create_oval(ox-ring_r, oy-ring_r, ox+ring_r, oy+ring_r,
                      outline=status_color, width=1)

        # Scanning arc
        c.create_arc(ox-r-8, oy-r-8, ox+r+8, oy+r+8,
                     start=self._scan_angle, extent=60,
                     outline=_C_CYAN, width=2, style="arc")

        # Core orb
        c.create_oval(ox-r, oy-r, ox+r, oy+r,
                      fill=_C_BG, outline=status_color, width=2)
        c.create_text(ox, oy, text="J", fill=status_color,
                      font=("Consolas", 18, "bold"))
        c.create_text(ox, oy+r+8, text=self._status.upper(),
                      fill=status_color, font=("Consolas", 7))

        # ── Metrics panel ─────────────────────────────────────────────────────
        mx = 90
        line_h = 22

        metrics = [
            ("CPU", f"{self._cpu:.1f}%",  self._bar_color(self._cpu / 100)),
            ("RAM", f"{self._ram:.1f}%",  self._bar_color(self._ram / 100)),
            ("↑",   f"{self._net_up:.1f}KB/s", _C_CYAN),
            ("↓",   f"{self._net_dn:.1f}KB/s", _C_GREEN),
        ]
        for i, (label, value, color) in enumerate(metrics):
            y = 14 + i * line_h
            c.create_text(mx, y, text=label, anchor="nw",
                          fill=_C_DIM, font=("Consolas", 8))
            c.create_text(mx + 30, y, text=value, anchor="nw",
                          fill=color, font=("Consolas", 9, "bold"))
            # Mini progress bar for CPU/RAM
            if label in ("CPU", "RAM"):
                pct = self._cpu / 100 if label == "CPU" else self._ram / 100
                bw = 100
                bx = mx + 80
                c.create_rectangle(bx, y+2, bx+bw, y+10, fill=_C_DIM, outline="")
                c.create_rectangle(bx, y+2, bx+int(bw*pct), y+10,
                                   fill=color, outline="")

        # ── Emotion indicator ─────────────────────────────────────────────────
        em_color = _EMOTION_COLORS.get(self._emotion, _C_CYAN)
        ey = 110
        c.create_text(mx, ey, text="MOOD", anchor="nw",
                      fill=_C_DIM, font=("Consolas", 7))
        c.create_text(mx+40, ey, text=self._emotion.upper(), anchor="nw",
                      fill=em_color, font=("Consolas", 9, "bold"))
        if self._stress > 0.6:
            c.create_text(mx+110, ey, text="⚠ STRESS",
                          fill=_C_RED, font=("Consolas", 7, "bold"))

        # ── Time ──────────────────────────────────────────────────────────────
        import datetime
        now = datetime.datetime.now()
        c.create_text(W//2, H-40, text=now.strftime("%H:%M:%S"),
                      fill=_C_CYAN, font=("Consolas", 20, "bold"))
        c.create_text(W//2, H-18, text=now.strftime("%A  %d %b %Y"),
                      fill=_C_DIM, font=("Consolas", 8))

        # ── Prediction chip ───────────────────────────────────────────────────
        if self._prediction:
            pred_text = f"→ {self._prediction[:28]}"
            c.create_rectangle(2, H-52, W-2, H-36, fill="#001820", outline=_C_DIM)
            c.create_text(8, H-44, text=pred_text, anchor="w",
                          fill=_C_GOLD, font=("Consolas", 7))

        # ── JARVIS label ──────────────────────────────────────────────────────
        c.create_text(W-8, 8, text="J.A.R.V.I.S", anchor="ne",
                      fill=_C_CYAN, font=("Consolas", 8, "bold"))

    @staticmethod
    def _bar_color(pct: float) -> str:
        if pct < 0.5:
            return _C_GREEN
        if pct < 0.8:
            return _C_GOLD
        return _C_RED

    def _collect_metrics(self):
        """Background thread: collect system metrics."""
        import psutil
        net_last = psutil.net_io_counters()
        t_last = time.time()
        while True:
            time.sleep(1.0)
            try:
                self._cpu = psutil.cpu_percent(interval=None)
                self._ram = psutil.virtual_memory().percent
                net = psutil.net_io_counters()
                t = time.time()
                dt = max(t - t_last, 0.1)
                self._net_up = (net.bytes_sent - net_last.bytes_sent) / dt / 1024
                self._net_dn = (net.bytes_recv - net_last.bytes_recv) / dt / 1024
                net_last = net
                t_last = t
            except Exception as e:
                log.debug(f"HUD metrics error: {e}")
