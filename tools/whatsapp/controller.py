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
from pathlib import Path

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

    def _phone_candidates(self, phone: str) -> list[str]:
        digits = "".join(ch for ch in (phone or "") if ch.isdigit())
        if not digits:
            return []

        candidates = []
        for candidate in (
            digits,
            f"91{digits}" if len(digits) == 10 else "",
            f"91{digits[1:]}" if len(digits) == 11 and digits.startswith("0") else "",
        ):
            clean = candidate.strip()
            if clean and clean not in candidates:
                candidates.append(clean)
        return candidates

    @staticmethod
    def _normalize_label(text: str) -> str:
        cleaned = "".join(ch.lower() if ch.isalnum() or ch.isspace() else " " for ch in (text or ""))
        return " ".join(cleaned.split())

    def _title_matches_contact(self, title: str, contact: str) -> bool:
        title_norm = self._normalize_label(title)
        contact_norm = self._normalize_label(contact)
        if not title_norm or not contact_norm:
            return False
        if title_norm == contact_norm or contact_norm in title_norm:
            return True

        contact_tokens = [token for token in contact_norm.split() if len(token) > 2]
        if not contact_tokens:
            return False
        matches = sum(1 for token in contact_tokens if token in title_norm)
        return matches >= max(1, len(contact_tokens) - 1)

    def _contact_search_queries(self, contact: str, phone: str = "") -> list[str]:
        queries = []
        normalized = " ".join((contact or "").split())
        if normalized:
            queries.append(normalized)
            parts = normalized.split()
            if len(parts) > 1:
                queries.append(" ".join(parts[:2]))
            if parts:
                queries.append(parts[0])
        queries.extend(self._phone_candidates(phone))

        deduped = []
        for item in queries:
            clean = item.strip()
            if clean and clean not in deduped:
                deduped.append(clean)
        return deduped

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

        contact_clean = contact.lower().strip()
        phone = self._lookup_saved_phone(contact_clean)
        try:
            import pyautogui  # noqa: F401
            import pyperclip  # noqa: F401
            threading.Thread(
                target=self._open_chat_for_call,
                args=(contact, phone, video),
                daemon=True,
            ).start()
            kind = "video call" if video else "call"
            if phone:
                return f"Opening WhatsApp Desktop and trying to start a {kind} with {contact} from your saved contact, {USER_NAME}."
            return f"Opening WhatsApp Desktop and trying to start a {kind} with {contact}, {USER_NAME}."
        except ImportError:
            if not self._open_desktop_app():
                webbrowser.open("https://web.whatsapp.com")
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

        phone = self._lookup_saved_phone(contact.lower().strip())
        if not self._open_contact_chat(contact, phone):
            log.warning("Could not open WhatsApp Desktop - falling back to web automation")
            self._send_via_web_search(contact, message)
            return

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

    def _open_desktop_link(self, phone: str, encoded_message: str = "") -> bool:
        if not IS_WIN:
            return False
        suffix = f"&text={encoded_message}" if encoded_message else ""
        for candidate in self._phone_candidates(phone):
            targets = [
                f"whatsapp://send?phone={candidate}{suffix}",
                f"whatsapp://send?abid={candidate}{suffix}",
            ]
            for target in targets:
                try:
                    subprocess.Popen(
                        ["cmd", "/c", "start", "", target],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    log.info(f"WhatsApp deep link launched for {candidate}")
                    return True
                except Exception as e:
                    log.warning(f"Desktop deep link failed for {candidate}: {e}")
        return False

    def _open_contact_chat(self, contact: str, phone: str = "") -> bool:
        try:
            import pyautogui
            import pyperclip
        except Exception:
            return False

        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.3

        if phone and self._open_desktop_link(phone):
            if self._focus_whatsapp_window(wait_seconds=12):
                time.sleep(3.0)
                if self._current_chat_matches(contact):
                    log.info(f"WhatsApp deep link confirmed chat for {contact}")
                    return True
                log.warning(f"WhatsApp deep link did not land on {contact}; falling back to search")
            log.warning("Saved-contact deep link opened but WhatsApp could not be focused")

        if not self._open_desktop_app():
            return False
        if not self._focus_whatsapp_window(wait_seconds=12):
            return False

        return self._open_chat_via_search(contact, phone=phone)

    def _chat_search_point(self, win) -> tuple[int, int]:
        x = win.left + int(win.width * 0.23)
        y = win.top + int(win.height * 0.18)
        return x, y

    def _first_search_result_point(self, win) -> tuple[int, int]:
        x = win.left + int(win.width * 0.21)
        y = win.top + int(win.height * 0.36)
        return x, y

    def _open_chat_via_search(self, contact: str, phone: str = "") -> bool:
        import pyautogui
        import pyperclip

        win = self._get_whatsapp_window() or self._get_active_window()
        if not win:
            return False

        try:
            queries = self._contact_search_queries(contact, phone=phone)
            if not queries:
                return False

            search_x, search_y = self._chat_search_point(win)
            result_x, result_y = self._first_search_result_point(win)
            for query in queries:
                pyautogui.press("esc")
                time.sleep(0.15)
                pyautogui.click(search_x, search_y)
                time.sleep(0.25)
                pyautogui.hotkey("ctrl", "a")
                time.sleep(0.1)
                pyautogui.press("backspace")
                time.sleep(0.1)
                pyautogui.write(query, interval=0.04)
                time.sleep(0.9)
                pyautogui.press("down")
                time.sleep(0.15)
                pyautogui.press("enter")
                time.sleep(1.0)
                if self._current_chat_matches(contact):
                    log.info(f"Opened WhatsApp chat via keyboard search for {contact} using query '{query}'")
                    return True
                if self._header_has_call_controls():
                    log.info(f"Assuming WhatsApp chat is open for {contact} after keyboard search '{query}'")
                    return True

                # Fallback to clipboard paste for cases where direct typing is blocked.
                pyautogui.click(search_x, search_y)
                time.sleep(0.2)
                pyautogui.hotkey("ctrl", "a")
                pyautogui.press("backspace")
                pyperclip.copy(query)
                pyautogui.hotkey("ctrl", "v")
                time.sleep(0.9)
                pyautogui.click(result_x, result_y)
                time.sleep(1.0)
                if self._current_chat_matches(contact):
                    log.info(f"Opened WhatsApp chat via paste search for {contact} using query '{query}'")
                    return True
                if self._header_has_call_controls():
                    log.info(f"Assuming WhatsApp chat is open for {contact} after result click for '{query}'")
                    return True

            log.warning(f"WhatsApp search could not confirm the chat for {contact}")
            return False
        except Exception as e:
            log.warning(f"Could not open chat for {contact}: {e}")
            return False

    def _read_current_chat_title(self) -> str:
        desktop = self._pywinauto_desktop()
        win = self._get_whatsapp_window() or self._get_active_window()
        if not desktop or not win:
            return ""

        anchor_x = win.left + int(win.width * 0.56)
        anchor_y = win.top + min(118, max(84, int(win.height * 0.09)))

        try:
            root = desktop.from_point(anchor_x, anchor_y)
        except Exception:
            return ""

        try:
            current = root
            best = root
            for _ in range(8):
                parent = current.parent()
                if not parent:
                    break
                rect = parent.rectangle()
                width = rect.right - rect.left
                height = rect.bottom - rect.top
                if width > max(win.width * 1.35, win.width + 260):
                    break
                if height > max(win.height * 1.35, win.height + 260):
                    break
                best = parent
                current = parent

            header_top = win.top + 35
            header_bottom = win.top + min(160, max(96, int(win.height * 0.15)))
            title_candidates = []
            for item in best.descendants():
                control_type = getattr(item.element_info, "control_type", "")
                if control_type != "Text":
                    continue
                rect = item.rectangle()
                center_y = (rect.top + rect.bottom) // 2
                center_x = (rect.left + rect.right) // 2
                if center_x < win.left + int(win.width * 0.44):
                    continue
                if center_y < header_top or center_y > header_bottom:
                    continue
                text = (item.window_text() or getattr(item.element_info, "name", "") or "").strip()
                if not text:
                    continue
                title_candidates.append((rect.top, len(text), text))

            if not title_candidates:
                return ""

            title_candidates.sort(key=lambda row: (row[0], -row[1]))
            for _, _, text in title_candidates:
                if "message yourself" in text.lower():
                    continue
                return text
        except Exception:
            return ""
        return ""

    def _current_chat_matches(self, contact: str) -> bool:
        title = self._read_current_chat_title()
        if title:
            log.info("WhatsApp current chat title: %s", title)
        return self._title_matches_contact(title, contact)

    def _get_whatsapp_window(self):
        wins = self._list_whatsapp_windows()
        if not wins:
            return None

        visible = [
            win for win in wins
            if getattr(win, "width", 0) >= 320 and getattr(win, "height", 0) >= 500
        ]
        pool = visible or wins
        return max(pool, key=lambda win: getattr(win, "width", 0) * getattr(win, "height", 0))

    def _get_active_window(self):
        try:
            import pygetwindow as gw
        except Exception:
            return None

        try:
            win = gw.getActiveWindow()
        except Exception:
            return None

        if not win:
            return None
        if getattr(win, "width", 0) < 320 or getattr(win, "height", 0) < 500:
            return None
        return win

    def _list_whatsapp_windows(self) -> list:
        try:
            import pygetwindow as gw
        except Exception:
            return []

        wins = []
        for title in WINDOW_TITLES:
            wins.extend(gw.getWindowsWithTitle(title))
        return wins

    def _focus_whatsapp_window(self, wait_seconds: int = 10) -> bool:
        deadline = time.time() + wait_seconds
        while time.time() < deadline:
            win = self._get_whatsapp_window() or self._get_active_window()
            if win:
                try:
                    if getattr(win, "isMinimized", False):
                        win.restore()
                        time.sleep(0.5)
                    win.activate()
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

    def _header_anchor_point(self, win) -> tuple[int, int]:
        x = win.left + int(win.width * 0.84)
        y = win.top + min(132, max(92, int(win.height * 0.105)))
        return x, y

    def _header_call_points(self, win) -> tuple[tuple[int, int], tuple[int, int]]:
        y = win.top + min(132, max(92, int(win.height * 0.105)))
        main_x = win.left + int(win.width * 0.825)
        menu_x = win.left + int(win.width * 0.858)
        return (main_x, y), (menu_x, y)

    def _header_has_call_controls(self) -> bool:
        win = self._get_whatsapp_window() or self._get_active_window()
        if not win:
            return False
        title = self._read_current_chat_title()
        if title and "message yourself" in title.lower():
            return False
        return win.width > 1100

    def _start_call_from_header(self, video: bool = False) -> bool:
        try:
            import pyautogui
        except Exception:
            return False

        win = self._get_whatsapp_window() or self._get_active_window()
        if not win:
            return False

        main_point, menu_point = self._header_call_points(win)
        try:
            if video:
                pyautogui.click(*main_point)
                time.sleep(0.4)
                log.info("Used primary WhatsApp header button for video call")
                return True

            pyautogui.click(*menu_point)
            time.sleep(0.3)
            pyautogui.press("enter")
            time.sleep(0.3)
            log.info("Used WhatsApp header menu for voice call")
            return True
        except Exception as e:
            log.warning(f"Could not use the WhatsApp header call control: {e}")
            return False

    def _open_chat_for_call(self, contact: str, phone: str, video: bool) -> None:
        import pyautogui

        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.3

        if not self._open_contact_chat(contact, phone):
            webbrowser.open("https://web.whatsapp.com")
            return
        try:
            pyautogui.press("esc")
            time.sleep(0.2)
        except Exception:
            pass
        if self._start_call_from_header(video=video):
            log.info(f"Activated {'video ' if video else ''}call from header controls for {contact}")
            return
        if self._click_call_button(video=video):
            log.info(f"Activated {'video ' if video else ''}call button for {contact} via UI automation")
            return
        log.warning(f"Could not resolve a direct call button for {contact}; trying keyboard shortcut")
        if self._start_call_via_shortcut(contact, video=video):
            log.info(f"Confirmed {'video ' if video else ''}call shortcut for {contact}")
            return
        log.warning(f"WhatsApp call automation ran out of safe fallbacks for {contact}")

    def _start_call_via_shortcut(self, contact: str, video: bool = False) -> bool:
        try:
            import pyautogui
            import pygetwindow as gw
        except Exception:
            return False

        win = self._get_whatsapp_window() or self._get_active_window()
        if not win:
            return False

        try:
            if getattr(win, "isMinimized", False):
                win.restore()
                time.sleep(0.5)
            win.activate()
        except Exception:
            pass

        before_count = len(self._list_whatsapp_windows())
        before_title = gw.getActiveWindowTitle() or ""
        shortcut = ("ctrl", "shift", "v") if video else ("ctrl", "shift", "c")

        try:
            header_x, header_y = self._header_anchor_point(win)
            pyautogui.click(header_x, header_y)
            time.sleep(0.25)
            pyautogui.hotkey(*shortcut)
            log.info(
                "Sent WhatsApp %s call shortcut: %s",
                "video" if video else "voice",
                "+".join(key.upper() for key in shortcut),
            )
        except Exception as e:
            log.warning(f"Could not send the call shortcut: {e}")
            return False

        deadline = time.time() + 3
        while time.time() < deadline:
            wins = self._list_whatsapp_windows()
            if len(wins) > before_count:
                return True
            active_title = gw.getActiveWindowTitle() or ""
            if active_title and active_title != before_title:
                lower_title = active_title.lower()
                if "whatsapp" in lower_title or contact.lower() in lower_title:
                    return True
            time.sleep(0.25)
        return False

    def _pywinauto_desktop(self):
        try:
            import comtypes
            import types
        except Exception as e:
            log.warning(f"UI automation prerequisites are unavailable: {e}")
            return None

        try:
            gen_dir = Path(__file__).resolve().parents[2] / ".runtime" / "comtypes_gen"
            gen_dir.mkdir(parents=True, exist_ok=True)

            gen_module = types.ModuleType("comtypes.gen")
            gen_module.__path__ = [str(gen_dir)]
            sys.modules["comtypes.gen"] = gen_module
            comtypes.gen = gen_module

            from pywinauto import Desktop

            return Desktop(backend="uia")
        except Exception as e:
            log.warning(f"UI automation backend could not start: {e}")
            return None

    def _button_signature(self, button) -> tuple:
        rect = button.rectangle()
        name = (button.window_text() or getattr(button.element_info, "name", "") or "").strip()
        return (rect.left, rect.top, rect.right, rect.bottom, name)

    def _click_call_button(self, video: bool = False) -> bool:
        desktop = self._pywinauto_desktop()
        win = self._get_whatsapp_window() or self._get_active_window()
        if not desktop or not win:
            return False

        try:
            if getattr(win, "isMinimized", False):
                win.restore()
                time.sleep(0.5)
            win.activate()
        except Exception:
            pass

        time.sleep(0.8)
        anchor_x, anchor_y = self._header_anchor_point(win)

        try:
            root = desktop.from_point(anchor_x, anchor_y)
        except Exception as e:
            log.warning(f"Could not locate the active WhatsApp element: {e}")
            return False

        try:
            current = root
            best = root
            for _ in range(8):
                parent = current.parent()
                if not parent:
                    break
                rect = parent.rectangle()
                width = rect.right - rect.left
                height = rect.bottom - rect.top
                if width > max(win.width * 1.35, win.width + 260):
                    break
                if height > max(win.height * 1.35, win.height + 260):
                    break
                best = parent
                current = parent
            buttons = [
                item for item in best.descendants()
                if getattr(item.element_info, "control_type", "") == "Button"
            ]
        except Exception as e:
            log.warning(f"Could not inspect WhatsApp controls: {e}")
            return False

        header_limit = win.top + min(170, max(70, int(win.height * 0.18)))
        header_buttons = []
        seen = set()
        for button in buttons:
            try:
                rect = button.rectangle()
                center_x = (rect.left + rect.right) // 2
                center_y = (rect.top + rect.bottom) // 2
                if center_x < win.left + int(win.width * 0.55):
                    continue
                if center_y < win.top + 40 or center_y > header_limit:
                    continue
                signature = self._button_signature(button)
                if signature in seen:
                    continue
                seen.add(signature)
                header_buttons.append(button)
            except Exception:
                continue

        if not header_buttons:
            return False

        def button_name(button) -> str:
            return (button.window_text() or getattr(button.element_info, "name", "") or "").strip()

        debug_buttons = []
        for button in sorted(header_buttons, key=lambda item: item.rectangle().left):
            rect = button.rectangle()
            debug_buttons.append(f"{button_name(button) or '<icon>'}@{rect.left},{rect.top}")
        log.info("WhatsApp header buttons: %s", " | ".join(debug_buttons[:8]))

        keywords = ("video", "camera") if video else ("voice", "call", "phone")
        blocked = ("search", "menu", "more", "close", "minimize", "maximize")

        for button in header_buttons:
            name = button_name(button).lower()
            if name and any(word in name for word in keywords) and not any(word in name for word in blocked):
                try:
                    button.click_input()
                    return True
                except Exception as e:
                    log.warning(f"Could not click the named WhatsApp call button '{button_name(button)}': {e}")

        action_buttons = []
        for button in header_buttons:
            name = button_name(button).lower()
            if any(word in name for word in blocked):
                continue
            action_buttons.append(button)

        if 2 <= len(action_buttons) <= 3:
            ordered = sorted(action_buttons, key=lambda item: item.rectangle().left)
            choice = ordered[min(1, len(ordered) - 1)] if video else ordered[0]
            try:
                log.info("Using WhatsApp header button fallback: %s", button_name(choice) or "<icon>")
                choice.click_input()
                return True
            except Exception as e:
                log.warning(f"Could not click the fallback WhatsApp call button: {e}")

        try:
            import pyautogui
        except Exception:
            return False

        main_point, menu_point = self._header_call_points(win)
        try:
            if video:
                pyautogui.click(*main_point)
                log.info("Used coordinate fallback for WhatsApp video call button")
                return True

            pyautogui.click(*menu_point)
            time.sleep(0.35)
            pyautogui.press("down")
            time.sleep(0.15)
            pyautogui.press("enter")
            log.info("Used coordinate fallback for WhatsApp voice call menu")
            return True
        except Exception as e:
            log.warning(f"Could not use the coordinate fallback for WhatsApp call controls: {e}")

        return False
