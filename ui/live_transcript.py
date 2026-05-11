"""
ui/live_transcript.py
Real-time live transcript display for JarvisX.

Shows what you say and what Jarvis replies, word-by-word,
as a floating panel with auto-fade.
"""
from __future__ import annotations
import threading
import time
import logging
from typing import Optional

log = logging.getLogger("live_transcript")

_FADE_AFTER  = 6.0   # seconds before fading
_MAX_LINES   = 6
_BG          = "#03111A"
_C_USER      = "#FFB800"
_C_JARVIS    = "#00DCFF"
_C_DIM       = "#2A4A5A"


class LiveTranscript:
    """
    Floating tkinter window that shows the live conversation transcript.
    Fades out after a period of silence.
    """

    def __init__(self):
        self._root  = None
        self._label = None
        self._lines: list[tuple[str, str]] = []   # [(speaker, text)]
        self._lock  = threading.Lock()
        self._last_update = 0.0
        self._visible = False
        self._thread: Optional[threading.Thread] = None
        self._fade_job = None

    def start(self):
        """Start the transcript window in a background thread."""
        self._thread = threading.Thread(target=self._run, daemon=True, name="live-transcript")
        self._thread.start()

    def add_user(self, text: str):
        """Add a user speech line."""
        self._add("You", text, _C_USER)

    def add_jarvis(self, text: str):
        """Add a Jarvis reply line (word-by-word streaming supported)."""
        self._add("Jarvis", text, _C_JARVIS)

    def stream_word(self, word: str):
        """Append a word to the last Jarvis line (streaming TTS)."""
        with self._lock:
            if self._lines and self._lines[-1][0] == "Jarvis":
                spk, txt, col = self._lines[-1] if len(self._lines[-1]) == 3 else (*self._lines[-1], _C_JARVIS)
                self._lines[-1] = ("Jarvis", txt + " " + word, _C_JARVIS)
            else:
                self._lines.append(("Jarvis", word, _C_JARVIS))
            if len(self._lines) > _MAX_LINES:
                self._lines.pop(0)
        self._refresh()

    def clear(self):
        """Clear all lines."""
        with self._lock:
            self._lines.clear()
        self._refresh()

    # ── Internal ───────────────────────────────────────────────────────────────

    def _add(self, speaker: str, text: str, color: str):
        short = (text or "").strip()[:120]
        if not short:
            return
        with self._lock:
            self._lines.append((speaker, short, color))
            if len(self._lines) > _MAX_LINES:
                self._lines.pop(0)
        self._last_update = time.time()
        self._refresh()
        self._schedule_fade()

    def _refresh(self):
        if self._root:
            self._root.after(0, self._redraw)

    def _schedule_fade(self):
        """Schedule auto-fade after FADE_AFTER seconds."""
        if self._root:
            if self._fade_job:
                try:
                    self._root.after_cancel(self._fade_job)
                except Exception:
                    pass
            self._fade_job = self._root.after(
                int(_FADE_AFTER * 1000), self._fade_out
            )

    def _fade_out(self):
        if self._root:
            try:
                self._root.attributes("-alpha", 0.0)
                self._visible = False
            except Exception:
                pass

    def _fade_in(self):
        if self._root:
            try:
                self._root.attributes("-alpha", 0.92)
                self._visible = True
            except Exception:
                pass

    def _run(self):
        import tkinter as tk
        self._root = tk.Tk()
        self._root.title("JarvisX Transcript")
        self._root.overrideredirect(True)
        self._root.attributes("-topmost", True)
        self._root.attributes("-alpha", 0.0)
        self._root.configure(bg=_BG)

        sw = self._root.winfo_screenwidth()
        sh = self._root.winfo_screenheight()
        W, H = 700, 140
        x = (sw - W) // 2
        y = sh - H - 80
        self._root.geometry(f"{W}x{H}+{x}+{y}")

        self._canvas = tk.Canvas(self._root, width=W, height=H,
                                 bg=_BG, highlightthickness=0)
        self._canvas.pack()
        self._root.mainloop()

    def _redraw(self):
        if not self._root or not hasattr(self, "_canvas"):
            return
        self._fade_in()
        c = self._canvas
        c.delete("all")
        W, H = 700, 140

        # Border
        c.create_rectangle(1, 1, W-1, H-1, outline=_C_DIM, width=1)

        with self._lock:
            lines = list(self._lines)

        y = 12
        line_h = max(1, (H - 20) // max(1, len(lines)))

        for speaker, text, color in lines[-_MAX_LINES:]:
            prefix = f"{speaker}: "
            c.create_text(10, y, text=prefix, anchor="nw",
                          fill=_C_DIM, font=("Consolas", 9, "bold"))
            c.create_text(10 + len(prefix) * 6, y, text=text, anchor="nw",
                          fill=color, font=("Consolas", 9))
            y += 20
