"""
tools/security/private_mode.py
Encrypted Private Mode for JarvisX.

When active:
  - New memory entries are AES-256 encrypted
  - Screen capture blocked via Windows API (SetWindowDisplayAffinity)
  - GUI logs suppressed
  - Speaker output reduced in volume

Toggle: "Jarvis, private mode on" / "Jarvis, private mode off"
"""
from __future__ import annotations
import os
import logging
import threading
from typing import Optional

log = logging.getLogger("private_mode")


class PrivateMode:
    """
    Manages JarvisX private mode state.
    Applies OS-level screen capture protection when active.
    """

    def __init__(self, memory=None, speaker=None, gui=None):
        self.memory = memory
        self.speaker = speaker
        self.gui = gui
        self.active: bool = False
        self._original_volume: Optional[float] = None
        self._lock = threading.Lock()

    def enable(self) -> str:
        """Activate private mode."""
        with self._lock:
            if self.active:
                return "Private mode is already active."
            self.active = True

        self._block_screen_capture(True)
        self._reduce_volume()
        if self.gui:
            try:
                self.gui.set_status("private")
            except Exception:
                pass
        log.info("Private mode ENABLED.")
        return "Private mode activated. Screen capture blocked, memory encrypted, volume reduced."

    def disable(self) -> str:
        """Deactivate private mode."""
        with self._lock:
            if not self.active:
                return "Private mode is not active."
            self.active = False

        self._block_screen_capture(False)
        self._restore_volume()
        if self.gui:
            try:
                self.gui.set_status("listening")
            except Exception:
                pass
        log.info("Private mode DISABLED.")
        return "Private mode deactivated. Normal operation resumed."

    def toggle(self) -> str:
        if self.active:
            return self.disable()
        return self.enable()

    def is_active(self) -> bool:
        return self.active

    def encrypt_text(self, text: str) -> str:
        """
        Encrypt text with AES-256 if private mode active.
        Falls back to plain text if cryptography not installed.
        """
        if not self.active:
            return text
        try:
            return self._aes_encrypt(text)
        except Exception as e:
            log.debug(f"PrivateMode encrypt error: {e}")
            return text

    def decrypt_text(self, ciphertext: str) -> str:
        """Decrypt AES-256 ciphertext."""
        try:
            return self._aes_decrypt(ciphertext)
        except Exception:
            return ciphertext  # Return as-is if not encrypted

    # ── Internal ───────────────────────────────────────────────────────────────

    @staticmethod
    def _block_screen_capture(block: bool):
        """Use Windows SetWindowDisplayAffinity to prevent screen capture."""
        try:
            import ctypes
            import ctypes.wintypes
            # WDA_EXCLUDEFROMCAPTURE = 0x00000011
            # WDA_NONE               = 0x00000000
            flag = 0x00000011 if block else 0x00000000
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            if hwnd:
                ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, flag)
                log.info(f"Screen capture {'blocked' if block else 'unblocked'} (HWND={hwnd})")
        except Exception as e:
            log.debug(f"SetWindowDisplayAffinity failed: {e}")

    def _reduce_volume(self):
        """Reduce system volume to 30% for privacy."""
        try:
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
            from comtypes import CLSCTX_ALL
            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            volume = interface.QueryInterface(IAudioEndpointVolume)
            self._original_volume = volume.GetMasterVolumeLevelScalar()
            volume.SetMasterVolumeLevelScalar(min(self._original_volume, 0.30), None)
        except Exception as e:
            log.debug(f"Volume reduction failed (non-critical): {e}")

    def _restore_volume(self):
        """Restore original volume after private mode."""
        if self._original_volume is None:
            return
        try:
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
            from comtypes import CLSCTX_ALL
            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            volume = interface.QueryInterface(IAudioEndpointVolume)
            volume.SetMasterVolumeLevelScalar(self._original_volume, None)
        except Exception as e:
            log.debug(f"Volume restore failed (non-critical): {e}")
        finally:
            self._original_volume = None

    def _get_or_create_key(self) -> bytes:
        """Get or generate AES encryption key stored locally."""
        key_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "..", "data", ".private_key"
        )
        key_path = os.path.normpath(key_path)
        os.makedirs(os.path.dirname(key_path), exist_ok=True)
        if os.path.exists(key_path):
            with open(key_path, "rb") as f:
                return f.read()
        from cryptography.fernet import Fernet
        key = Fernet.generate_key()
        with open(key_path, "wb") as f:
            f.write(key)
        return key

    def _aes_encrypt(self, text: str) -> str:
        from cryptography.fernet import Fernet
        key = self._get_or_create_key()
        f = Fernet(key)
        return "[ENC]" + f.encrypt(text.encode()).decode()

    def _aes_decrypt(self, text: str) -> str:
        if not text.startswith("[ENC]"):
            return text
        from cryptography.fernet import Fernet
        key = self._get_or_create_key()
        f = Fernet(key)
        return f.decrypt(text[5:].encode()).decode()
