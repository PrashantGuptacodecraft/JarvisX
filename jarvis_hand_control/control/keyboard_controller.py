"""
control/keyboard_controller.py
Full keyboard action dispatcher using pynput.keyboard.Controller.
Every method catches all exceptions and logs without crashing.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

try:
    from pynput.keyboard import Controller as _KbCtrl, Key
    _kb     = _KbCtrl()
    _PYNPUT = True
except ImportError:
    _PYNPUT = False
    log.warning("pynput not installed — keyboard control disabled")

try:
    import pyautogui as _pag
    _PAG = True
except ImportError:
    _PAG = False

_SCREENSHOT_DIR = Path(__file__).resolve().parent.parent / "data" / "screenshots"
_SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


def _press(*keys) -> None:
    """Press a key combination then release in reverse order."""
    if not _PYNPUT:
        return
    try:
        for k in keys:
            _kb.press(k)
        for k in reversed(keys):
            _kb.release(k)
    except Exception as exc:
        log.debug("_press error: %s", exc)


def _tap(key) -> None:
    """Press and release a single key."""
    if not _PYNPUT:
        return
    try:
        _kb.press(key)
        _kb.release(key)
    except Exception as exc:
        log.debug("_tap error: %s", exc)


class KeyboardController:
    """
    High-level keyboard action controller.
    All methods are safe to call even if pynput is unavailable.
    """

    # ── Edit operations ───────────────────────────────────────────────────────

    def ctrl_s(self)    -> None: _press(Key.ctrl, 's')
    def ctrl_z(self)    -> None: _press(Key.ctrl, 'z')
    def ctrl_c(self)    -> None: _press(Key.ctrl, 'c')
    def ctrl_v(self)    -> None: _press(Key.ctrl, 'v')
    def ctrl_a(self)    -> None: _press(Key.ctrl, 'a')
    def ctrl_t(self)    -> None: _press(Key.ctrl, 't')
    def ctrl_w(self)    -> None: _press(Key.ctrl, 'w')
    def ctrl_tab(self)  -> None: _press(Key.ctrl, Key.tab)
    def ctrl_plus(self) -> None: _press(Key.ctrl, '+')
    def ctrl_minus(self)-> None: _press(Key.ctrl, '-')

    # ── Navigation ────────────────────────────────────────────────────────────

    def alt_left(self)  -> None: _press(Key.alt, Key.left)
    def alt_right(self) -> None: _press(Key.alt, Key.right)
    def alt_f4(self)    -> None: _press(Key.alt, Key.f4)

    # ── Special keys ─────────────────────────────────────────────────────────

    def delete_key(self) -> None: _tap(Key.delete)
    def enter_key(self)  -> None: _tap(Key.enter)
    def escape_key(self) -> None: _tap(Key.esc)
    def space_key(self)  -> None: _tap(Key.space)

    # ── Media keys ────────────────────────────────────────────────────────────

    def media_play_pause(self) -> None:
        _tap(Key.media_play_pause)

    def media_next(self) -> None:
        _tap(Key.media_next)

    def media_prev(self) -> None:
        _tap(Key.media_previous)

    def media_stop(self) -> None:
        _tap(Key.media_play_pause)   # press again to stop if playing
        time.sleep(0.05)
        _tap(Key.media_play_pause)

    # ── Volume ────────────────────────────────────────────────────────────────

    def volume_up(self, steps: int = 2) -> None:
        for _ in range(steps):
            _tap(Key.media_volume_up)
            time.sleep(0.03)

    def volume_down(self, steps: int = 2) -> None:
        for _ in range(steps):
            _tap(Key.media_volume_down)
            time.sleep(0.03)

    def volume_mute(self) -> None:
        _tap(Key.media_volume_mute)

    # ── Window management ─────────────────────────────────────────────────────

    def close_window(self)    -> None: _press(Key.alt, Key.f4)
    def maximize_window(self) -> None: _press(Key.cmd, Key.up)
    def minimize_window(self) -> None: _press(Key.cmd, Key.down)
    def switch_window(self)   -> None: _press(Key.alt, Key.tab)
    def new_desktop(self)     -> None: _press(Key.cmd, Key.ctrl, 'd')

    # ── Browser ───────────────────────────────────────────────────────────────

    def browser_back(self)    -> None: self.alt_left()
    def browser_forward(self) -> None: self.alt_right()
    def browser_refresh(self) -> None: _tap(Key.f5)
    def open_browser_search(self) -> None:
        _press(Key.ctrl, 't')
        time.sleep(0.15)

    # ── Application actions ───────────────────────────────────────────────────

    def open_file_under_cursor(self) -> None:
        _tap(Key.enter)

    def increase_window_size(self) -> None:
        _press(Key.cmd, Key.up)   # maximise

    def open_ai_chat(self) -> None:
        # Placeholder: open browser to AI chat URL
        import subprocess, sys
        try:
            if sys.platform == "win32":
                subprocess.Popen(["start", "https://chat.openai.com"], shell=True)
            else:
                subprocess.Popen(["xdg-open", "https://chat.openai.com"])
        except Exception as exc:
            log.debug("open_ai_chat: %s", exc)

    def zoom_in(self)  -> None: self.ctrl_plus()
    def zoom_out(self) -> None: self.ctrl_minus()

    def new_tab(self)  -> None: self.ctrl_t()
    def ctrl_f(self)   -> None: _press(Key.ctrl, 'f')

    # ── Screenshot ────────────────────────────────────────────────────────────

    def take_screenshot(self) -> Optional[str]:
        """Capture full screen and save to data/screenshots/."""
        if not _PAG:
            log.warning("pyautogui not available for screenshots")
            return None
        try:
            ts   = time.strftime("%Y%m%d_%H%M%S")
            path = str(_SCREENSHOT_DIR / f"screenshot_{ts}.png")
            _pag.screenshot(path)
            log.info("Screenshot saved: %s", path)
            return path
        except Exception as exc:
            log.error("Screenshot failed: %s", exc)
            return None

    # ── Text input ────────────────────────────────────────────────────────────

    def type_text(self, text: str) -> None:
        """Type a string character by character with a tiny delay."""
        if not _PYNPUT:
            return
        for char in text:
            try:
                _kb.type(char)
                time.sleep(0.02)
            except Exception as exc:
                log.debug("type_text char '%s': %s", char, exc)

    # ── Generic ───────────────────────────────────────────────────────────────

    def press(self, *keys) -> None:
        """Press an arbitrary key combination."""
        _press(*keys)

    def tap(self, key) -> None:
        """Press and release a single key."""
        _tap(key)
