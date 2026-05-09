"""
ui/ar_overlay.py
AROverlayEngine — composites AR effects and feeds a virtual camera.
Falls back gracefully if pyvirtualcam is unavailable or no backend found.
"""
from __future__ import annotations

import json
import logging
import time
from collections import deque
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from ui.ar_effects import (
    generate_circuit_pattern,
    scroll_circuit_pattern,
    draw_pulse_ring,
    draw_waveform_bars,
    apply_glow_effect,
    draw_name_badge,
    draw_scanning_line_overlay,
)

log = logging.getLogger(__name__)

_SETTINGS_FILE = Path(__file__).resolve().parent.parent / "config" / "ar_settings.json"

_RES_MAP = {
    "720p":  (1280, 720),
    "1080p": (1920, 1080),
    "480p":  (854,  480),
}


def _load_ar_settings() -> dict:
    try:
        with _SETTINGS_FILE.open(encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


class AROverlayEngine:
    """
    Applies AR overlays (circuit, pulse rings, waveform, glow, badge)
    and optionally streams to a virtual camera via pyvirtualcam.

    Call update() every frame. Call close() at shutdown.
    """

    def __init__(self, settings=None) -> None:
        self._settings    = settings
        self._ar_cfg      = _load_ar_settings()
        self._enabled     = self._ar_cfg.get("enabled", True)
        self._glow        = self._ar_cfg.get("glow_effects", True)
        self._badge       = self._ar_cfg.get("badge_visible", True)
        self._circuit_on  = self._ar_cfg.get("circuit_pattern_opacity", 0.15) > 0
        self._circuit_op  = float(self._ar_cfg.get("circuit_pattern_opacity", 0.15))
        self._pulse_on    = self._ar_cfg.get("pulse_ring_enabled", True)
        self._wave_on     = self._ar_cfg.get("waveform_bars_enabled", True)
        self._scan_on     = self._ar_cfg.get("scanning_line_enabled", True)
        self._bg_int      = self._ar_cfg.get("background_effects_intensity", 70) / 100.0
        self._fps_target  = int(self._ar_cfg.get("fps_target", 30))

        res_key = self._ar_cfg.get("resolution", "720p")
        self._out_w, self._out_h = _RES_MAP.get(res_key, (1280, 720))

        # Virtual camera
        self._vcam        = None
        self.backend_name = "none"
        self._init_virtual_camera()

        # Circuit pattern (generated once, scrolled each frame)
        self._circuit: Optional[np.ndarray] = None
        if self._circuit_on:
            self._circuit = generate_circuit_pattern(self._out_w, self._out_h)

        # Token bucket rate limiter
        self._tokens:      float = float(self._fps_target)
        self._last_refill: float = time.perf_counter()
        self._max_tokens:  float = float(self._fps_target)
        self._refill_rate: float = float(self._fps_target)   # per second

        # Frame timing / diagnostics
        self._last_frame_times: deque[float] = deque(maxlen=30)
        self._consecutive_drops: int  = 0
        self._last_fps_log:      float = 0.0
        self._frame_count:       int   = 0

        log.info("AROverlayEngine ready  backend=%s  out=%dx%d  fps_target=%d",
                 self.backend_name, self._out_w, self._out_h, self._fps_target)

    # ── Virtual camera init ───────────────────────────────────────────────────

    def _init_virtual_camera(self) -> None:
        """Try pyvirtualcam backends in preference order."""
        backend_pref = self._ar_cfg.get("virtual_camera_backend", "auto")
        candidates   = []

        if backend_pref == "auto":
            import sys
            if sys.platform == "win32":
                candidates = ["obs", "unitycapture", None]
            else:
                candidates = ["v4l2", None]
        elif backend_pref != "none":
            candidates = [backend_pref, None]
        else:
            return

        try:
            import pyvirtualcam
        except ImportError:
            log.warning("pyvirtualcam not installed — virtual camera disabled")
            return

        for backend in candidates:
            try:
                kwargs = dict(width=self._out_w, height=self._out_h,
                              fps=self._fps_target, delay=0)
                if backend is not None:
                    kwargs["backend"] = backend
                cam = pyvirtualcam.Camera(**kwargs)
                self._vcam        = cam
                self.backend_name = backend or "auto"
                log.info("Virtual camera opened: backend=%s", self.backend_name)
                return
            except Exception as exc:
                log.debug("pyvirtualcam backend '%s' failed: %s", backend, exc)

        log.warning("No virtual camera backend available — AR preview only")

    # ── Token bucket ──────────────────────────────────────────────────────────

    def _token_bucket_wait(self) -> None:
        """Refill tokens based on elapsed time, sleep if bucket empty."""
        now     = time.perf_counter()
        elapsed = now - self._last_refill
        self._tokens      = min(self._max_tokens, self._tokens + elapsed * self._refill_rate)
        self._last_refill = now

        if self._tokens < 1.0:
            wait = (1.0 - self._tokens) / self._refill_rate
            time.sleep(wait)
            self._tokens = 0.0
        else:
            self._tokens -= 1.0

    # ── Main update ───────────────────────────────────────────────────────────

    def update(
        self,
        frame:          np.ndarray,
        amplitude_data: Optional[np.ndarray]   = None,
        hand_positions: Optional[list[tuple]]  = None,
        active_gestures: Optional[list[str]]   = None,
        drawing_layer:  Optional[np.ndarray]   = None,
    ) -> None:
        """
        Composite AR effects and send to virtual camera.

        frame           : BGR frame from camera
        amplitude_data  : 1-D float array 0–1 for waveform (len >= 32)
        hand_positions  : list of (cx, cy) pixel positions for pulse rings
        active_gestures : list of current gesture names (unused currently)
        drawing_layer   : BGR array with air-drawing strokes (black background)
        """
        if not self._enabled:
            return

        self._token_bucket_wait()
        t_start = time.perf_counter()
        self._frame_count += 1

        # Work on a copy so HUD changes don't bleed to virtual cam
        out = frame.copy()
        h, w = out.shape[:2]

        # 1. Circuit pattern overlay
        if self._circuit_on and self._circuit is not None:
            scrolled = scroll_circuit_pattern(self._circuit, self._frame_count)
            # Resize circuit to match frame if needed
            if scrolled.shape[:2] != (h, w):
                scrolled = cv2.resize(scrolled, (w, h))
            cv2.addWeighted(
                scrolled, self._circuit_op * self._bg_int,
                out,      1.0,
                0, out
            )

        # 2. Pulse rings at each hand center
        if self._pulse_on and hand_positions:
            for cx, cy in hand_positions:
                out = draw_pulse_ring(out, (cx, cy), self._frame_count,
                                      color=(255, 255, 0), max_radius=60, duration=12)

        # 3. Waveform bars
        if self._wave_on and amplitude_data is not None and len(amplitude_data) > 0:
            amps = np.asarray(amplitude_data, dtype=np.float32)
            out  = draw_waveform_bars(out, amps, bar_count=32, max_height=60)

        # 4. Drawing glow + composite
        if drawing_layer is not None:
            if self._glow:
                out = apply_glow_effect(out, drawing_layer, blur_radius=15)
            else:
                mask = cv2.cvtColor(drawing_layer, cv2.COLOR_BGR2GRAY)
                _, mask = cv2.threshold(mask, 1, 255, cv2.THRESH_BINARY)
                out[mask > 0] = drawing_layer[mask > 0]

        # 5. Name badge
        if self._badge:
            out = draw_name_badge(out, "J.A.R.V.I.S", "bottom_right",
                                  self._frame_count)

        # 6. Scanning line
        if self._scan_on:
            out = draw_scanning_line_overlay(out, self._frame_count, speed=4)

        # 7. Resize to output resolution
        if (w, h) != (self._out_w, self._out_h):
            out = cv2.resize(out, (self._out_w, self._out_h))

        # 8. Send to virtual camera (RGB)
        if self._vcam is not None:
            try:
                rgb = cv2.cvtColor(out, cv2.COLOR_BGR2RGB)
                self._vcam.send(rgb)
            except Exception as exc:
                log.debug("vcam send error: %s", exc)

        # 9. FPS accounting
        t_end    = time.perf_counter()
        latency  = t_end - t_start
        expected = 1.0 / self._fps_target

        self._last_frame_times.append(latency)

        if latency > expected * 1.5:
            self._consecutive_drops += 1
        else:
            self._consecutive_drops = 0

        if self._consecutive_drops > 5:
            log.warning("AR overlay: %d consecutive late frames (%.1fms avg)",
                        self._consecutive_drops,
                        sum(self._last_frame_times) / len(self._last_frame_times) * 1000)
            self._consecutive_drops = 0

        now = time.time()
        if now - self._last_fps_log > 10.0:
            if self._last_frame_times:
                avg_ms  = sum(self._last_frame_times) / len(self._last_frame_times) * 1000
                live_fps = 1000.0 / max(avg_ms, 1)
                log.info("AR overlay FPS: %.1f  avg_latency: %.1fms", live_fps, avg_ms)
            self._last_fps_log = now

    # ── Cleanup ───────────────────────────────────────────────────────────────

    def close(self) -> None:
        """Release virtual camera and log final statistics."""
        if self._vcam is not None:
            try:
                self._vcam.close()
            except Exception as exc:
                log.debug("vcam close: %s", exc)

        if self._last_frame_times:
            avg_ms  = sum(self._last_frame_times) / len(self._last_frame_times) * 1000
            log.info("AROverlayEngine closed — frames: %d  avg_latency: %.1fms  backend: %s",
                     self._frame_count, avg_ms, self.backend_name)
        else:
            log.info("AROverlayEngine closed — no frames processed  backend: %s",
                     self.backend_name)
