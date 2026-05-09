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
CALL_BUTTON_AVOID_REGIONS = [
    (0.72, 0.00, 1.00, 0.18),
]

# ── SafeWhatsAppSender constants ──────────────────────────────────────────────
SAFE_CLICK_DELAY    = 0.5    # seconds between automation actions
WHATSAPP_LOAD_WAIT  = 3.0    # seconds to wait after opening WhatsApp
MAX_RETRY_ATTEMPTS  = 3      # max retries for safe_send_message
SEARCH_RESULT_WAIT  = 2.5    # allow filtered search rows time to render
SEARCH_RESULT_POLL  = 0.25   # check interval while waiting for search rows


class SafeWhatsAppSender:
    """
    Safe WhatsApp message sender that avoids accidentally triggering calls.

    Uses pyautogui + pygetwindow (already in requirements.txt).
    Works alongside the existing WhatsAppController — call safe_send_message()
    and it will fall back to pywhatkit web method on any failure.
    """

    def __init__(self, controller=None):
        self._controller = controller
        self._log = get_logger("whatsapp.safe")

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _get_wa_window(self):
        """Return the largest visible WhatsApp window, or None."""
        if self._controller:
            return self._controller._get_whatsapp_window() or self._controller._get_active_window()
        try:
            import pygetwindow as gw
        except ImportError:
            return None
        wins = []
        for title in WINDOW_TITLES:
            wins.extend(gw.getWindowsWithTitle(title))
        visible = [w for w in wins if getattr(w, "width", 0) >= 320 and getattr(w, "height", 0) >= 500]
        if not visible:
            return None
        return max(visible, key=lambda w: w.width * w.height)

    def _point_is_safe(self, win, point: tuple[int, int]) -> bool:
        x, y = point
        for x0, y0, x1, y1 in CALL_BUTTON_AVOID_REGIONS:
            left = win.left + int(win.width * x0)
            top = win.top + int(win.height * y0)
            right = win.left + int(win.width * x1)
            bottom = win.top + int(win.height * y1)
            if left <= x <= right and top <= y <= bottom:
                return False
        return True

    def _window_title(self) -> str:
        """Return the current active window title (lowercase)."""
        try:
            import pygetwindow as gw
            title = gw.getActiveWindowTitle() or ""
            return title.lower()
        except Exception:
            return ""

    # ── Public API ────────────────────────────────────────────────────────────

    def is_call_active(self) -> bool:
        """
        Detect if a WhatsApp call is currently active.

        Checks two signals:
          1. Window title contains call-related keywords ("calling", "on a call").
          2. WhatsApp window has an unusual aspect ratio consistent with call UI.
        Returns True if a call appears to be in progress.
        """
        title = self._window_title()
        call_keywords = ("calling", "on a call", "voice call", "video call", "incoming call")
        if any(kw in title for kw in call_keywords):
            self._log.info("Call detected via window title: %r", title)
            return True

        win = self._get_wa_window()
        if not win:
            return False
        # WhatsApp call UI is typically portrait and narrow
        try:
            if win.width > 0 and (win.height / win.width) > 2.0:
                self._log.info("Call detected via window aspect ratio (h/w=%.1f)", win.height / win.width)
                return True
        except Exception:
            pass
        return False

    def cancel_active_call(self) -> bool:
        """
        End an active WhatsApp call by pressing Escape or clicking the end-call area.

        Returns True if the cancel action was sent, False if WhatsApp was not found.
        """
        try:
            import pyautogui
        except ImportError:
            self._log.warning("pyautogui not available — cannot cancel call")
            return False

        win = self._get_wa_window()
        if not win:
            self._log.warning("cancel_active_call: WhatsApp window not found")
            return False

        try:
            if getattr(win, "isMinimized", False):
                win.restore()
            win.activate()
            time.sleep(SAFE_CLICK_DELAY)
            # Press Escape first — ends call in WhatsApp Desktop
            pyautogui.press("escape")
            time.sleep(1.0)
            self._log.info("Sent Escape to cancel active WhatsApp call")
            return True
        except Exception as exc:
            self._log.warning("cancel_active_call failed: %s", exc)
            return False

    def find_message_input_box(self) -> "tuple[int, int] | None":
        """
        Locate the WhatsApp message input box safely using window-relative coordinates.

        The input box is always in the lower-centre of the chat area.
        Returns (x, y) screen coordinates, or None if window is not found.
        """
        win = self._get_wa_window()
        if not win:
            return None
        try:
            # Input box is at ~50% width, ~92% height of the WhatsApp window.
            x = win.left + int(win.width * 0.50)
            y = win.top  + int(win.height * 0.92)
            if not self._point_is_safe(win, (x, y)):
                self._log.warning("Refusing to use an unsafe WhatsApp click point at (%d, %d)", x, y)
                return None
            self._log.debug("Message input box estimated at (%d, %d)", x, y)
            return x, y
        except Exception as exc:
            self._log.warning("find_message_input_box failed: %s", exc)
            return None

    def safe_send_message(self, phone_number: str, message: str, contact: str = "") -> bool:
        """
        Send a WhatsApp message safely, avoiding call button areas.

        Step 1: Open WhatsApp with the contact via deep link.
        Step 2: Wait WHATSAPP_LOAD_WAIT for the window to load.
        Step 3: Check for active call; cancel if found.
        Step 4: Wait SAFE_CLICK_DELAY.
        Step 5: Find message input box.
        Step 6: Click input, type message, press Enter.
        Step 7: Fall back to pywhatkit web method on any failure.

        Returns True on success, False on failure.
        """
        clean_phone = "".join(ch for ch in (phone_number or "") if ch.isdigit())
        if not clean_phone or not message:
            return False

        for attempt in range(1, MAX_RETRY_ATTEMPTS + 1):
            self._log.info("safe_send_message attempt %d/%d to %s", attempt, MAX_RETRY_ATTEMPTS, clean_phone)
            try:
                import pyautogui
                import pyperclip
            except ImportError:
                self._log.warning("pyautogui/pyperclip not available — falling back to web")
                return self._web_fallback(clean_phone, message)

            try:
                # Step 1 — open WhatsApp deep link to the contact
                if self._controller and contact:
                    if not self._controller._open_contact_chat(contact, clean_phone):
                        raise RuntimeError(f"Could not open the WhatsApp chat for {contact}")
                else:
                    target = f"whatsapp://send?phone={clean_phone}"
                    subprocess.Popen(
                        ["cmd", "/c", "start", "", target],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    )
                    self._log.info("Deep link launched for %s", clean_phone)

                # Step 2 — wait for window
                time.sleep(WHATSAPP_LOAD_WAIT)
                if self._controller and contact and not self._controller._current_chat_matches(contact):
                    raise RuntimeError(f"WhatsApp did not open the correct chat for {contact}")

                # Step 3 — cancel any active call
                if self.is_call_active():
                    self._log.warning("Call detected — cancelling before sending message")
                    if not self.cancel_active_call():
                        raise RuntimeError("An active WhatsApp call could not be cancelled")

                # Step 4 — safety pause
                time.sleep(SAFE_CLICK_DELAY)
                if self._controller and contact and not self._controller._current_chat_matches(contact):
                    raise RuntimeError(f"Target chat is not active before sending to {contact}")

                # Step 5 — locate input box
                input_pos = self.find_message_input_box()
                if not input_pos:
                    self._log.warning("Could not find message input box on attempt %d", attempt)
                    continue

                # Step 6 — click input, paste message, send
                win = self._get_wa_window()
                if win:
                    if not self._point_is_safe(win, input_pos):
                        raise RuntimeError("Refusing to click an unsafe area inside WhatsApp")
                    try:
                        if getattr(win, "isMinimized", False):
                            win.restore()
                        win.activate()
                        time.sleep(SAFE_CLICK_DELAY)
                    except Exception:
                        pass

                pyautogui.click(*input_pos)
                time.sleep(SAFE_CLICK_DELAY)
                if self._controller and contact and not self._controller._current_chat_matches(contact):
                    raise RuntimeError(f"Target chat focus was lost before sending to {contact}")
                # Use clipboard paste — safer than pyautogui.write for Unicode
                pyperclip.copy(message)
                pyautogui.hotkey("ctrl", "v")
                time.sleep(0.4)
                pyautogui.press("enter")
                self._log.info("safe_send_message: message sent to %s", clean_phone)
                return True

            except Exception as exc:
                self._log.warning("safe_send_message attempt %d failed: %s", attempt, exc)
                if attempt < MAX_RETRY_ATTEMPTS:
                    time.sleep(1.0)

        # Step 7 — web fallback
        self._log.warning("All desktop attempts failed — using web fallback for %s", clean_phone)
        return self._web_fallback(clean_phone, message)

    def _web_fallback(self, phone_number: str, message: str) -> bool:
        """pywhatkit web fallback — opens wa.me link in default browser."""
        try:
            encoded = urllib.parse.quote(message)
            webbrowser.open(f"https://wa.me/{phone_number}?text={encoded}")
            self._log.info("Web fallback opened for %s", phone_number)
            return True
        except Exception as exc:
            self._log.error("Web fallback also failed: %s", exc)
            return False


class WhatsAppController:
    def __init__(self, memory=None):
        self._whatsapp_ready = False
        self.memory = memory
        self._safe_sender = SafeWhatsAppSender(self)
        self._ui_automation_unavailable = False

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

    def _can_assume_chat_opened(self, contact: str, query: str, source: str) -> bool:
        contact_norm = self._normalize_label(contact)
        query_norm = self._normalize_label(query)
        if not contact_norm or query_norm != contact_norm:
            return False
        if not self._header_has_call_controls():
            return False
        log.info(f"Assuming WhatsApp chat is open for {contact} after {source} '{query}'")
        return True

    def send_message(self, contact: str, message: str) -> str:
        if not contact or not message:
            return f"Please provide both a contact name and a message, {USER_NAME}."

        contact_clean = contact.lower().strip()
        log.info(f"WhatsApp desktop preferred -> {contact}: {message}")

        phone = self._lookup_saved_phone(contact_clean)
        if phone:
            # SafeWhatsAppSender: call-safe primary path.
            # _send_via_desktop_link is kept as fallback if safe sender fails.
            def _safe_then_link():
                ok = self._safe_sender.safe_send_message(phone, message, contact=contact)
                if not ok:
                    log.warning("SafeWhatsAppSender failed - retrying with link for %s", contact)
                    self._send_via_desktop_link(phone, message, contact)
            threading.Thread(target=_safe_then_link, daemon=True).start()
            return f"Sending WhatsApp message to {contact} safely, {USER_NAME}."

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
                time.sleep(WHATSAPP_LOAD_WAIT)
                if self._current_chat_matches(contact):
                    self._press_enter_after_delay(1)
                    log.info(f"Sent desktop deep-link message to {contact}")
                    return
                log.warning(f"Desktop deep link did not confirm the chat for {contact}; retrying with search")

        if self._open_contact_chat(contact, phone):
            self._send_via_desktop_search(contact, message)
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

        input_pos = self._safe_sender.find_message_input_box()
        if input_pos:
            pyautogui.click(*input_pos)
            time.sleep(0.3)

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

    def _search_result_rows(self, win) -> list:
        desktop = self._pywinauto_desktop()
        if not desktop or not win:
            return []

        try:
            root = desktop.from_point(
                win.left + int(win.width * 0.23),
                win.top + int(win.height * 0.36),
            ).top_level_parent()
        except Exception:
            return []

        left_limit = win.left + int(win.width * 0.03)
        right_limit = win.left + int(win.width * 0.37)
        top_limit = win.top + int(win.height * 0.22)
        bottom_limit = win.top + int(win.height * 0.95)

        rows = []
        seen = set()
        for item in root.descendants():
            control_type = getattr(item.element_info, "control_type", "")
            if control_type not in ("ListItem", "Button", "Pane"):
                continue
            try:
                rect = item.rectangle()
            except Exception:
                continue

            width = rect.right - rect.left
            height = rect.bottom - rect.top
            center_x = (rect.left + rect.right) // 2
            center_y = (rect.top + rect.bottom) // 2
            if width < 180 or height < 40 or height > 140:
                continue
            if center_x < left_limit or center_x > right_limit:
                continue
            if center_y < top_limit or center_y > bottom_limit:
                continue

            signature = (rect.left, rect.top, rect.right, rect.bottom)
            if signature in seen:
                continue
            seen.add(signature)
            rows.append(item)
        return rows

    def _row_primary_text(self, row) -> str:
        texts = []
        try:
            row_rect = row.rectangle()
        except Exception:
            return ""

        for item in row.descendants():
            if getattr(item.element_info, "control_type", "") != "Text":
                continue
            try:
                rect = item.rectangle()
            except Exception:
                continue
            text = (item.window_text() or getattr(item.element_info, "name", "") or "").strip()
            if not text:
                continue
            if rect.left < row_rect.left or rect.right > row_rect.right:
                continue
            if rect.top < row_rect.top or rect.bottom > row_rect.bottom:
                continue
            texts.append((rect.top, rect.left, text))

        if not texts:
            return ""

        texts.sort(key=lambda row: (row[0], row[1]))
        return texts[0][2]

    def _click_exact_search_result(self, contact: str, wait_timeout: float = SEARCH_RESULT_WAIT) -> bool:
        win = self._get_whatsapp_window() or self._get_active_window()
        if not win:
            return False

        deadline = time.monotonic() + max(wait_timeout, 0.0)
        last_visible_labels = []

        while True:
            rows = self._search_result_rows(win)
            matching_rows = []
            visible_labels = []
            for row in rows:
                label = self._row_primary_text(row)
                if not label:
                    continue
                visible_labels.append(label)
                if self._title_matches_contact(label, contact):
                    matching_rows.append(row)

            if matching_rows:
                if visible_labels:
                    log.info("WhatsApp visible search rows: %s", " | ".join(visible_labels[:6]))
                for row in matching_rows:
                    try:
                        row.click_input()
                        time.sleep(1.0)
                        if self._current_chat_matches(contact):
                            log.info(f"Opened WhatsApp chat via exact result row for {contact}")
                            return True
                    except Exception:
                        try:
                            import pyautogui

                            rect = row.rectangle()
                            pyautogui.click((rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2)
                            time.sleep(1.0)
                            if self._current_chat_matches(contact):
                                log.info(f"Opened WhatsApp chat via exact result row center for {contact}")
                                return True
                        except Exception as e:
                            log.warning(f"Could not click exact WhatsApp result row for {contact}: {e}")
                            continue
                return False

            last_visible_labels = visible_labels
            if time.monotonic() >= deadline:
                if last_visible_labels:
                    log.info("WhatsApp visible search rows: %s", " | ".join(last_visible_labels[:6]))
                return False
            time.sleep(SEARCH_RESULT_POLL)

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
                time.sleep(0.25)
                if self._click_exact_search_result(contact):
                    return True
                if self._click_first_search_result(win, contact, query, source="typed search"):
                    return True
                pyautogui.press("down")
                time.sleep(0.15)
                pyautogui.press("enter")
                time.sleep(1.0)
                if self._current_chat_matches(contact):
                    log.info(f"Opened WhatsApp chat via keyboard search for {contact} using query '{query}'")
                    return True
                if self._can_assume_chat_opened(contact, query, source="keyboard search"):
                    return True

                # Fallback to clipboard paste for cases where direct typing is blocked.
                pyautogui.click(search_x, search_y)
                time.sleep(0.2)
                pyautogui.hotkey("ctrl", "a")
                pyautogui.press("backspace")
                pyperclip.copy(query)
                pyautogui.hotkey("ctrl", "v")
                time.sleep(0.25)
                if self._click_exact_search_result(contact):
                    return True
                if self._click_first_search_result(win, contact, query, source="result click"):
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

        try:
            import pygetwindow as gw

            active_title = gw.getActiveWindowTitle() or ""
        except Exception:
            active_title = ""

        if active_title:
            log.info("WhatsApp active window title fallback: %s", active_title)
        return self._title_matches_contact(active_title, contact)

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
            log.warning(f"Could not open a WhatsApp Desktop chat for {contact}; not falling back to web")
            self._open_desktop_app()
            self._focus_whatsapp_window(wait_seconds=8)
            return
        try:
            pyautogui.press("esc")
            time.sleep(0.2)
        except Exception:
            pass
        if self._click_call_button(video=video):
            log.info(f"Activated {'video ' if video else ''}call button for {contact} via UI automation")
            return
        if self._start_call_via_shortcut(contact, video=video):
            log.info(f"Confirmed {'video ' if video else ''}call shortcut for {contact}")
            return
        if self._start_call_from_header(video=video):
            log.info(f"Activated {'video ' if video else ''}call from header controls for {contact}")
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
        if self._ui_automation_unavailable:
            return None
        try:
            import comtypes
            import types
        except Exception as e:
            self._ui_automation_unavailable = True
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
            self._ui_automation_unavailable = True
            log.warning(f"UI automation backend could not start: {e}")
            return None

    def _click_first_search_result(self, win, contact: str, query: str, source: str) -> bool:
        try:
            import pyautogui
        except Exception:
            return False

        try:
            result_x, result_y = self._first_search_result_point(win)
            pyautogui.click(result_x, result_y)
            time.sleep(1.0)
        except Exception as e:
            log.warning(f"Could not click the first WhatsApp search result for {contact}: {e}")
            return False

        if self._current_chat_matches(contact):
            log.info(f"Opened WhatsApp chat via {source} for {contact} using query '{query}'")
            return True
        return self._can_assume_chat_opened(contact, query, source=source)

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
