"""
tools/whatsapp/controller.py
Prefer WhatsApp Desktop first, then fall back to WhatsApp Web if needed.
"""

import subprocess
import sys
import threading
import time
import urllib.parse
import webbrowser

from config.logger import get_logger
from config.settings import USER_NAME

log = get_logger("whatsapp")
IS_WIN = sys.platform == "win32"

# Add your contacts here: "name": "country_code+number"
CONTACT_NUMBERS = {
    # "rahul": "919876543210",
    # "abhishek tripathi": "91XXXXXXXXXX",
}

WINDOW_TITLES = ["WhatsApp", "WhatsApp Beta"]


class WhatsAppController:
    def __init__(self, memory=None):
        self._whatsapp_ready = False
        self.memory = memory

    def _lookup_saved_phone(self, contact: str) -> str:
        contact_clean = (contact or "").lower().strip()
        if self.memory:
            phone = self.memory.get_contact_phone(contact_clean, channel="whatsapp")
            if phone:
                return phone
        return CONTACT_NUMBERS.get(contact_clean, "")

    def send_message(self, contact: str, message: str) -> str:
        if not contact or not message:
            return f"Please provide both a contact name and a message, {USER_NAME}."

        contact_clean = contact.lower().strip()
        log.info(f"WhatsApp desktop preferred -> {contact}: {message}")

        phone = self._lookup_saved_phone(contact_clean)
        if phone:
            threading.Thread(
                target=self._send_via_desktop_link,
                args=(phone, message, contact),
                daemon=True,
            ).start()
            return f"Sending WhatsApp message to {contact} in the desktop app, {USER_NAME}."

        try:
            import pyautogui  # noqa: F401
            import pyperclip  # noqa: F401
            threading.Thread(
                target=self._send_via_desktop_search,
                args=(contact, message),
                daemon=True,
            ).start()
            return f"Opening WhatsApp Desktop and sending the message to {contact}, {USER_NAME}."
        except ImportError:
            log.warning("Desktop automation packages unavailable - using clipboard fallback")
            return self._send_via_clipboard(contact, message)

    def start_call(self, contact: str, video: bool = False) -> str:
        if not contact:
            return f"Please tell me who to call, {USER_NAME}."

        try:
            import pyautogui  # noqa: F401
            import pyperclip  # noqa: F401
            threading.Thread(
                target=self._open_chat_for_call,
                args=(contact, video),
                daemon=True,
            ).start()
            kind = "video call" if video else "call"
            return f"Opening WhatsApp Desktop and preparing a {kind} with {contact}, {USER_NAME}."
        except ImportError:
            return (
                f"WhatsApp opened, {USER_NAME}. "
                f"I couldn't automate the {'video call' if video else 'call'} buttons on this setup, "
                f"but I'll open the app so you can start it for {contact}."
            )

    def _send_via_desktop_link(self, phone: str, message: str, contact: str) -> None:
        encoded = urllib.parse.quote(message)
        if self._open_desktop_link(phone, encoded):
            if self._focus_whatsapp_window(wait_seconds=8):
                self._press_enter_after_delay(1)
                log.info(f"Sent desktop deep-link message to {contact}")
                return

        log.warning("Desktop deep link failed - falling back to WhatsApp Web link")
        self._send_via_web_link(phone, message, contact)

    def _send_via_desktop_search(self, contact: str, message: str) -> None:
        import pyautogui
        import pyperclip

        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.3

        opened = self._open_desktop_app()
        if not opened:
            log.warning("Could not open WhatsApp Desktop - falling back to web automation")
            self._send_via_web_search(contact, message)
            return

        if not self._focus_whatsapp_window(wait_seconds=12):
            log.warning("WhatsApp Desktop window not found - falling back to web automation")
            self._send_via_web_search(contact, message)
            return

        pyautogui.hotkey("ctrl", "f")
        time.sleep(1.0)
        pyperclip.copy(contact)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(2.0)
        pyautogui.press("enter")
        time.sleep(1.2)

        pyperclip.copy(message)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.5)
        pyautogui.press("enter")
        log.info(f"Desktop message sent to {contact}")

    def _send_via_clipboard(self, contact: str, message: str) -> str:
        try:
            self._open_desktop_app()
            import pyperclip

            pyperclip.copy(message)
            return (
                f"WhatsApp Desktop opened, {USER_NAME}. "
                f"Message copied to clipboard. Open '{contact}' and press Ctrl+V, then Enter."
            )
        except Exception:
            webbrowser.open("https://web.whatsapp.com")
            return (
                f"WhatsApp opened, {USER_NAME}. "
                f"Please find '{contact}' and send: '{message}'"
            )

    def add_contact(self, name: str, phone: str) -> str:
        if self.memory:
            ok, result = self.memory.save_contact(name, phone, channel="whatsapp")
            if ok:
                return f"WhatsApp contact saved: {name} -> +{result}, {USER_NAME}."
            return f"I couldn't save that contact, {USER_NAME}. {result}"

        CONTACT_NUMBERS[name.lower()] = "".join(ch for ch in phone if ch.isdigit())
        return f"Contact saved for this session: {name} -> {phone}, {USER_NAME}."

    def open_whatsapp(self) -> str:
        if self._open_desktop_app():
            if self._focus_whatsapp_window(wait_seconds=8):
                return f"Opening WhatsApp Desktop, {USER_NAME}."
            log.warning("WhatsApp Desktop did not appear - falling back to WhatsApp Web")
        webbrowser.open("https://web.whatsapp.com")
        return f"Opening WhatsApp Web, {USER_NAME}."

    def list_contacts(self) -> str:
        saved = []
        if self.memory:
            saved = self.memory.list_contacts(channel="whatsapp")
        merged = {item["name"]: item["phone"] for item in saved}
        for name, num in CONTACT_NUMBERS.items():
            merged.setdefault(name, num)

        if not merged:
            return (
                f"No contacts saved yet, {USER_NAME}. "
                f"Say 'add whatsapp contact Abhishek Tripathi 91XXXXXXXXXX' to save one."
            )
        lines = "\n".join(f"  - {name.title()}: +{num}" for name, num in sorted(merged.items()))
        return f"Saved WhatsApp contacts:\n{lines}"

    def _open_desktop_app(self) -> bool:
        if not IS_WIN:
            return False

        candidates = [
            ["cmd", "/c", "start", "", "whatsapp:"],
            ["cmd", "/c", "start", "", "shell:AppsFolder\\5319275A.WhatsAppDesktop_cv1g1gvanyjgm!App"],
        ]
        for cmd in candidates:
            try:
                subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return True
            except Exception as e:
                log.warning(f"Desktop launch attempt failed: {e}")
        return False

    def _open_desktop_link(self, phone: str, encoded_message: str) -> bool:
        if not IS_WIN:
            return False
        candidates = [
            f"whatsapp://send?phone={phone}&text={encoded_message}",
            f"whatsapp://send?abid={phone}&text={encoded_message}",
        ]
        for target in candidates:
            try:
                subprocess.Popen(
                    ["cmd", "/c", "start", "", target],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return True
            except Exception as e:
                log.warning(f"Desktop deep link failed: {e}")
        return False

    def _focus_whatsapp_window(self, wait_seconds: int = 10) -> bool:
        try:
            import pygetwindow as gw
        except Exception:
            return False

        deadline = time.time() + wait_seconds
        while time.time() < deadline:
            for title in WINDOW_TITLES:
                wins = gw.getWindowsWithTitle(title)
                if wins:
                    try:
                        wins[0].activate()
                        time.sleep(0.8)
                        return True
                    except Exception:
                        pass
            time.sleep(0.5)
        return False

    def _press_enter_after_delay(self, seconds: int) -> None:
        try:
            import pyautogui

            time.sleep(seconds)
            self._focus_whatsapp_window(wait_seconds=5)
            pyautogui.press("enter")
        except Exception as e:
            log.warning(f"Could not auto-confirm desktop send: {e}")

    def _send_via_web_link(self, phone: str, message: str, contact: str) -> None:
        encoded = urllib.parse.quote(message)
        webbrowser.open(f"https://wa.me/{phone}?text={encoded}")
        self._press_enter_after_delay(6)
        log.info(f"Web link fallback used for {contact}")

    def _send_via_web_search(self, contact: str, message: str) -> None:
        import pyautogui
        import pyperclip

        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.3

        webbrowser.open("https://web.whatsapp.com")
        time.sleep(8)
        self._focus_whatsapp_window(wait_seconds=8)
        pyautogui.hotkey("ctrl", "alt", "n")
        time.sleep(1.5)
        pyperclip.copy(contact)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(2.5)
        pyautogui.press("enter")
        time.sleep(1.5)
        pyperclip.copy(message)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.8)
        pyautogui.press("enter")
        log.info(f"Web fallback message sent to {contact}")

    def _open_chat_for_call(self, contact: str, video: bool) -> None:
        import pyautogui
        import pyperclip

        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.3

        opened = self._open_desktop_app()
        if not opened:
            webbrowser.open("https://web.whatsapp.com")
            return

        if not self._focus_whatsapp_window(wait_seconds=12):
            webbrowser.open("https://web.whatsapp.com")
            return

        pyautogui.hotkey("ctrl", "f")
        time.sleep(1.0)
        pyperclip.copy(contact)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(2.0)
        pyautogui.press("enter")
        time.sleep(1.5)

        # Best-effort keyboard navigation to the call buttons in desktop UI.
        pyautogui.press("tab", presses=6, interval=0.15)
        if video:
            pyautogui.press("right")
        pyautogui.press("enter")
        log.info(f"Prepared {'video ' if video else ''}call for {contact}")
