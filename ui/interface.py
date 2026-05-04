"""
ui/interface.py
Ultra-futuristic JARVIS GUI.
Canvas HUD with animated rings + particles, tabbed interface
(Chat | Terminal | System | Memory), live system metrics, voice waveform.
"""
import math, random, threading, datetime, time
import queue as q_module
import tkinter as tk
from tkinter import ttk, scrolledtext
from config.settings import JARVIS_NAME, USER_NAME, WAKE_WORD

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


# ═══════════════════════════════════════════════════════════════
class HUDCanvas(tk.Canvas):
    """
    Animated holographic HUD visualizer.
    Multiple rotating rings, particle field, pulsing center.
    """
    W = H = 220

    def __init__(self, parent, **kw):
        super().__init__(parent, width=self.W, height=self.H,
                         bg=BG1, highlightthickness=0, **kw)
        self.cx = self.cy = self.W // 2
        self.status = "sleeping"
        self._angle1 = 0.0   # outer ring
        self._angle2 = 0.0   # mid ring (counter)
        self._angle3 = 0.0   # inner ring
        self._pulse  = 0.0   # center pulse
        self._particles = self._make_particles(22)
        self._running = True
        self._draw()

    def set_status(self, s: str):
        self.status = s

    def stop(self):
        self._running = False

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

        # Background gradient (concentric dark circles)
        for r, c in [(105, "#06101e"), (90, "#070d18"), (72, "#060c16")]:
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
            len_ = 6 if i % 3 == 0 else 3
            x1 = cx + 100 * math.cos(ang)
            y1 = cy + 100 * math.sin(ang)
            x2 = cx + (100 - len_) * math.cos(ang)
            y2 = cy + (100 - len_) * math.sin(ang)
            tick_c = self._alpha_hex(color, 60 if i % 3 == 0 else 30)
            self.create_line(x1, y1, x2, y2, fill=tick_c, width=1)

        # Outer ring (rotating dash arc)
        ext = 280 if self.status != "sleeping" else 120
        self._draw_arc(cx, cy, 98, self._angle1, ext, color, 2)

        # Mid ring (counter-rotating)
        ext2 = 200 if self.status == "thinking" else 100
        self._draw_arc(cx, cy, 80, self._angle2, ext2,
                       self._alpha_hex(color, 130), 1)

        # Inner ring
        ext3 = 160 if self.status in ("listening","speaking") else 60
        self._draw_arc(cx, cy, 62, self._angle3, ext3,
                       self._alpha_hex(color, 100), 1)

        # Grid lines (horizontal/vertical)
        self._draw_grid(cx, cy, color)

        # Center glow
        pulse_r = 3 + 2 * math.sin(self._pulse)
        glow_layers = [(28, 20), (22, 40), (17, 70), (13, 120)]
        for rad, alpha in glow_layers:
            c = self._alpha_hex(color, alpha)
            self.create_oval(cx-rad, cy-rad, cx+rad, cy+rad,
                             fill=c, outline="")

        # Center hex background
        self._draw_hex(cx, cy, 14, BG0, color)

        # Center text "J"
        self.create_text(cx, cy, text="J", fill=color,
                         font=("Courier New", 14, "bold"))

        # Status ring (thin colored border)
        pulse_extra = 2 * math.sin(self._pulse * 2)
        sr = 50 + pulse_extra
        self.create_oval(cx-sr, cy-sr, cx+sr, cy+sr,
                         outline=self._alpha_hex(color, 80), width=1)

        self.after(40, self._draw)

    def _draw_arc(self, cx, cy, r, start, extent, color, width):
        self.create_arc(cx-r, cy-r, cx+r, cy+r,
                        start=start, extent=extent,
                        outline=color, width=width, style="arc")

    def _draw_grid(self, cx, cy, color):
        lc = self._alpha_hex(color, 18)
        for offset in [-40, 0, 40]:
            self.create_line(cx + offset, cy - 95, cx + offset, cy + 95,
                             fill=lc, width=1)
            self.create_line(cx - 95, cy + offset, cx + 95, cy + offset,
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
    def __init__(self, parent, label: str, color: str = CYAN, **kw):
        super().__init__(parent, bg=BG1, **kw)
        self._color = color
        tk.Label(self, text=label, font=FONT_MONO_SM, fg=TEXT2,
                 bg=BG1, width=4, anchor="w").pack(side="left")
        self._canvas = tk.Canvas(self, width=110, height=10,
                                 bg=BG2, highlightthickness=0)
        self._canvas.pack(side="left", padx=4)
        self._pct_var = tk.StringVar(value="  0%")
        tk.Label(self, textvariable=self._pct_var, font=FONT_MONO_SM,
                 fg=TEXT1, bg=BG1, width=5).pack(side="left")

    def update_value(self, pct: float):
        self._canvas.delete("all")
        self._canvas.create_rectangle(0, 0, 110, 10, fill=BG2, outline="")
        w = int(pct / 100 * 110)
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

        self.root = tk.Tk()
        self.root.title(f"J.A.R.V.I.S — Advanced AI System")
        self.root.geometry("1100x740")
        self.root.minsize(900, 620)
        self.root.configure(bg=BG0)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._center_window()
        self._apply_style()
        self._build_ui()
        self._start_clock()
        self._start_sys_monitor()

    # ── Setup ────────────────────────────────────────────────
    def _center_window(self):
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        w, h = 1100, 740
        self.root.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

    def _apply_style(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(".", background=BG0, foreground=TEXT1,
                        font=FONT_MONO, borderwidth=0)
        style.configure("TNotebook", background=BG1, borderwidth=0,
                        tabmargins=[0, 0, 0, 0])
        style.configure("TNotebook.Tab", background=BG2, foreground=TEXT2,
                        font=FONT_MONO_SM, padding=[14, 6],
                        borderwidth=0, relief="flat")
        style.map("TNotebook.Tab",
                  background=[("selected", BG1)],
                  foreground=[("selected", CYAN)])
        style.configure("TSeparator", background=BORDER)

    # ── Main UI ─────────────────────────────────────────────
    def _build_ui(self):
        # ── Header ──
        self._build_header()
        tk.Frame(self.root, bg=CYAN, height=1).pack(fill="x")

        # ── Body ──
        body = tk.Frame(self.root, bg=BG0)
        body.pack(fill="both", expand=True, padx=8, pady=8)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        self._build_sidebar(body)
        self._build_main_panel(body)

    # ── Header ──────────────────────────────────────────────
    def _build_header(self):
        hdr = tk.Frame(self.root, bg=BG1, height=56)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        # Left: Logo
        logo_f = tk.Frame(hdr, bg=BG1)
        logo_f.pack(side="left", padx=16)
        tk.Label(logo_f, text="⬡", font=("Courier New", 22, "bold"),
                 fg=CYAN, bg=BG1).pack(side="left")
        tk.Label(logo_f, text=" J.A.R.V.I.S", font=FONT_TITLE,
                 fg=CYAN, bg=BG1).pack(side="left")
        tk.Label(logo_f, text="  /  ADVANCED AI SYSTEM",
                 font=FONT_MONO_SM, fg=TEXT2, bg=BG1).pack(side="left")

        # Right: clock + status
        right_f = tk.Frame(hdr, bg=BG1)
        right_f.pack(side="right", padx=16)

        self._status_var = tk.StringVar(value=STATUS_LABEL["sleeping"])
        self._status_lbl = tk.Label(right_f, textvariable=self._status_var,
                                    font=("Courier New", 10, "bold"),
                                    fg=STATUS_COLOR["sleeping"], bg=BG1)
        self._status_lbl.pack(side="right", padx=(16, 0))

        self._clock_var = tk.StringVar()
        tk.Label(right_f, textvariable=self._clock_var,
                 font=("Courier New", 14), fg=TEXT2, bg=BG1).pack(side="right")

    # ── Sidebar ─────────────────────────────────────────────
    def _build_sidebar(self, parent):
        side = tk.Frame(parent, bg=BG1, width=240)
        side.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        side.grid_propagate(False)
        side.columnconfigure(0, weight=1)

        # HUD Canvas
        self._hud = HUDCanvas(side)
        self._hud.pack(pady=(12, 4), padx=10)

        # Waveform
        self._wave = WaveformBar(side)
        self._wave.pack(fill="x", padx=10, pady=(0, 8))

        # Status text under HUD
        self._mode_var = tk.StringVar(value="STANDBY MODE")
        tk.Label(side, textvariable=self._mode_var,
                 font=FONT_MONO_SM, fg=TEXT2, bg=BG1).pack()

        # Separator
        tk.Frame(side, bg=BORDER, height=1).pack(fill="x", padx=10, pady=8)

        # System metrics
        tk.Label(side, text="SYSTEM METRICS",
                 font=FONT_MONO_SM, fg=TEXT2, bg=BG1).pack(anchor="w", padx=12)

        metrics_f = tk.Frame(side, bg=BG1)
        metrics_f.pack(fill="x", padx=10, pady=4)
        self._cpu_bar  = MetricBar(metrics_f, "CPU", CYAN)
        self._cpu_bar.pack(fill="x", pady=2)
        self._ram_bar  = MetricBar(metrics_f, "RAM", GREEN)
        self._ram_bar.pack(fill="x", pady=2)
        self._disk_bar = MetricBar(metrics_f, "DSK", AMBER)
        self._disk_bar.pack(fill="x", pady=2)

        # Separator
        tk.Frame(side, bg=BORDER, height=1).pack(fill="x", padx=10, pady=8)

        # Control buttons
        self._build_sidebar_buttons(side)

        # Wake word hint
        tk.Frame(side, bg=BORDER, height=1).pack(fill="x", padx=10, pady=8)
        tk.Label(side, text=f'Wake: "{WAKE_WORD.title()}"',
                 font=FONT_MONO_SM, fg=TEXT2, bg=BG1,
                 wraplength=200).pack(pady=2)

    def _build_sidebar_buttons(self, parent):
        btn_cfg = dict(
            font=("Courier New", 9, "bold"), relief="flat",
            cursor="hand2", pady=5, borderwidth=0
        )
        def btn(p, text, bg, fg, cmd):
            b = tk.Button(p, text=text, bg=bg, fg=fg,
                          activebackground=CYAN, activeforeground=BG0,
                          command=cmd, **btn_cfg)
            b.pack(fill="x", padx=10, pady=2)
            return b

        btn(parent, "⊙  ACTIVATE",  BLUE, TEXT1, self._activate)
        btn(parent, "◌  SLEEP",     BG2,  TEXT2, self._sleep)
        btn(parent, "✕  CLEAR CHAT", BG2, TEXT2, self._clear_chat)
        btn(parent, "⚙  WORKSPACE", BG2,  TEXT2, self._open_workspace)

        # Quick actions
        tk.Frame(parent, bg=BORDER, height=1).pack(fill="x", padx=10, pady=6)
        tk.Label(parent, text="QUICK COMMANDS",
                 font=FONT_MONO_SM, fg=TEXT2, bg=BG1).pack(anchor="w", padx=12)
        quick = [
            ("⏰ Time", "what time is it"),
            ("🔋 Battery", "battery status"),
            ("📸 Screenshot", "take a screenshot"),
            ("💻 System Info", "cpu usage and ram usage"),
            ("🌐 Google", "open google"),
            ("📂 Downloads", "open downloads folder"),
        ]
        for label, cmd in quick:
            tk.Button(parent, text=label, bg=BG2, fg=TEXT1,
                      activebackground=BLUE, activeforeground=TEXT1,
                      relief="flat", cursor="hand2", pady=3,
                      font=FONT_MONO_SM, borderwidth=0,
                      command=lambda c=cmd: self._quick_cmd(c)
                     ).pack(fill="x", padx=10, pady=1)

    # ── Main panel ──────────────────────────────────────────
    def _build_main_panel(self, parent):
        main = tk.Frame(parent, bg=BG0)
        main.grid(row=0, column=1, sticky="nsew")
        main.columnconfigure(0, weight=1)
        main.rowconfigure(0, weight=1)

        # Notebook tabs
        self._nb = ttk.Notebook(main)
        self._nb.grid(row=0, column=0, sticky="nsew")

        self._build_chat_tab()
        self._build_terminal_tab()
        self._build_system_tab()
        self._build_memory_tab()

        # Input bar
        self._build_input_bar(main)

    # ── Chat tab ────────────────────────────────────────────
    def _build_chat_tab(self):
        f = tk.Frame(self._nb, bg=BG1)
        self._nb.add(f, text="  CHAT  ")
        f.columnconfigure(0, weight=1)
        f.rowconfigure(0, weight=1)

        self._chat_text = tk.Text(
            f, bg=BG1, fg=TEXT1, insertbackground=CYAN,
            font=FONT_MONO_LG, relief="flat", padx=14, pady=10,
            wrap="word", state="disabled", spacing3=6,
            selectbackground=BLUE, selectforeground=TEXT1
        )
        sb = tk.Scrollbar(f, command=self._chat_text.yview, bg=BG0,
                          troughcolor=BG2, activebackground=CYAN)
        self._chat_text.configure(yscrollcommand=sb.set)
        self._chat_text.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")

        self._chat_text.tag_configure("user",
            foreground=BLUE, font=("Courier New", 11, "bold"))
        self._chat_text.tag_configure("jarvis",
            foreground=CYAN, font=("Courier New", 11))
        self._chat_text.tag_configure("system",
            foreground=TEXT2, font=("Courier New", 9, "italic"))
        self._chat_text.tag_configure("time",
            foreground="#1a2a3a", font=("Courier New", 9))
        self._chat_text.tag_configure("plan",
            foreground=AMBER, font=("Courier New", 10))

        self._chat_append_system(f"System online. Say '{WAKE_WORD.title()}' or type below.")

    # ── Terminal tab ─────────────────────────────────────────
    def _build_terminal_tab(self):
        f = tk.Frame(self._nb, bg=BG0)
        self._nb.add(f, text="  TERMINAL  ")
        f.columnconfigure(0, weight=1)
        f.rowconfigure(0, weight=1)

        # Output area
        self._term_text = tk.Text(
            f, bg="#020408", fg="#00ff66", insertbackground=GREEN,
            font=("Courier New", 11), relief="flat", padx=12, pady=8,
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

        tk.Label(term_in, text="JARVIS $", font=("Courier New", 11, "bold"),
                 fg=GREEN, bg="#030608").grid(row=0, column=0, padx=8)

        self._term_input_var = tk.StringVar()
        self._term_entry = tk.Entry(
            term_in, textvariable=self._term_input_var,
            bg="#030608", fg=GREEN, insertbackground=GREEN,
            font=("Courier New", 11), relief="flat", highlightthickness=0
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
            font=FONT_MONO, relief="flat", padx=12, pady=8,
            wrap="word", state="disabled"
        )
        self._sys_text.grid(row=0, column=0, sticky="nsew")
        self._sys_text.tag_configure("header", foreground=CYAN,
                                     font=("Courier New", 10, "bold"))
        self._sys_text.tag_configure("val",    foreground=TEXT1)
        self._sys_text.tag_configure("warn",   foreground=AMBER)
        self._sys_text.tag_configure("good",   foreground=GREEN)

        tk.Button(f, text="↻  REFRESH", bg=BLUE, fg=TEXT1, relief="flat",
                  font=FONT_MONO_SM, cursor="hand2",
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
            font=FONT_MONO, relief="flat", padx=12, pady=8,
            wrap="word", state="disabled"
        )
        self._mem_text.grid(row=0, column=0, sticky="nsew")
        self._mem_text.tag_configure("header", foreground=CYAN,
                                     font=("Courier New", 10, "bold"))
        self._mem_text.tag_configure("item",   foreground=TEXT1)
        self._mem_text.tag_configure("meta",   foreground=TEXT2,
                                     font=("Courier New", 9))

        tk.Button(f, text="↻  REFRESH MEMORY", bg=BLUE, fg=TEXT1,
                  relief="flat", font=FONT_MONO_SM, cursor="hand2",
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

    # ── Input bar ────────────────────────────────────────────
    def _build_input_bar(self, parent):
        bar = tk.Frame(parent, bg=BG2,
                       highlightthickness=1, highlightbackground=BORDER)
        bar.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        bar.columnconfigure(1, weight=1)

        tk.Label(bar, text=">", font=("Courier New", 13, "bold"),
                 fg=CYAN, bg=BG2).grid(row=0, column=0, padx=(12, 4), pady=10)

        self._input_var = tk.StringVar()
        self._entry = tk.Entry(
            bar, textvariable=self._input_var,
            bg=BG2, fg=TEXT1, insertbackground=CYAN,
            font=FONT_MONO_LG, relief="flat", highlightthickness=0
        )
        self._entry.grid(row=0, column=1, sticky="ew", pady=10)
        self._entry.bind("<Return>", self._on_submit)
        self._entry.focus_set()

        tk.Button(bar, text="SEND  →", bg=BLUE, fg=TEXT1,
                  activebackground=CYAN, activeforeground=BG0,
                  font=("Courier New", 10, "bold"), relief="flat",
                  cursor="hand2", padx=14, pady=8,
                  command=self._on_submit
                 ).grid(row=0, column=2, padx=(0, 8))

        tk.Label(bar,
                 text=f'Type or say "{WAKE_WORD.title()}" to activate voice mode',
                 font=FONT_MONO_SM, fg=TEXT2, bg=BG2
                ).grid(row=1, column=0, columnspan=3, sticky="w", padx=12, pady=(0, 6))

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
            tk.Label(pop, text=f"  {title}", font=("Courier New", 12, "bold"),
                     fg=AMBER, bg=BG2, anchor="w").pack(fill="x", pady=(16, 4), padx=16)
            tk.Label(pop, text=message, font=FONT_MONO,
                     fg=TEXT1, bg=BG2, wraplength=300, justify="left").pack(pady=4, padx=16)
            tk.Button(pop, text="  DISMISS  ", bg=BLUE, fg=TEXT1,
                      font=FONT_MONO_SM, relief="flat", cursor="hand2",
                      command=pop.destroy).pack(pady=8)
            pop.after(8000, pop.destroy)
        self.root.after(0, _show)

    # ── Clock ────────────────────────────────────────────────
    def _start_clock(self):
        def _tick():
            now = datetime.datetime.now()
            self._clock_var.set(now.strftime("%H:%M:%S"))
            self.root.after(1000, _tick)
        self._clock_var = tk.StringVar()
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
        self.root.destroy()

    def run(self):
        self.root.mainloop()
