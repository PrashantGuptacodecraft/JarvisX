"""os_sampler.py - minimal continuous OS perception tick (Phase B · B5/B6 foundation).

Samples cheap, high-value OS signals on a fixed interval and publishes them as
`perception.os.snapshot` onto the Event Bus, so the StateManager/ledger receive a continuous
stream of cpu / memory / focused-process / terminals / network / clipboard state.

Scope note: this is the FOUNDATION sampler. Full B6 coverage (GPU telemetry, filesystem-change
watcher, richer network analysis) and the formal multi-rate tick scheduler (B5) are later
Phase-B milestones. All sampling is crash-proof and degrades silently if a dependency is absent.
"""
from __future__ import annotations

import threading
import time

from config.logger import get_logger

log = get_logger("state.os_sampler")

_TERMINAL_NAMES = {
    "cmd.exe", "powershell.exe", "pwsh.exe", "windowsterminal.exe",
    "wt.exe", "conhost.exe", "bash.exe", "git-bash.exe",
}


class OSSampler:
    def __init__(self, bus, interval: float = 2.0):
        self.bus = bus
        self.interval = max(0.5, float(interval))
        self._running = False
        self._thread = None
        self._last_clipboard_fp = None

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, name="os-sampler", daemon=True)
        self._thread.start()
        log.info("OSSampler started.")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)

    def sample_once(self) -> dict:
        """Collect a single OS snapshot dict (also usable directly in tests)."""
        snap: dict = {}
        try:
            import psutil
            snap["cpu"] = psutil.cpu_percent(interval=None)
            snap["memory"] = psutil.virtual_memory().percent
            try:
                batt = psutil.sensors_battery()
                snap["battery"] = batt.percent if batt else None
            except Exception:
                snap["battery"] = None
            terms = []
            for p in psutil.process_iter(["name"]):
                name = (p.info.get("name") or "").lower()
                if name in _TERMINAL_NAMES:
                    terms.append(name)
            snap["running_terminals"] = sorted(set(terms))
            try:
                n = psutil.net_io_counters()
                snap["network_summary"] = {
                    "sent_mb": round(n.bytes_sent / 1e6, 2),
                    "recv_mb": round(n.bytes_recv / 1e6, 2),
                }
            except Exception:
                snap["network_summary"] = {}
        except Exception as exc:
            log.debug(f"psutil sampling unavailable: {exc}")

        snap["focused_process"] = self._foreground_process()
        clip = self._clipboard_change()
        if clip is not None:
            snap["clipboard_change"] = clip
        return snap

    def _foreground_process(self):
        try:
            import ctypes
            import psutil
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            pid = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            return psutil.Process(pid.value).name()
        except Exception:
            return None

    def _clipboard_change(self):
        """Detect clipboard CHANGE only. Content is NOT stored (privacy guardrails) —
        we keep a fingerprint + length so we can record that it changed, not what it was."""
        try:
            import hashlib
            import pyperclip
            text = pyperclip.paste() or ""
            fp = hashlib.sha1(text.encode("utf-8", "ignore")).hexdigest()[:12]
            if fp != self._last_clipboard_fp:
                self._last_clipboard_fp = fp
                return {"changed": True, "length": len(text)}
            return None
        except Exception:
            return None

    def _loop(self):
        while self._running:
            try:
                snap = self.sample_once()
                self.bus.publish("perception.os.snapshot", snap, source="os_sampler")
            except Exception as exc:
                log.debug(f"OSSampler tick error: {exc}")
            time.sleep(self.interval)
