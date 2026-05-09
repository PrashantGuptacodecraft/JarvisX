"""
ui/interface.py
Ultra-futuristic JARVIS GUI.
Canvas HUD with animated rings + particles, tabbed interface
(Chat | Terminal | System | Memory), live system metrics, voice waveform.
"""
import math, random, threading, datetime, time, io
import queue as q_module
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk, scrolledtext
from config.settings import JARVIS_NAME, USER_NAME, WAKE_WORD, OPERATOR_MODE

# ── Palette ────────────────────────────────────────────────────
BG0    = "#040810"   # deepest background
BG1    = "#080e1a"   # panel bg
BG2    = "#0c1424"   # card bg
BG3    = "#101c30"   # input bg
CYAN   = "#00d4ff"   # primary accent
BLUE   = "#0055ff"   # secondary
GREEN  = "#00ff88"   # success / listening
AMBER  = "#ffaa00"   # warning / thinking
RED    = "#ff2244"   # danger
PURPLE = "#9933ff"   # special
TEXT1  = "#ddeeff"   # primary text
TEXT2  = "#5577aa"   # secondary text
BORDER = "#0d2040"   # border color
GLOW   = "#00d4ff18" # glow color

STATUS_COLOR = {
    "sleeping":  "#1a3050",
    "listening": GREEN,
    "thinking":  AMBER,
    "speaking":  CYAN,
    "error":     RED,
}
STATUS_LABEL = {
    "sleeping":  "◌  STANDBY",
    "listening": "◉  LISTENING",
    "thinking":  "⟳  PROCESSING",
    "speaking":  "◆  SPEAKING",
    "error":     "⚠  ERROR",
}

FONT_MONO  = ("Courier New", 10)
FONT_MONO_LG = ("Courier New", 12)
FONT_MONO_SM = ("Courier New", 9)
FONT_TITLE = ("Courier New", 18, "bold")

BASE_WIDTH = 1100
BASE_HEIGHT = 740
MIN_WIDTH = 900
MIN_HEIGHT = 620
SIDEBAR_BASE_WIDTH = 250
HUD_BASE_SIZE = 220


# ═══════════════════════════════════════════════════════════════
class HUDCanvas(tk.Canvas):
    """
    Animated holographic HUD visualizer.
    Multiple rotating rings, particle field, pulsing center.
    """
    DEFAULT_SIZE = 220

    def __init__(self, parent, size=None, **kw):
        size = size or self.DEFAULT_SIZE
        super().__init__(parent, width=size, height=size,
                         bg=BG1, highlightthickness=0, **kw)
        self.W = self.H = size
        self.cx = self.cy = size // 2
        self.status = "sleeping"
        self._angle1 = 0.0   # outer ring
        self._angle2 = 0.0   # mid ring (counter)
        self._angle3 = 0.0   # inner ring
        self._pulse  = 0.0   # center pulse
        self._particles = self._make_particles(max(18, size // 10))
        self._running = True
        self._draw()

    def set_status(self, s: str):
        self.status = s

    def stop(self):
        self._running = False

    def resize(self, size: int):
        size = max(180, int(size))
        if size == self.W:
            return
        self.W = self.H = size
        self.cx = self.cy = size // 2
        self.configure(width=size, height=size)
        self._particles = self._make_particles(max(18, size // 10))

    # ── Particles ───────────────────────────────────────────
    def _make_particles(self, n: int) -> list:
        return [{
            "x": random.uniform(10, self.W - 10),
            "y": random.uniform(10, self.H - 10),
            "vx": random.uniform(-0.4, 0.4),
            "vy": random.uniform(-0.4, 0.4),
            "r": random.uniform(1, 2.5),
            "alpha": random.uniform(0.15, 0.55),
        } for _ in range(n)]

    def _update_particles(self):
        for p in self._particles:
            p["x"] += p["vx"]
            p["y"] += p["vy"]
            if p["x"] < 5 or p["x"] > self.W - 5: p["vx"] *= -1
            if p["y"] < 5 or p["y"] > self.H - 5: p["vy"] *= -1

    # ── Draw ────────────────────────────────────────────────
    def _draw(self):
        if not self._running:
            return

        color = STATUS_COLOR.get(self.status, CYAN)
        speed = {"sleeping": 0.4, "listening": 3.0,
                 "thinking": 6.0, "speaking": 2.0}.get(self.status, 1.0)
        self._angle1 = (self._angle1 + speed)           % 360
        self._angle2 = (self._angle2 - speed * 0.7)     % 360
        self._angle3 = (self._angle3 + speed * 1.5)     % 360
        self._pulse  = (self._pulse  + 0.07)             % (2 * math.pi)

        self.delete("all")
        cx, cy = self.cx, self.cy
        outer_r = int(self.W * 0.48)
        mid_r = int(self.W * 0.40)
        inner_r = int(self.W * 0.31)
        grid_r = int(self.W * 0.43)

        # Background gradient (concentric dark circles)
        for r, c in [
            (int(self.W * 0.48), "#06101e"),
            (int(self.W * 0.41), "#070d18"),
            (int(self.W * 0.33), "#060c16"),
        ]:
            self.create_oval(cx-r, cy-r, cx+r, cy+r, fill=c, outline="")

        # Particles
        self._update_particles()
        for p in self._particles:
            a = int(p["alpha"] * 80)
            col = self._alpha_hex(color, a)
            r = p["r"]
            self.create_oval(p["x"]-r, p["y"]-r, p["x"]+r, p["y"]+r,
                             fill=col, outline="")

        # Tick marks (outer)
        for i in range(36):
            ang = math.radians(i * 10)
            len_ = max(3, int(self.W * (0.028 if i % 3 == 0 else 0.014)))
            x1 = cx + outer_r * math.cos(ang)
            y1 = cy + outer_r * math.sin(ang)
            x2 = cx + (outer_r - len_) * math.cos(ang)
            y2 = cy + (outer_r - len_) * math.sin(ang)
            tick_c = self._alpha_hex(color, 60 if i % 3 == 0 else 30)
            self.create_line(x1, y1, x2, y2, fill=tick_c, width=1)

        # Outer ring (rotating dash arc)
        ext = 280 if self.status != "sleeping" else 120
        self._draw_arc(cx, cy, int(self.W * 0.445), self._angle1, ext, color, 2)

        # Mid ring (counter-rotating)
        ext2 = 200 if self.status == "thinking" else 100
        self._draw_arc(cx, cy, mid_r, self._angle2, ext2,
                       self._alpha_hex(color, 130), 1)

        # Inner ring
        ext3 = 160 if self.status in ("listening","speaking") else 60
        self._draw_arc(cx, cy, inner_r, self._angle3, ext3,
                       self._alpha_hex(color, 100), 1)

        # Grid lines (horizontal/vertical)
        self._draw_grid(cx, cy, color)

        # Center glow
        pulse_r = max(3, int(self.W * 0.012)) + 2 * math.sin(self._pulse)
        glow_layers = [
            (int(self.W * 0.13), 20),
            (int(self.W * 0.10), 40),
            (int(self.W * 0.08), 70),
            (int(self.W * 0.06), 120),
        ]
        for rad, alpha in glow_layers:
            c = self._alpha_hex(color, alpha)
            self.create_oval(cx-rad, cy-rad, cx+rad, cy+rad,
                             fill=c, outline="")

        # Center hex background
        self._draw_hex(cx, cy, max(12, int(self.W * 0.065)), BG0, color)

        # Center text "J"
        self.create_text(cx, cy, text="J", fill=color,
                         font=("Consolas", max(14, int(self.W * 0.065)), "bold"))

        # Status ring (thin colored border)
        pulse_extra = 2 * math.sin(self._pulse * 2)
        sr = int(self.W * 0.23) + pulse_extra
        self.create_oval(cx-sr, cy-sr, cx+sr, cy+sr,
                         outline=self._alpha_hex(color, 80), width=1)

        self.after(40, self._draw)

    def _draw_arc(self, cx, cy, r, start, extent, color, width):
        self.create_arc(cx-r, cy-r, cx+r, cy+r,
                        start=start, extent=extent,
                        outline=color, width=width, style="arc")

    def _draw_grid(self, cx, cy, color):
        lc = self._alpha_hex(color, 18)
        grid_r = int(self.W * 0.43)
        offset = int(self.W * 0.18)
        for delta in [-offset, 0, offset]:
            self.create_line(cx + delta, cy - grid_r, cx + delta, cy + grid_r,
                             fill=lc, width=1)
            self.create_line(cx - grid_r, cy + delta, cx + grid_r, cy + delta,
                             fill=lc, width=1)

    def _draw_hex(self, cx, cy, size, fill, outline):
        pts = []
        for i in range(6):
            a = math.radians(60 * i - 30)
            pts.extend([cx + size * math.cos(a), cy + size * math.sin(a)])
        self.create_polygon(pts, fill=fill, outline=outline, width=1)

    @staticmethod
    def _alpha_hex(hex_color: str, alpha: int) -> str:
        """Simulate alpha by blending hex color with bg."""
        try:
            r = int(hex_color[1:3], 16)
            g = int(hex_color[3:5], 16)
            b = int(hex_color[5:7], 16)
            br, bg_, bb = 4, 8, 16  # BG0 = "#040810"
            t = alpha / 255
            nr = int(br + (r - br) * t)
            ng = int(bg_ + (g - bg_) * t)
            nb = int(bb + (b - bb) * t)
            return f"#{nr:02x}{ng:02x}{nb:02x}"
        except Exception:
            return hex_color


# ═══════════════════════════════════════════════════════════════
class DashRingCanvas(tk.Canvas):
    """
    Large cinematic ring for the Dashboard tab.
    Three counter-rotating arcs, hex grid, animated stats text.
    """
    def __init__(self, parent, size=320, **kw):
        super().__init__(parent, width=size, height=size,
                         bg=BG0, highlightthickness=0, **kw)
        self.W = self.H = size
        self.cx = self.cy = size // 2
        self._a1 = 0.0
        self._a2 = 180.0
        self._a3 = 90.0
        self._pulse = 0.0
        self._scan = 0.0
        self._status = "sleeping"
        self._running = True
        self._particles = [{
            "x": random.uniform(0, size),
            "y": random.uniform(0, size),
            "vx": random.uniform(-0.3, 0.3),
            "vy": random.uniform(-0.3, 0.3),
            "r": random.uniform(1, 2),
        } for _ in range(40)]
        self._draw()

    def set_status(self, s):
        self._status = s

    def stop(self):
        self._running = False

    def _draw(self):
        if not self._running:
            return
        color = STATUS_COLOR.get(self._status, CYAN)
        speed = {"sleeping": 0.35, "listening": 2.5,
                 "thinking": 5.0, "speaking": 1.8}.get(self._status, 1.0)
        self._a1 = (self._a1 + speed)        % 360
        self._a2 = (self._a2 - speed * 0.6)  % 360
        self._a3 = (self._a3 + speed * 1.3)  % 360
        self._pulse = (self._pulse + 0.06)    % (2 * math.pi)
        self._scan  = (self._scan  + 1.2)     % 360
        self.delete("all")
        cx, cy = self.cx, self.cy
        W = self.W

        # deep bg
        self.create_oval(0, 0, W, W, fill="#030609", outline="")

        # particles
        for p in self._particles:
            p["x"] = (p["x"] + p["vx"]) % W
            p["y"] = (p["y"] + p["vy"]) % W
            r = p["r"]
            self.create_oval(p["x"]-r, p["y"]-r, p["x"]+r, p["y"]+r,
                             fill=self._blend(color, 35), outline="")

        # hex grid
        grid_step = int(W * 0.09)
        for gx in range(0, W, grid_step):
            for gy in range(0, W, grid_step):
                dist = math.hypot(gx - cx, gy - cy)
                if dist < W * 0.48:
                    self.create_oval(gx-1, gy-1, gx+1, gy+1,
                                     fill=self._blend(color, 12), outline="")

        # scan line sweeping
        sr = int(W * 0.46)
        sx = cx + sr * math.cos(math.radians(self._scan))
        sy = cy + sr * math.sin(math.radians(self._scan))
        self.create_line(cx, cy, sx, sy,
                         fill=self._blend(color, 30), width=1)

        # concentric bg circles
        for rad, col in [
            (int(W*0.46), "#06101e"),
            (int(W*0.38), "#070d18"),
            (int(W*0.28), "#060c16"),
        ]:
            self.create_oval(cx-rad, cy-rad, cx+rad, cy+rad,
                             fill=col, outline="")

        # tick marks
        outr = int(W * 0.455)
        for i in range(72):
            ang = math.radians(i * 5)
            long_tick = i % 9 == 0
            tlen = int(W * (0.04 if long_tick else 0.02))
            x1 = cx + outr * math.cos(ang)
            y1 = cy + outr * math.sin(ang)
            x2 = cx + (outr - tlen) * math.cos(ang)
            y2 = cy + (outr - tlen) * math.sin(ang)
            alpha = 90 if long_tick else 30
            self.create_line(x1, y1, x2, y2,
                             fill=self._blend(color, alpha), width=1)

        # arc rings
        self._arc(cx, cy, int(W*0.43), self._a1, 260, color, 3)
        self._arc(cx, cy, int(W*0.37), self._a2, 180,
                  self._blend(color, 150), 2)
        self._arc(cx, cy, int(W*0.28), self._a3, 120,
                  self._blend(color, 100), 1)

        # glow rings
        pulse_r = int(W * 0.18) + int(3 * math.sin(self._pulse))
        for rad, alpha in [(int(W*0.16), 15), (int(W*0.13), 30),
                           (int(W*0.10), 55), (int(W*0.07), 100)]:
            self.create_oval(cx-rad, cy-rad, cx+rad, cy+rad,
                             fill=self._blend(color, alpha), outline="")

        # center hex + J
        pts = []
        for i in range(6):
            a = math.radians(60*i - 30)
            s = int(W * 0.075)
            pts.extend([cx + s*math.cos(a), cy + s*math.sin(a)])
        self.create_polygon(pts, fill=BG0, outline=color, width=1)
        self.create_text(cx, cy, text="J", fill=color,
                         font=("Consolas", int(W*0.075)+2, "bold"))

        # pulsing outer ring
        pr = int(W*0.47) + int(2*math.sin(self._pulse*2))
        self.create_oval(cx-pr, cy-pr, cx+pr, cy+pr,
                         outline=self._blend(color, 50), width=1)

        self.after(35, self._draw)

    def _arc(self, cx, cy, r, start, extent, color, width):
        self.create_arc(cx-r, cy-r, cx+r, cy+r,
                        start=start, extent=extent,
                        outline=color, width=width, style="arc")

    @staticmethod
    def _blend(hex_color: str, alpha: int) -> str:
        try:
            r = int(hex_color[1:3], 16)
            g = int(hex_color[3:5], 16)
            b = int(hex_color[5:7], 16)
            t = alpha / 255
            nr = int(4  + (r-4)  * t)
            ng = int(8  + (g-8)  * t)
            nb = int(16 + (b-16) * t)
            return f"#{nr:02x}{ng:02x}{nb:02x}"
        except Exception:
            return hex_color


# ═══════════════════════════════════════════════════════════════
class WaveformBar(tk.Canvas):
    """Animated audio waveform displayed when JARVIS speaks."""
    def __init__(self, parent, **kw):
        super().__init__(parent, height=28, bg=BG1, highlightthickness=0, **kw)
        self._active = False
        self._t = 0.0
        self._draw()

    def set_active(self, active: bool):
        self._active = active

    def _draw(self):
        self.delete("all")
        w = self.winfo_width() or 300
        if self._active:
            self._t += 0.15
            bars = 30
            bar_w = w / bars
            for i in range(bars):
                h = 4 + 10 * abs(math.sin(self._t + i * 0.4))
                x = i * bar_w + bar_w / 2
                self.create_rectangle(x - 2, 14 - h, x + 2, 14 + h,
                                      fill=CYAN, outline="")
        else:
            # flat line
            self.create_line(0, 14, w, 14, fill=TEXT2, width=1)
        self.after(60, self._draw)


# ═══════════════════════════════════════════════════════════════
class MetricBar(tk.Frame):
    """Animated metric bar (CPU / RAM / Disk)."""
    def __init__(self, parent, label: str, color: str = CYAN,
                 label_font=None, value_font=None, bar_width: int = 110, **kw):
        super().__init__(parent, bg=BG1, **kw)
        self._color = color
        self._bar_width = bar_width
        self._last_pct = 0.0
        self._label = tk.Label(self, text=label, font=label_font or FONT_MONO_SM,
                               fg=TEXT2, bg=BG1, width=4, anchor="w")
        self._label.pack(side="left")
        self._canvas = tk.Canvas(self, width=self._bar_width, height=10,
                                 bg=BG2, highlightthickness=0)
        self._canvas.pack(side="left", padx=4)
        self._pct_var = tk.StringVar(value="  0%")
        self._value = tk.Label(self, textvariable=self._pct_var,
                               font=value_font or FONT_MONO_SM,
                               fg=TEXT1, bg=BG1, width=5)
        self._value.pack(side="left")

    def resize(self, bar_width: int):
        self._bar_width = max(110, int(bar_width))
        self._canvas.configure(width=self._bar_width)
        self.update_value(self._last_pct)

    def update_fonts(self, label_font=None, value_font=None):
        if label_font:
            self._label.configure(font=label_font)
        if value_font:
            self._value.configure(font=value_font)

    def update_value(self, pct: float):
        self._last_pct = pct
        self._canvas.delete("all")
        self._canvas.create_rectangle(0, 0, self._bar_width, 10, fill=BG2, outline="")
        w = int(pct / 100 * self._bar_width)
        if w > 0:
            self._canvas.create_rectangle(0, 0, w, 10, fill=self._color, outline="")
        self._pct_var.set(f"{pct:4.0f}%")


# ═══════════════════════════════════════════════════════════════
class JarvisGUI:
    """
    Ultra-futuristic JARVIS Desktop Interface.
    Tabs: CHAT | TERMINAL | SYSTEM | MEMORY
    """

    def __init__(self, command_queue, listener=None, speaker=None):
        self.command_queue = command_queue
        self.listener      = listener
        self.speaker       = speaker
        self.status        = "sleeping"
        self._running      = True
        self._term_lines   = []
        self._sys_update_running = False
        self._is_fullscreen = False
        self._resize_job = None
        self._font_scale = 1.0

        self.root = tk.Tk()
        self.root.title(f"J.A.R.V.I.S — Advanced AI System")
        self.root.geometry(f"{BASE_WIDTH}x{BASE_HEIGHT}")
        self.root.minsize(MIN_WIDTH, MIN_HEIGHT)
        self.root.configure(bg=BG0)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._init_fonts()
        self._center_window()
        self._apply_style()
        self._build_ui()
        self.root.bind("<F11>", self._toggle_fullscreen)
        self.root.bind("<Escape>", self._exit_fullscreen)
        self.root.bind("<Configure>", self._handle_resize)
        self.root.after(80, self._apply_responsive_scale)
        self._start_clock()
        self._start_sys_monitor()

    # ── Setup ────────────────────────────────────────────────
    def _init_fonts(self):
        self._font_specs = {}
        self._fonts = {}

        def make(name, size, weight="normal", slant="roman"):
            self._font_specs[name] = {
                "family": "Consolas",
                "size": size,
                "weight": weight,
                "slant": slant,
            }
            self._fonts[name] = tkfont.Font(
                family="Consolas",
                size=size,
                weight=weight,
                slant=slant,
            )

        make("body_sm", 10)
        make("body", 11)
        make("body_lg", 13)
        make("title", 24, "bold")
        make("subtitle", 10)
        make("status", 11, "bold")
        make("clock", 16)
        make("button", 10, "bold")
        make("section", 10, "bold")
        make("tab", 10, "bold")
        make("input", 14)
        make("chat_user", 13, "bold")
        make("chat_jarvis", 13)
        make("chat_system", 10, slant="italic")
        make("chat_time", 10)
        make("plan", 11)
        make("mono_lg", 12)
        make("mono_popup", 12, "bold")

    def _center_window(self):
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        w, h = BASE_WIDTH, BASE_HEIGHT
        self.root.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

    def _apply_style(self):
        self._style = ttk.Style()
        self._style.theme_use("clam")
        self._style.configure(".", background=BG0, foreground=TEXT1,
                              font=self._fonts["body"], borderwidth=0)
        self._style.configure("Jarvis.TNotebook", background=BG1, borderwidth=0,
                              tabmargins=[0, 0, 0, 0])
        self._style.configure("Jarvis.TNotebook.Tab", background=BG2, foreground=TEXT2,
                              font=self._fonts["tab"], padding=[18, 8],
                              borderwidth=0, relief="flat")
        self._style.map("Jarvis.TNotebook.Tab",
                        background=[("selected", BG1)],
                        foreground=[("selected", CYAN)])
        self._style.configure("TSeparator", background=BORDER)

    def _handle_resize(self, event=None):
        if event and event.widget is not self.root:
            return
        if self._resize_job:
            self.root.after_cancel(self._resize_job)
        self._resize_job = self.root.after(80, self._apply_responsive_scale)

    def _apply_responsive_scale(self):
        self._resize_job = None
        width = max(self.root.winfo_width(), BASE_WIDTH)
        height = max(self.root.winfo_height(), BASE_HEIGHT)
        scale = min(1.9, max(1.0, min(width / BASE_WIDTH, height / BASE_HEIGHT)))
        if self._is_fullscreen:
            scale = max(scale, 1.45)
        if abs(scale - self._font_scale) < 0.03:
            self._refresh_display_state()
            return

        self._font_scale = scale
        for name, spec in self._font_specs.items():
            self._fonts[name].configure(
                size=max(spec["size"], round(spec["size"] * scale)),
                weight=spec["weight"],
                slant=spec["slant"],
            )

        self._style.configure(
            "Jarvis.TNotebook.Tab",
            font=self._fonts["tab"],
            padding=[int(18 * scale), int(8 * scale)],
        )

        if hasattr(self, "_header_frame"):
            self._header_frame.configure(height=max(68, int(74 * scale)))
        if hasattr(self, "_sidebar"):
            self._sidebar.configure(width=max(SIDEBAR_BASE_WIDTH, int(SIDEBAR_BASE_WIDTH * scale)))
        if hasattr(self, "_hud"):
            self._hud.resize(max(HUD_BASE_SIZE, int(HUD_BASE_SIZE * scale)))
        if hasattr(self, "_cpu_bar"):
            metric_width = max(110, int(120 * scale))
            for bar in (self._cpu_bar, self._ram_bar, self._disk_bar):
                bar.resize(metric_width)
                bar.update_fonts(self._fonts["body_sm"], self._fonts["body_sm"])
        if hasattr(self, "_wake_hint"):
            self._wake_hint.configure(wraplength=max(220, int(self._sidebar.winfo_width() - 36)))
        if hasattr(self, "_voice_hint_label"):
            self._voice_hint_label.configure(wraplength=max(420, width - 420))
        if hasattr(self, "_chat_text"):
            pad_x = int(16 * scale)
            pad_y = int(12 * scale)
            self._chat_text.configure(padx=pad_x, pady=pad_y, spacing3=max(6, int(8 * scale)))
            self._term_text.configure(padx=pad_x, pady=max(10, int(10 * scale)))
            self._sys_text.configure(padx=pad_x, pady=max(10, int(10 * scale)))
            self._mem_text.configure(padx=pad_x, pady=max(10, int(10 * scale)))

        self._refresh_display_state()

    def _refresh_display_state(self):
        if hasattr(self, "_display_hint_var"):
            self._display_hint_var.set("WINDOWED [ESC]" if self._is_fullscreen else "FULLSCREEN [F11]")
        if hasattr(self, "_display_mode_var"):
            if self._is_fullscreen:
                self._display_mode_var.set("IMMERSIVE HUD")
            elif self._font_scale >= 1.2:
                self._display_mode_var.set("EXPANDED CONSOLE")
            else:
                self._display_mode_var.set("ADAPTIVE CONSOLE")

    def _toggle_fullscreen(self, event=None):
        self._is_fullscreen = not self._is_fullscreen
        self.root.attributes("-fullscreen", self._is_fullscreen)
        self._apply_responsive_scale()
        return "break"

    def _exit_fullscreen(self, event=None):
        if self._is_fullscreen:
            self._is_fullscreen = False
            self.root.attributes("-fullscreen", False)
            self._apply_responsive_scale()
        return "break"

    # ── Main UI ─────────────────────────────────────────────
    def _build_ui(self):
        # ── Header ──
        self._build_header()
        tk.Frame(self.root, bg=CYAN, height=1).pack(fill="x")
        tk.Frame(self.root, bg="#092845", height=1).pack(fill="x")

        # ── Body ──
        body = tk.Frame(self.root, bg=BG0)
        body.pack(fill="both", expand=True, padx=10, pady=10)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        self._build_sidebar(body)
        self._build_main_panel(body)

    # ── Header ──────────────────────────────────────────────
    def _build_header(self):
        hdr = tk.Frame(self.root, bg=BG1, height=74)
        self._header_frame = hdr
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        # Left: Logo
        logo_f = tk.Frame(hdr, bg=BG1)
        logo_f.pack(side="left", padx=16)
        tk.Label(logo_f, text="⬡", font=self._fonts["title"],
                 fg=CYAN, bg=BG1).pack(side="left")
        tk.Label(logo_f, text=" J.A.R.V.I.S", font=self._fonts["title"],
                 fg=CYAN, bg=BG1).pack(side="left")
        tk.Label(logo_f, text="  /  ADVANCED AI SYSTEM",
                 font=self._fonts["subtitle"], fg=TEXT2, bg=BG1).pack(side="left")

        # Right: clock + status
        right_f = tk.Frame(hdr, bg=BG1)
        right_f.pack(side="right", padx=16)

        self._display_hint_var = tk.StringVar(value="FULLSCREEN [F11]")
        self._fullscreen_btn = tk.Button(
            right_f,
            textvariable=self._display_hint_var,
            bg=BG2,
            fg=TEXT1,
            activebackground=CYAN,
            activeforeground=BG0,
            relief="flat",
            cursor="hand2",
            borderwidth=0,
            font=self._fonts["button"],
            padx=12,
            pady=6,
            command=self._toggle_fullscreen,
        )
        self._fullscreen_btn.pack(side="right")

        self._status_var = tk.StringVar(value=STATUS_LABEL["sleeping"])
        self._status_lbl = tk.Label(right_f, textvariable=self._status_var,
                                    font=self._fonts["status"],
                                    fg=STATUS_COLOR["sleeping"], bg=BG1)
        self._status_lbl.pack(side="right", padx=(16, 0))

        self._clock_var = tk.StringVar()
        self._clock_lbl = tk.Label(right_f, textvariable=self._clock_var,
                                   font=self._fonts["clock"], fg=TEXT2, bg=BG1)
        self._clock_lbl.pack(side="right", padx=(0, 12))

    # ── Sidebar ─────────────────────────────────────────────
    def _build_sidebar(self, parent):
        side = tk.Frame(parent, bg=BG1, width=SIDEBAR_BASE_WIDTH,
                        highlightthickness=1, highlightbackground=BORDER)
        self._sidebar = side
        side.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        side.grid_propagate(False)
        side.columnconfigure(0, weight=1)

        tk.Label(side, text="TACTICAL OVERVIEW",
                 font=self._fonts["section"], fg=CYAN, bg=BG1).pack(anchor="w", padx=14, pady=(12, 4))

        # HUD Canvas
        self._hud = HUDCanvas(side, size=HUD_BASE_SIZE)
        self._hud.pack(pady=(12, 4), padx=10)

        # Waveform
        self._wave = WaveformBar(side)
        self._wave.pack(fill="x", padx=10, pady=(0, 8))

        # Status text under HUD
        self._mode_var = tk.StringVar(value="STANDBY MODE")
        tk.Label(side, textvariable=self._mode_var,
                 font=self._fonts["body_sm"], fg=TEXT2, bg=BG1).pack()

        # Separator
        tk.Frame(side, bg=BORDER, height=1).pack(fill="x", padx=10, pady=8)

        # System metrics
        tk.Label(side, text="SYSTEM METRICS",
                 font=self._fonts["section"], fg=TEXT2, bg=BG1).pack(anchor="w", padx=12)

        metrics_f = tk.Frame(side, bg=BG1)
        metrics_f.pack(fill="x", padx=10, pady=4)
        self._cpu_bar  = MetricBar(metrics_f, "CPU", CYAN,
                                   label_font=self._fonts["body_sm"],
                                   value_font=self._fonts["body_sm"],
                                   bar_width=120)
        self._cpu_bar.pack(fill="x", pady=2)
        self._ram_bar  = MetricBar(metrics_f, "RAM", GREEN,
                                   label_font=self._fonts["body_sm"],
                                   value_font=self._fonts["body_sm"],
                                   bar_width=120)
        self._ram_bar.pack(fill="x", pady=2)
        self._disk_bar = MetricBar(metrics_f, "DSK", AMBER,
                                   label_font=self._fonts["body_sm"],
                                   value_font=self._fonts["body_sm"],
                                   bar_width=120)
        self._disk_bar.pack(fill="x", pady=2)

        # Separator
        tk.Frame(side, bg=BORDER, height=1).pack(fill="x", padx=10, pady=8)

        # Control buttons
        self._build_sidebar_buttons(side)

        # Wake word hint
        tk.Frame(side, bg=BORDER, height=1).pack(fill="x", padx=10, pady=8)
        self._wake_hint = tk.Label(side, text=f'Wake: "{WAKE_WORD.title()}"',
                                   font=self._fonts["body_sm"], fg=TEXT2, bg=BG1,
                                   wraplength=220, justify="left")
        self._wake_hint.pack(pady=2, padx=12, anchor="w")

    def _build_sidebar_buttons(self, parent):
        btn_cfg = dict(
            font=self._fonts["button"], relief="flat",
            cursor="hand2", pady=6, borderwidth=0
        )
        def btn(p, text, bg, fg, cmd):
            b = tk.Button(p, text=text, bg=bg, fg=fg,
                          activebackground=CYAN, activeforeground=BG0,
                          command=cmd, **btn_cfg)
            b.pack(fill="x", padx=10, pady=2)
            return b

        btn(parent, "⊙  ACTIVATE",  BLUE, TEXT1, self._activate)
        btn(parent, "◌  SLEEP",     BG2,  TEXT2, self._sleep)
        btn(parent, "📷  CAMERA",   PURPLE, TEXT1, self._open_camera_tab)
        self._gesture_btn = btn(parent, "🖐  GESTURE CTRL", BG2, TEXT2, self._toggle_gesture_control)
        btn(parent, "✕  CLEAR CHAT", BG2, TEXT2, self._clear_chat)
        btn(parent, "⚙  WORKSPACE", BG2,  TEXT2, self._open_workspace)

        # Quick actions
        tk.Frame(parent, bg=BORDER, height=1).pack(fill="x", padx=10, pady=6)
        tk.Label(parent, text="QUICK COMMANDS",
                 font=self._fonts["section"], fg=TEXT2, bg=BG1).pack(anchor="w", padx=12)
        quick = [
            ("⏰ Time", "what time is it"),
            ("🔋 Battery", "battery status"),
            ("📸 Screenshot", "take a screenshot"),
            ("💻 System Info", "cpu usage and ram usage"),
            ("🌐 Google", "open google"),
            ("📂 Downloads", "open downloads folder"),
            ("👁 Look at me", "look at me and describe what you see"),
        ]
        for label, cmd in quick:
            tk.Button(parent, text=label, bg=BG2, fg=TEXT1,
                      activebackground=BLUE, activeforeground=TEXT1,
                      relief="flat", cursor="hand2", pady=4,
                      font=self._fonts["body_sm"], borderwidth=0,
                      command=lambda c=cmd: self._quick_cmd(c)
                     ).pack(fill="x", padx=10, pady=1)

    # ── Main panel ──────────────────────────────────────────
    def _build_main_panel(self, parent):
        main = tk.Frame(parent, bg=BG0)
        main.grid(row=0, column=1, sticky="nsew")
        main.columnconfigure(0, weight=1)
        main.rowconfigure(1, weight=1)

        self._build_signal_rail(main)

        deck = tk.Frame(main, bg=BORDER, padx=1, pady=1)
        deck.grid(row=1, column=0, sticky="nsew")
        deck.columnconfigure(0, weight=1)
        deck.rowconfigure(0, weight=1)

        console = tk.Frame(deck, bg=BG1)
        console.grid(row=0, column=0, sticky="nsew")
        console.columnconfigure(0, weight=1)
        console.rowconfigure(0, weight=1)

        # Notebook tabs
        self._nb = ttk.Notebook(console, style="Jarvis.TNotebook")
        self._nb.grid(row=0, column=0, sticky="nsew")

        for _tab_builder, _tab_name in [
            (self._build_dashboard_tab, "DASHBOARD"),
            (self._build_chat_tab,     "CHAT"),
            (self._build_terminal_tab, "TERMINAL"),
            (self._build_system_tab,   "SYSTEM"),
            (self._build_memory_tab,   "MEMORY"),
            (self._build_camera_tab,   "CAMERA"),
        ]:
            try:
                _tab_builder()
            except Exception as _e:
                import traceback
                traceback.print_exc()
                import tkinter as _tk
                _err_f = _tk.Frame(self._nb, bg="#0a0014")
                self._nb.add(_err_f, text=f"  {_tab_name}  ")
                _tk.Label(_err_f, text=f"{_tab_name} tab error:\n{_e}",
                          fg="#ff4444", bg="#0a0014").pack(pady=40)

        # Input bar
        self._build_input_bar(console)

    def _build_signal_rail(self, parent):
        rail = tk.Frame(parent, bg=BG0)
        rail.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        for col in range(4):
            rail.columnconfigure(col, weight=1)

        self._display_mode_var = tk.StringVar(value="ADAPTIVE CONSOLE")
        self._operator_state_var = tk.StringVar(value="OPERATOR MODE" if OPERATOR_MODE else "SAFE MODE")
        self._command_state_var = tk.StringVar(value="STANDBY MODE")
        self._wake_word_var = tk.StringVar(value=WAKE_WORD.upper())

        cards = [
            ("DISPLAY", self._display_mode_var, CYAN),
            ("CONTROL", self._operator_state_var, BLUE),
            ("STATUS", self._command_state_var, GREEN),
            ("WAKE WORD", self._wake_word_var, AMBER),
        ]
        for col, (label, value_var, accent) in enumerate(cards):
            self._make_signal_card(rail, col, label, value_var, accent)

    def _make_signal_card(self, parent, column, label, value_var, accent):
        card = tk.Frame(parent, bg=BG1, highlightthickness=1, highlightbackground=BORDER)
        card.grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 4, 0))
        tk.Frame(card, bg=accent, height=2).pack(fill="x")
        inner = tk.Frame(card, bg=BG1)
        inner.pack(fill="both", expand=True, padx=12, pady=10)
        tk.Label(inner, text=label, font=self._fonts["section"], fg=TEXT2, bg=BG1).pack(anchor="w")
        tk.Label(inner, textvariable=value_var, font=self._fonts["body_lg"], fg=TEXT1, bg=BG1).pack(anchor="w")

    # ── Dashboard tab ────────────────────────────────────────
    def _build_dashboard_tab(self):
        f = tk.Frame(self._nb, bg=BG0)
        self._nb.add(f, text="  ⬡ DASHBOARD  ")
        f.columnconfigure(0, weight=1)
        f.columnconfigure(1, weight=1)
        f.rowconfigure(1, weight=1)

        # ── Mission banner ───────────────────────────────────
        banner = tk.Frame(f, bg="#050d1a", height=52)
        banner.grid(row=0, column=0, columnspan=2, sticky="ew")
        banner.grid_propagate(False)
        tk.Frame(banner, bg=CYAN, height=2).pack(fill="x", side="top")
        inner_b = tk.Frame(banner, bg="#050d1a")
        inner_b.pack(fill="both", expand=True, padx=18, pady=6)

        # animated mission text
        self._dash_mission_var = tk.StringVar(
            value=f"  ◈  J.A.R.V.I.S  ADVANCED AI SYSTEM  ◈  OPERATOR: {USER_NAME.upper()}  ◈  ALL SYSTEMS NOMINAL")
        self._dash_mission_offset = [0]
        mission_lbl = tk.Label(inner_b, textvariable=self._dash_mission_var,
                               font=("Consolas", 10, "bold"),
                               fg=CYAN, bg="#050d1a", anchor="w")
        mission_lbl.pack(side="left", fill="x", expand=True)

        mode_badge = tk.Label(inner_b,
            text=" OPERATOR MODE " if OPERATOR_MODE else " SAFE MODE ",
            font=("Consolas", 9, "bold"),
            fg=BG0, bg=GREEN if OPERATOR_MODE else AMBER, padx=4)
        mode_badge.pack(side="right", padx=(8, 0))

        # ── Left column: ring + live stats ──────────────────
        left = tk.Frame(f, bg=BG0)
        left.grid(row=1, column=0, sticky="nsew", padx=(12, 6), pady=10)
        left.columnconfigure(0, weight=1)

        # big ring
        self._dash_ring = DashRingCanvas(left, size=290)
        self._dash_ring.pack(pady=(8, 4))

        # live clock under ring
        self._dash_clock_var = tk.StringVar(value="")
        tk.Label(left, textvariable=self._dash_clock_var,
                 font=("Consolas", 22, "bold"),
                 fg=CYAN, bg=BG0).pack()
        self._dash_date_var = tk.StringVar(value="")
        tk.Label(left, textvariable=self._dash_date_var,
                 font=("Consolas", 10),
                 fg=TEXT2, bg=BG0).pack(pady=(0, 8))

        # uptime + session
        info_f = tk.Frame(left, bg=BG0)
        info_f.pack(fill="x", padx=10)
        self._dash_uptime_var  = tk.StringVar(value="UPTIME:  00:00:00")
        self._dash_session_var = tk.StringVar(value="SESSION: ACTIVE")
        for var, col in [(self._dash_uptime_var, TEXT2),
                         (self._dash_session_var, GREEN)]:
            tk.Label(info_f, textvariable=var,
                     font=("Consolas", 9), fg=col, bg=BG0,
                     anchor="w").pack(fill="x")

        # ── Right column: stat cards + quick actions ─────────
        right = tk.Frame(f, bg=BG0)
        right.grid(row=1, column=1, sticky="nsew", padx=(6, 12), pady=10)
        right.columnconfigure(0, weight=1)
        right.columnconfigure(1, weight=1)

        # stat card grid 2×2
        stat_grid = tk.Frame(right, bg=BG0)
        stat_grid.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        stat_grid.columnconfigure(0, weight=1)
        stat_grid.columnconfigure(1, weight=1)

        self._dash_cpu_var  = tk.StringVar(value="--")
        self._dash_ram_var  = tk.StringVar(value="--")
        self._dash_net_var  = tk.StringVar(value="ONLINE")
        self._dash_ai_var   = tk.StringVar(value="GROQ")

        cards_def = [
            ("CPU",     self._dash_cpu_var,  CYAN,   "◈", 0, 0),
            ("RAM",     self._dash_ram_var,  GREEN,  "◉", 0, 1),
            ("NETWORK", self._dash_net_var,  BLUE,   "◆", 1, 0),
            ("AI CORE", self._dash_ai_var,   PURPLE, "⬡", 1, 1),
        ]
        for label, var, accent, icon, row_, col_ in cards_def:
            self._make_dash_card(stat_grid, row_, col_, label, var, accent, icon)

        # divider
        tk.Frame(right, bg=BORDER, height=1).grid(
            row=1, column=0, columnspan=2, sticky="ew", pady=6)

        # quick action label
        tk.Label(right, text="  QUICK ACTIONS",
                 font=("Consolas", 9, "bold"), fg=TEXT2, bg=BG0,
                 anchor="w").grid(row=2, column=0, columnspan=2, sticky="w")

        # 3×2 quick-action buttons
        actions = [
            ("⏰ TIME",      "what time is it",           CYAN),
            ("💻 SYSTEM",   "cpu usage and ram usage",   GREEN),
            ("🌐 BROWSER",  "open google",               BLUE),
            ("📸 SCREENSHOT","take a screenshot",         AMBER),
            ("📂 FILES",    "open downloads folder",     PURPLE),
            ("👁 VISION",   "look at me and describe what you see", RED),
        ]
        qa_frame = tk.Frame(right, bg=BG0)
        qa_frame.grid(row=3, column=0, columnspan=2, sticky="ew", pady=4)
        for idx, (label, cmd, accent) in enumerate(actions):
            r_, c_ = divmod(idx, 3)
            btn = tk.Button(
                qa_frame, text=label,
                bg=BG1, fg=TEXT1,
                activebackground=accent, activeforeground=BG0,
                font=("Consolas", 8, "bold"),
                relief="flat", cursor="hand2",
                padx=6, pady=8, borderwidth=0,
                command=lambda c=cmd: self._quick_cmd(c)
            )
            btn.grid(row=r_, column=c_, padx=2, pady=2, sticky="ew")
            qa_frame.columnconfigure(c_, weight=1)
            # hover glow
            btn.bind("<Enter>",
                     lambda e, b=btn, a=accent: b.configure(bg=a, fg=BG0))
            btn.bind("<Leave>",
                     lambda e, b=btn: b.configure(bg=BG1, fg=TEXT1))

        # status strip at bottom
        tk.Frame(right, bg=BORDER, height=1).grid(
            row=4, column=0, columnspan=2, sticky="ew", pady=6)
        strip = tk.Frame(right, bg=BG0)
        strip.grid(row=5, column=0, columnspan=2, sticky="ew")
        dots = [
            ("●", GREEN,  "VOICE ACTIVE"),
            ("●", CYAN,   "AI PROVIDER"),
            ("●", BLUE,   "MEMORY DB"),
            ("●", PURPLE, "GESTURE"),
        ]
        for dot, col, tip in dots:
            frm = tk.Frame(strip, bg=BG0)
            frm.pack(side="left", padx=6)
            tk.Label(frm, text=dot, fg=col, bg=BG0,
                     font=("Consolas", 8)).pack(side="left")
            tk.Label(frm, text=tip, fg=TEXT2, bg=BG0,
                     font=("Consolas", 7)).pack(side="left")

        # start dashboard updater
        self._dash_start_time = time.time()
        self._dash_update()

    def _make_dash_card(self, parent, row, col, label, var, accent, icon):
        card = tk.Frame(parent, bg=BG1, highlightthickness=1,
                        highlightbackground=BORDER)
        card.grid(row=row, column=col, padx=3, pady=3, sticky="nsew")
        tk.Frame(card, bg=accent, height=3).pack(fill="x")
        inner = tk.Frame(card, bg=BG1)
        inner.pack(fill="both", padx=10, pady=8)
        tk.Label(inner, text=f"{icon}  {label}",
                 font=("Consolas", 8, "bold"),
                 fg=TEXT2, bg=BG1, anchor="w").pack(fill="x")
        tk.Label(inner, textvariable=var,
                 font=("Consolas", 18, "bold"),
                 fg=accent, bg=BG1, anchor="w").pack(fill="x")

    def _dash_update(self):
        """Update dashboard live values every second."""
        if not self._running:
            return
        # clock
        now = datetime.datetime.now()
        self._dash_clock_var.set(now.strftime("%H:%M:%S"))
        self._dash_date_var.set(now.strftime("%A, %d %B %Y"))
        # uptime
        elapsed = int(time.time() - self._dash_start_time)
        h, rem = divmod(elapsed, 3600)
        m, s   = divmod(rem, 60)
        self._dash_uptime_var.set(f"UPTIME:  {h:02d}:{m:02d}:{s:02d}")
        # cpu / ram
        try:
            import psutil
            self._dash_cpu_var.set(f"{psutil.cpu_percent(interval=None):.0f}%")
            self._dash_ram_var.set(f"{psutil.virtual_memory().percent:.0f}%")
        except Exception:
            pass
        # scrolling mission text
        raw = f"  ◈  J.A.R.V.I.S  ADVANCED AI SYSTEM  ◈  OPERATOR: {USER_NAME.upper()}  ◈  ALL SYSTEMS NOMINAL  ◈  {now.strftime('%H:%M:%S')}"
        off = self._dash_mission_offset[0]
        display = raw[off:] + "   " + raw[:off]
        self._dash_mission_var.set(display[:80])
        self._dash_mission_offset[0] = (off + 1) % len(raw)
        self.root.after(100, self._dash_update)

    # ── Chat tab ────────────────────────────────────────────
    def _build_chat_tab(self):
        f = tk.Frame(self._nb, bg=BG1)
        self._nb.add(f, text="  CHAT  ")
        f.columnconfigure(0, weight=1)
        f.rowconfigure(0, weight=1)

        self._chat_text = tk.Text(
            f, bg=BG1, fg=TEXT1, insertbackground=CYAN,
            font=self._fonts["body_lg"], relief="flat", padx=14, pady=10,
            wrap="word", state="disabled", spacing3=6,
            selectbackground=BLUE, selectforeground=TEXT1
        )
        sb = tk.Scrollbar(f, command=self._chat_text.yview, bg=BG0,
                          troughcolor=BG2, activebackground=CYAN)
        self._chat_text.configure(yscrollcommand=sb.set)
        self._chat_text.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")

        self._chat_text.tag_configure("user",
            foreground=BLUE, font=self._fonts["chat_user"])
        self._chat_text.tag_configure("jarvis",
            foreground=CYAN, font=self._fonts["chat_jarvis"])
        self._chat_text.tag_configure("system",
            foreground=TEXT2, font=self._fonts["chat_system"])
        self._chat_text.tag_configure("time",
            foreground="#1a2a3a", font=self._fonts["chat_time"])
        self._chat_text.tag_configure("plan",
            foreground=AMBER, font=self._fonts["plan"])

        self._chat_append_system(f"System online. Say '{WAKE_WORD.title()}' or press F11 for immersive view.")

    # ── Terminal tab ─────────────────────────────────────────
    def _build_terminal_tab(self):
        f = tk.Frame(self._nb, bg=BG0)
        self._nb.add(f, text="  TERMINAL  ")
        f.columnconfigure(0, weight=1)
        f.rowconfigure(0, weight=1)

        # Output area
        self._term_text = tk.Text(
            f, bg="#020408", fg="#00ff66", insertbackground=GREEN,
            font=self._fonts["mono_lg"], relief="flat", padx=12, pady=8,
            wrap="word", state="disabled",
            selectbackground="#003320", selectforeground="#00ff66"
        )
        tsb = tk.Scrollbar(f, command=self._term_text.yview,
                           bg=BG0, troughcolor=BG2)
        self._term_text.configure(yscrollcommand=tsb.set)
        self._term_text.grid(row=0, column=0, sticky="nsew")
        tsb.grid(row=0, column=1, sticky="ns")

        self._term_text.tag_configure("cmd",  foreground=GREEN)
        self._term_text.tag_configure("out",  foreground="#88ffaa")
        self._term_text.tag_configure("err",  foreground=RED)
        self._term_text.tag_configure("info", foreground=CYAN)
        self._term_text.tag_configure("plan", foreground=AMBER)

        # Terminal input row
        term_in = tk.Frame(f, bg="#030608")
        term_in.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(2, 0))
        term_in.columnconfigure(1, weight=1)

        tk.Label(term_in, text="JARVIS $", font=self._fonts["button"],
                 fg=GREEN, bg="#030608").grid(row=0, column=0, padx=8)

        self._term_input_var = tk.StringVar()
        self._term_entry = tk.Entry(
            term_in, textvariable=self._term_input_var,
            bg="#030608", fg=GREEN, insertbackground=GREEN,
            font=self._fonts["mono_lg"], relief="flat", highlightthickness=0
        )
        self._term_entry.grid(row=0, column=1, sticky="ew", pady=6)
        self._term_entry.bind("<Return>", self._on_term_submit)

        self._term_log("JARVIS Terminal — type commands or ask JARVIS to run them via voice", "info")
        self._term_log("─" * 55, "info")

    # ── System tab ────────────────────────────────────────────
    def _build_system_tab(self):
        f = tk.Frame(self._nb, bg=BG1)
        self._nb.add(f, text="  SYSTEM  ")
        f.columnconfigure(0, weight=1)
        f.rowconfigure(0, weight=1)

        self._sys_text = tk.Text(
            f, bg=BG1, fg=TEXT1, insertbackground=CYAN,
            font=self._fonts["body"], relief="flat", padx=12, pady=8,
            wrap="word", state="disabled"
        )
        self._sys_text.grid(row=0, column=0, sticky="nsew")
        self._sys_text.tag_configure("header", foreground=CYAN,
                                     font=self._fonts["section"])
        self._sys_text.tag_configure("val",    foreground=TEXT1)
        self._sys_text.tag_configure("warn",   foreground=AMBER)
        self._sys_text.tag_configure("good",   foreground=GREEN)

        tk.Button(f, text="↻  REFRESH", bg=BLUE, fg=TEXT1, relief="flat",
                  font=self._fonts["button"], cursor="hand2",
                  command=self._refresh_system_tab
                 ).grid(row=1, column=0, pady=4)
        self._refresh_system_tab()

    def _refresh_system_tab(self):
        try:
            import psutil, platform
            self._sys_text.configure(state="normal")
            self._sys_text.delete("1.0", "end")

            def row(label, val, tag="val"):
                self._sys_text.insert("end", f"  {label:<22}", "header")
                self._sys_text.insert("end", f"{val}\n", tag)

            self._sys_text.insert("end", "── MACHINE ─────────────────────────────────\n", "header")
            row("Hostname",     platform.node())
            row("OS",           f"{platform.system()} {platform.release()}")
            row("Python",       platform.python_version())

            self._sys_text.insert("end", "\n── PERFORMANCE ──────────────────────────────\n", "header")
            cpu = psutil.cpu_percent(interval=0.3)
            ram = psutil.virtual_memory()
            disk = psutil.disk_usage("/")
            tag_c = "warn" if cpu > 80 else "good" if cpu < 40 else "val"
            tag_r = "warn" if ram.percent > 85 else "good" if ram.percent < 50 else "val"
            row("CPU Usage",    f"{cpu:.1f}%", tag_c)
            row("CPU Cores",    f"{psutil.cpu_count(logical=True)} logical")
            row("RAM Usage",    f"{ram.percent:.1f}%  ({ram.used/1e9:.1f}/{ram.total/1e9:.1f} GB)", tag_r)
            row("Disk Usage",   f"{disk.percent:.1f}%  ({disk.used/1e9:.0f}/{disk.total/1e9:.0f} GB)")

            self._sys_text.insert("end", "\n── NETWORK ──────────────────────────────────\n", "header")
            for iface, stats in psutil.net_if_stats().items():
                if stats.isup and iface.lower() not in ("lo", "loopback"):
                    addrs = psutil.net_if_addrs().get(iface, [])
                    ip = next((a.address for a in addrs if a.family == 2), "N/A")
                    row(f"Interface [{iface}]", ip, "good")

            self._sys_text.insert("end", "\n── TOP PROCESSES ────────────────────────────\n", "header")
            procs = sorted(psutil.process_iter(['name', 'cpu_percent', 'memory_percent']),
                           key=lambda p: p.info.get('cpu_percent', 0), reverse=True)
            for p in procs[:8]:
                name = p.info.get('name', '?')[:20]
                cpu_p = p.info.get('cpu_percent', 0)
                mem_p = p.info.get('memory_percent', 0)
                row(name, f"CPU:{cpu_p:.1f}%  MEM:{mem_p:.1f}%")

            now = datetime.datetime.now().strftime("%H:%M:%S")
            self._sys_text.insert("end", f"\n  Updated: {now}\n", "header")
            self._sys_text.configure(state="disabled")
        except Exception as e:
            self._sys_text.configure(state="normal")
            self._sys_text.insert("end", f"System info error: {e}\n")
            self._sys_text.configure(state="disabled")

    # ── Memory tab ────────────────────────────────────────────
    def _build_memory_tab(self):
        f = tk.Frame(self._nb, bg=BG1)
        self._nb.add(f, text="  MEMORY  ")
        f.columnconfigure(0, weight=1)
        f.rowconfigure(0, weight=1)

        self._mem_text = tk.Text(
            f, bg=BG1, fg=TEXT1, insertbackground=CYAN,
            font=self._fonts["body"], relief="flat", padx=12, pady=8,
            wrap="word", state="disabled"
        )
        self._mem_text.grid(row=0, column=0, sticky="nsew")
        self._mem_text.tag_configure("header", foreground=CYAN,
                                     font=self._fonts["section"])
        self._mem_text.tag_configure("item",   foreground=TEXT1)
        self._mem_text.tag_configure("meta",   foreground=TEXT2,
                                     font=self._fonts["body_sm"])

        tk.Button(f, text="↻  REFRESH MEMORY", bg=BLUE, fg=TEXT1,
                  relief="flat", font=self._fonts["button"], cursor="hand2",
                  command=self.refresh_memory_tab
                 ).grid(row=1, column=0, pady=4)

    def refresh_memory_tab(self, memory=None):
        """Refresh the memory tab. Call with memory manager or without."""
        self._mem_text.configure(state="normal")
        self._mem_text.delete("1.0", "end")
        if memory:
            self._memory_ref = memory

        mem = getattr(self, "_memory_ref", None)
        if not mem:
            self._mem_text.insert("end", "  Memory manager not connected yet.\n", "meta")
            self._mem_text.configure(state="disabled")
            return

        try:
            facts = mem.get_all_facts()
            todos = mem.get_todos()
            notes = mem.get_notes()
            reminders = mem.get_pending_reminders()

            self._mem_text.insert("end", "── STORED FACTS ─────────────────────────────\n", "header")
            if facts:
                for f_item in facts[:15]:
                    self._mem_text.insert("end", f"  • {f_item['value']}\n", "item")
                    self._mem_text.insert("end", f"    {f_item['created'][:16]}\n", "meta")
            else:
                self._mem_text.insert("end", "  (none)\n", "meta")

            self._mem_text.insert("end", "\n── TO-DO LIST ───────────────────────────────\n", "header")
            if todos:
                for t in todos:
                    self._mem_text.insert("end", f"  ☐ {t['item']}\n", "item")
            else:
                self._mem_text.insert("end", "  (empty)\n", "meta")

            self._mem_text.insert("end", "\n── NOTES ────────────────────────────────────\n", "header")
            if notes:
                for n in notes[:10]:
                    self._mem_text.insert("end", f"  ◈ {n['content']}\n", "item")
                    self._mem_text.insert("end", f"    {n['created'][:16]}\n", "meta")
            else:
                self._mem_text.insert("end", "  (none)\n", "meta")

            self._mem_text.insert("end", "\n── REMINDERS ────────────────────────────────\n", "header")
            if reminders:
                for r in reminders:
                    self._mem_text.insert("end", f"  ⏰ {r['task']}  @  {r['time']}\n", "item")
            else:
                self._mem_text.insert("end", "  (none pending)\n", "meta")

        except Exception as e:
            self._mem_text.insert("end", f"Memory read error: {e}\n")

        self._mem_text.configure(state="disabled")

    # ── Camera tab ───────────────────────────────────────────
    def _build_camera_tab(self):
        """Live webcam feed with AI vision query."""
        f = tk.Frame(self._nb, bg=BG0)
        self._nb.add(f, text="  CAMERA  ")
        self._camera_frame_ref = f
        f.columnconfigure(0, weight=1)
        f.rowconfigure(0, weight=1)

        # Camera feed canvas
        self._cam_canvas = tk.Canvas(
            f, bg="#000508", highlightthickness=1,
            highlightbackground=PURPLE
        )
        self._cam_canvas.grid(row=0, column=0, sticky="nsew", padx=12, pady=(10, 6))
        self._cam_canvas.create_text(
            320, 240, text="◉  CAMERA OFFLINE\nPress [ START CAMERA ] to activate",
            fill=TEXT2, font=self._fonts["body_lg"], justify="center"
        )

        # Corner HUD overlays drawn on canvas
        self._cam_overlay_on = False

        # Controls row
        ctrl = tk.Frame(f, bg=BG0)
        ctrl.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 4))
        for i in range(4):
            ctrl.columnconfigure(i, weight=1)

        self._cam_running   = False
        self._cam_cap       = None
        self._cam_photo_ref = None
        self._cam_last_img  = None   # PIL Image of last frame
        self._cam_last_frame_raw = None
        self._gesture_ctrl   = None
        self._gesture_active = False
        self._gesture_btn    = None
        self._gesture_status_var = None

        self._cam_start_btn = tk.Button(
            ctrl, text="▶  START CAMERA",
            bg=PURPLE, fg=TEXT1, activebackground=CYAN, activeforeground=BG0,
            font=self._fonts["button"], relief="flat", cursor="hand2",
            command=self._toggle_camera
        )
        self._cam_start_btn.grid(row=0, column=0, padx=4, pady=6, sticky="ew")

        tk.Button(
            ctrl, text="📷  SNAPSHOT",
            bg=BG2, fg=TEXT1, activebackground=CYAN, activeforeground=BG0,
            font=self._fonts["button"], relief="flat", cursor="hand2",
            command=self._save_snapshot
        ).grid(row=0, column=1, padx=4, pady=6, sticky="ew")

        tk.Button(
            ctrl, text="🤖  ASK JARVIS",
            bg=BLUE, fg=TEXT1, activebackground=CYAN, activeforeground=BG0,
            font=self._fonts["button"], relief="flat", cursor="hand2",
            command=self._ask_about_camera
        ).grid(row=0, column=2, padx=4, pady=6, sticky="ew")

        tk.Button(
            ctrl, text="👤  DETECT FACE",
            bg=BG2, fg=TEXT1, activebackground=GREEN, activeforeground=BG0,
            font=self._fonts["button"], relief="flat", cursor="hand2",
            command=self._detect_faces_now
        ).grid(row=0, column=3, padx=4, pady=6, sticky="ew")

        # Ask prompt row
        ask_row = tk.Frame(f, bg=BG0)
        ask_row.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 8))
        ask_row.columnconfigure(0, weight=1)

        tk.Label(ask_row, text="Ask about what camera sees:",
                 font=self._fonts["body_sm"], fg=TEXT2, bg=BG0).pack(anchor="w")

        ask_inner = tk.Frame(ask_row, bg=BG0)
        ask_inner.pack(fill="x", pady=4)
        ask_inner.columnconfigure(0, weight=1)

        self._cam_ask_var = tk.StringVar()
        cam_entry = tk.Entry(
            ask_inner, textvariable=self._cam_ask_var,
            bg=BG2, fg=TEXT1, insertbackground=PURPLE,
            font=self._fonts["input"], relief="flat",
            highlightthickness=1, highlightbackground=PURPLE
        )
        cam_entry.grid(row=0, column=0, sticky="ew", ipady=6)
        cam_entry.bind("<Return>", lambda e: self._ask_about_camera())

        tk.Button(
            ask_inner, text="ASK  →",
            bg=PURPLE, fg=TEXT1, activebackground=CYAN, activeforeground=BG0,
            font=self._fonts["button"], relief="flat", cursor="hand2",
            command=self._ask_about_camera
        ).grid(row=0, column=1, padx=(6, 0))

        # Status labels
        self._cam_status_var = tk.StringVar(value="Camera offline")
        tk.Label(f, textvariable=self._cam_status_var,
                 font=self._fonts["body_sm"], fg=PURPLE, bg=BG0
                ).grid(row=3, column=0, pady=(0, 2))

        self._gesture_status_var = tk.StringVar(value="—  Gesture control off")
        tk.Label(f, textvariable=self._gesture_status_var,
                 font=self._fonts["body_sm"], fg=GREEN, bg=BG0
                ).grid(row=4, column=0, pady=(0, 4))

        # Gesture legend
        legend_f = tk.Frame(f, bg=BG0)
        legend_f.grid(row=5, column=0, sticky="ew", padx=12, pady=(0, 8))
        tk.Label(legend_f, text="GESTURE LEGEND", font=self._fonts["section"],
                 fg=TEXT2, bg=BG0).pack(anchor="w")
        gestures = [
            ("☝  Index only",       "Move cursor"),
            ("🤏  Pinch",              "Left click"),
            ("✌  Index+Middle",     "Right click"),
            ("🤚  Open palm",          "Scroll up"),
            ("✊  Fist",               "Scroll down"),
            ("👍  Thumb up",           "Volume up"),
            ("👎  Thumb down",         "Volume down"),
            ("🤘  Rock sign",           "Screenshot"),
            ("🖐  All up + wrist high", "Wake JARVIS"),
        ]
        for g, action in gestures:
            row_f = tk.Frame(legend_f, bg=BG0)
            row_f.pack(fill="x", pady=1)
            tk.Label(row_f, text=g, font=self._fonts["body_sm"],
                     fg=TEXT1, bg=BG0, width=22, anchor="w").pack(side="left")
            tk.Label(row_f, text=action, font=self._fonts["body_sm"],
                     fg=CYAN, bg=BG0).pack(side="left")


    def _toggle_gesture_control(self):
        if not self._gesture_ctrl:
            self.show_notification('Gesture Control', 'Restart JARVIS to enable gesture control.')
            return
        active = self._gesture_ctrl.toggle(cam_index=0)
        self._gesture_active = active
        if active:
            if self._gesture_btn: self._gesture_btn.configure(text='GESTURE ON', bg=GREEN, fg=BG0)
            if self._gesture_status_var: self._gesture_status_var.set('Gesture control ACTIVE')
            self._open_camera_tab()
            if not self._cam_running: self._start_camera()
        else:
            if self._gesture_btn: self._gesture_btn.configure(text='GESTURE CTRL', bg=BG2, fg=TEXT2)
            if self._gesture_status_var: self._gesture_status_var.set('Gesture control off')

    def _open_camera_tab(self):
        """Switch to camera tab."""
        for i in range(self._nb.index("end")):
            if "CAMERA" in self._nb.tab(i, "text"):
                self._nb.select(i)
                break

    def _toggle_camera(self):
        if self._cam_running:
            self._stop_camera()
        else:
            self._start_camera()

    def _start_camera(self):
        try:
            import cv2  # noqa
        except ImportError:
            self._cam_status_var.set("opencv-python not installed. Run: pip install opencv-python")
            return
        import cv2
        cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        if not cap.isOpened():
            cap = cv2.VideoCapture(0)   # fallback to default backend
        if not cap.isOpened():
            self._cam_status_var.set("⚠ Camera not accessible. Check permissions.")
            return
        self._cam_cap = cap
        self._cam_running = True
        self._cam_start_btn.configure(text="⏹  STOP CAMERA", bg=RED)
        self._cam_status_var.set("◉  CAMERA LIVE")
        self._cam_overlay_on = True
        threading.Thread(target=self._camera_loop, daemon=True).start()

    def _stop_camera(self):
        self._cam_running = False
        if self._cam_cap:
            try:
                self._cam_cap.release()
            except Exception:
                pass
            self._cam_cap = None
        self._cam_start_btn.configure(text="▶  START CAMERA", bg=PURPLE)
        self._cam_status_var.set("Camera stopped")
        self._cam_overlay_on = False
        self.root.after(100, lambda: (
            self._cam_canvas.delete("all"),
            self._cam_canvas.create_text(
                self._cam_canvas.winfo_width() // 2 or 320,
                self._cam_canvas.winfo_height() // 2 or 240,
                text="◉  CAMERA OFFLINE",
                fill=TEXT2, font=self._fonts["body_lg"]
            )
        ))

    def _camera_loop(self):
        """Background thread: read frames and push to canvas."""
        import cv2
        while self._cam_running and self._cam_cap:
            ret, frame = self._cam_cap.read()
            if not ret:
                break
            self._cam_last_frame_raw = frame.copy()   # BGR numpy for CV ops
            # Convert BGR → RGB → PIL
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            self.root.after(0, self._update_camera_frame, rgb)
            import time as _t
            _t.sleep(0.033)   # ~30 fps

    def _update_camera_frame(self, rgb_array):
        """Update tkinter canvas with latest frame (runs on main thread)."""
        try:
            from PIL import Image, ImageTk, ImageDraw
        except ImportError:
            return
        try:
            cw = self._cam_canvas.winfo_width()  or 640
            ch = self._cam_canvas.winfo_height() or 480

            img = Image.fromarray(rgb_array).resize((cw, ch), Image.LANCZOS)
            self._cam_last_img = img.copy()  # Save clean RGB copy for snapshots/AI

            # Convert to RGBA so we can draw semi-transparent overlays
            overlay = img.convert("RGBA")
            draw = ImageDraw.Draw(overlay)

            # Corner HUD brackets (fully opaque cyan)
            bw, bt, pad = 30, 3, 12
            for (x0, y0, xd, yd) in [
                (pad, pad, 1, 1),
                (cw-pad, pad, -1, 1),
                (pad, ch-pad, 1, -1),
                (cw-pad, ch-pad, -1, -1),
            ]:
                draw.line([(x0, y0), (x0+xd*bw, y0)], fill=(0, 212, 255, 255), width=bt)
                draw.line([(x0, y0), (x0, y0+yd*bw)], fill=(0, 212, 255, 255), width=bt)

            # Scanlines (subtle dark lines)
            for y in range(0, ch, 6):
                draw.line([(0, y), (cw, y)], fill=(0, 0, 0, 40))

            # Center crosshair
            cx, cy = cw//2, ch//2
            draw.line([(cx-20, cy), (cx+20, cy)], fill=(0, 212, 255, 200), width=1)
            draw.line([(cx, cy-20), (cx, cy+20)], fill=(0, 212, 255, 200), width=1)

            # Convert back to RGB for tkinter
            final = overlay.convert("RGB")

            photo = ImageTk.PhotoImage(final)
            self._cam_photo_ref = photo
            self._cam_canvas.delete("all")
            self._cam_canvas.create_image(0, 0, anchor="nw", image=photo)

            # Timestamp overlay via canvas text (no PIL needed)
            now = datetime.datetime.now().strftime("%H:%M:%S")
            self._cam_canvas.create_text(
                cw - 8, ch - 8, anchor="se",
                text="REC  " + now,
                fill=CYAN, font=self._fonts["body_sm"]
            )
        except Exception as _e:
            import traceback
            traceback.print_exc()

    def _save_snapshot(self):
        """Save current frame to disk and notify."""
        if self._cam_last_img is None:
            self.show_notification("Camera", "No frame captured yet. Start the camera first.")
            return
        import os, tempfile
        path = os.path.join(tempfile.gettempdir(), "jarvis_snapshot.jpg")
        self._cam_last_img.save(path)
        self.show_notification("Snapshot Saved", f"Saved to:\n{path}")
        self._cam_status_var.set(f"Snapshot saved: {path}")

    def _ask_about_camera(self):
        """Capture current frame and ask JARVIS to analyze it."""
        import os as _os, tempfile
        question = self._cam_ask_var.get().strip()
        if not question:
            question = "What do you see? Describe everything in detail."

        # Try to grab the latest frame directly from the live capture
        if self._cam_cap and self._cam_running:
            try:
                import cv2
                ret, frame = self._cam_cap.read()
                if ret:
                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    from PIL import Image
                    self._cam_last_img = Image.fromarray(rgb)
                    self._cam_last_frame_raw = frame.copy()
            except Exception:
                pass

        if self._cam_last_img is None:
            if not self._cam_running:
                self.show_notification("Camera", "Start the camera first — press the START CAMERA button.")
            else:
                self.show_notification("Camera", "Camera is starting up, please wait a moment and try again.")
            return

        frame_path = _os.path.join(tempfile.gettempdir(), "jarvis_cam_ask.jpg")
        try:
            self._cam_last_img.save(frame_path)
        except Exception as e:
            self.show_notification("Camera", f"Could not save frame: {e}")
            return

        self._cam_ask_var.set("")
        cmd = "look at camera image " + frame_path + " and answer: " + question
        self.add_user_message("[Camera] " + question)
        self.command_queue.put(cmd)
        self._cam_status_var.set("Analyzing frame...")

    def _detect_faces_now(self):
        """Run face detection on current frame."""
        if not hasattr(self, "_cam_last_frame_raw") or self._cam_last_frame_raw is None:
            self.show_notification("Camera", "Start the camera first.")
            return
        try:
            import cv2
            import numpy as np
            face_detector = cv2.CascadeClassifier(
                cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            )
            gray = cv2.cvtColor(self._cam_last_frame_raw, cv2.COLOR_BGR2GRAY)
            faces = face_detector.detectMultiScale(
                gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60)
            )
            count = len(faces)
            msg = f"{count} face(s) detected" if count else "No faces detected"
            self._cam_status_var.set(f"◉  {msg}")
            self.show_notification("Face Detection", msg)
            # Draw boxes on canvas if faces found
            if count and self._cam_last_img:
                from PIL import Image, ImageTk, ImageDraw
                img = self._cam_last_img.copy()
                draw = ImageDraw.Draw(img)
                cw = self._cam_canvas.winfo_width() or 640
                ch = self._cam_canvas.winfo_height() or 480
                scale_x = cw / self._cam_last_frame_raw.shape[1]
                scale_y = ch / self._cam_last_frame_raw.shape[0]
                for (x, y, w, h) in faces:
                    draw.rectangle(
                        [int(x*scale_x), int(y*scale_y),
                         int((x+w)*scale_x), int((y+h)*scale_y)],
                        outline=(0, 255, 136), width=2
                    )
                photo = ImageTk.PhotoImage(img)
                self._cam_photo_ref = photo
                self._cam_canvas.delete("all")
                self._cam_canvas.create_image(0, 0, anchor="nw", image=photo)
        except ImportError:
            self._cam_status_var.set("opencv-python not installed")
        except Exception as e:
            self._cam_status_var.set(f"Error: {e}")

    # ── Input bar ────────────────────────────────────────────
    def _build_input_bar(self, parent):
        bar = tk.Frame(parent, bg=BG2,
                       highlightthickness=1, highlightbackground=BORDER)
        bar.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        bar.columnconfigure(1, weight=1)

        tk.Label(bar, text=">", font=self._fonts["input"],
                 fg=CYAN, bg=BG2).grid(row=0, column=0, padx=(12, 4), pady=10)

        self._input_var = tk.StringVar()
        self._entry = tk.Entry(
            bar, textvariable=self._input_var,
            bg=BG2, fg=TEXT1, insertbackground=CYAN,
            font=self._fonts["input"], relief="flat", highlightthickness=0
        )
        self._entry.grid(row=0, column=1, sticky="ew", pady=10)
        self._entry.bind("<Return>", self._on_submit)
        self._entry.focus_set()

        tk.Button(bar, text="SEND  →", bg=BLUE, fg=TEXT1,
                  activebackground=CYAN, activeforeground=BG0,
                  font=self._fonts["button"], relief="flat",
                  cursor="hand2", padx=14, pady=8,
                  command=self._on_submit
                 ).grid(row=0, column=2, padx=(0, 8))

        self._voice_hint_label = tk.Label(
            bar,
            text=f'Type a command or say "{WAKE_WORD.title()}". Press F11 for immersive view.',
            font=self._fonts["body_sm"], fg=TEXT2, bg=BG2
        )
        self._voice_hint_label.grid(row=1, column=0, columnspan=3, sticky="w", padx=12, pady=(0, 6))

    # ── Chat helpers ─────────────────────────────────────────
    def add_user_message(self, text: str):
        self.root.after(0, self._append_user, text)

    def add_jarvis_message(self, text: str):
        self.root.after(0, self._append_jarvis, text)

    def _append_user(self, text: str):
        now = datetime.datetime.now().strftime("%H:%M")
        self._chat_write(f"\n[{now}] ", "time")
        self._chat_write(f"{USER_NAME}: ", "user")
        self._chat_write(text + "\n", "user")
        self._chat_text.see("end")

    def _append_jarvis(self, text: str):
        now = datetime.datetime.now().strftime("%H:%M")
        self._chat_write(f"[{now}] ", "time")
        self._chat_write(f"{JARVIS_NAME}: ", "jarvis")
        self._chat_write(text + "\n", "jarvis")
        self._chat_text.see("end")

    def _chat_append_system(self, text: str):
        self._chat_write(f"◈ {text}\n", "system")

    def _chat_write(self, text: str, tag: str = ""):
        self._chat_text.configure(state="normal")
        self._chat_text.insert("end", text, tag if tag else ())
        self._chat_text.configure(state="disabled")

    def _clear_chat(self):
        self._chat_text.configure(state="normal")
        self._chat_text.delete("1.0", "end")
        self._chat_text.configure(state="disabled")
        self._chat_append_system("Conversation cleared.")

    # ── Terminal helpers ──────────────────────────────────────
    def _term_log(self, text: str, tag: str = "out"):
        """Write to terminal tab — callable from background threads."""
        def _do():
            self._term_text.configure(state="normal")
            self._term_text.insert("end", text + "\n", tag)
            self._term_text.configure(state="disabled")
            self._term_text.see("end")
        self.root.after(0, _do)

    def terminal_log(self, text: str):
        """Public method for brain to call."""
        self._term_log(text, "out")

    def _on_term_submit(self, event=None):
        cmd = self._term_input_var.get().strip()
        if not cmd: return
        self._term_input_var.set("")
        self._term_log(f"$ {cmd}", "cmd")
        # Send to brain as a terminal command
        self.command_queue.put(f"run command {cmd}")
        if self.listener:
            pass  # already queued

    # ── Status ───────────────────────────────────────────────
    def set_status(self, status: str):
        self.status = status
        color = STATUS_COLOR.get(status, CYAN)
        label = STATUS_LABEL.get(status, status.upper())
        mode_map = {
            "sleeping":  "STANDBY MODE",
            "listening": "LISTENING...",
            "thinking":  "PROCESSING...",
            "speaking":  "SPEAKING",
        }

        def _update():
            self._status_var.set(label)
            self._status_lbl.configure(fg=color)
            self._mode_var.set(mode_map.get(status, status.upper()))
            if hasattr(self, "_command_state_var"):
                self._command_state_var.set(mode_map.get(status, status.upper()))
            self._hud.set_status(status)
            self._wave.set_active(status == "speaking")

        self.root.after(0, _update)

    # ── Notification popup ────────────────────────────────────
    def show_notification(self, title: str, message: str):
        def _show():
            pop = tk.Toplevel(self.root)
            pop.title(title)
            pop.configure(bg=BG2)
            pop.geometry("340x130")
            pop.attributes("-topmost", True)
            pop.resizable(False, False)
            tk.Label(pop, text=f"  {title}", font=self._fonts["mono_popup"],
                     fg=AMBER, bg=BG2, anchor="w").pack(fill="x", pady=(16, 4), padx=16)
            tk.Label(pop, text=message, font=self._fonts["body"],
                     fg=TEXT1, bg=BG2, wraplength=300, justify="left").pack(pady=4, padx=16)
            tk.Button(pop, text="  DISMISS  ", bg=BLUE, fg=TEXT1,
                      font=self._fonts["button"], relief="flat", cursor="hand2",
                      command=pop.destroy).pack(pady=8)
            pop.after(8000, pop.destroy)
        self.root.after(0, _show)

    # ── Clock ────────────────────────────────────────────────
    def _start_clock(self):
        def _tick():
            now = datetime.datetime.now()
            self._clock_var.set(now.strftime("%H:%M:%S"))
            self.root.after(1000, _tick)
        _tick()

    # ── System monitor (live metrics) ─────────────────────────
    def _start_sys_monitor(self):
        def _update():
            if not self._running: return
            try:
                import psutil
                cpu  = psutil.cpu_percent(interval=0)
                ram  = psutil.virtual_memory().percent
                disk = psutil.disk_usage("/").percent
                self._cpu_bar.update_value(cpu)
                self._ram_bar.update_value(ram)
                self._disk_bar.update_value(disk)
            except Exception:
                pass
            self.root.after(2000, _update)
        _update()

    # ── Controls ─────────────────────────────────────────────
    def _activate(self):
        if self.listener:
            self.listener.wake(with_callback=True)
        else:
            self.command_queue.put("__WAKE__")
        self.set_status("listening")

    def _sleep(self):
        if self.listener:
            self.listener.sleep()
        self.command_queue.put("__SLEEP__")
        self.set_status("sleeping")

    def _quick_cmd(self, cmd: str):
        self._append_user(cmd)
        self.command_queue.put(cmd)

    def _open_workspace(self):
        self.command_queue.put("run command explorer JarvisWorkspace" if __import__("sys").platform=="win32"
                               else "run command xdg-open JarvisWorkspace")

    def _on_submit(self, event=None):
        text = self._input_var.get().strip()
        if not text: return
        self._input_var.set("")
        if self.listener:
            self.listener.inject_text(text)
        else:
            self.command_queue.put(text)
            self._append_user(text)

    # ── Lifecycle ─────────────────────────────────────────────
    def _on_close(self):
        self._running = False
        self._hud.stop()
        if getattr(self, "_cam_running", False):
            self._stop_camera()
        self.root.destroy()

    def run(self):
        self.root.mainloop()
