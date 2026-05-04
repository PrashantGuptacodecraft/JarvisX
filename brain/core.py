"""
brain/core.py
Intent detection → action router.
Routes 40+ command types including terminal, web, and code execution.
"""
import json
import re
from difflib import get_close_matches
from config.logger import get_logger
from config.settings import USER_NAME

log = get_logger("brain")

# ──────────────────────────────────────────────
#  Intent keyword map
# ──────────────────────────────────────────────
INTENTS = {
    # Apps
    "open_app":       ["open ", "launch ", "start ", "run "],
    "close_app":      ["close ", "kill ", "quit "],
    # Browser
    "search_google":  ["search for", "google ", "look up", "search on google"],
    "site_search":    ["search github for", "search reddit for", "search wikipedia for", "search stackoverflow for", "search maps for", "search amazon for"],
    "play_youtube":   ["play ", "youtube ", "watch "],
    "search_youtube": ["search youtube", "youtube search", "find on youtube"],
    "open_website":   ["go to ", "open website", "visit ", "navigate to"],
    "open_gmail":     ["open gmail", "check gmail", "my email", "open mail", "check mail"],
    "open_github":    ["open github", "go to github"],
    "open_whatsapp_web": ["open whatsapp", "whatsapp web"],
    # Email compose
    "compose_email":  ["write email", "compose email", "write a mail", "compose mail",
                       "send email", "send mail", "write mail to", "email to ",
                       "draft email", "draft mail"],
    # System
    "volume_up":      ["volume up", "louder", "increase volume", "turn up"],
    "volume_down":    ["volume down", "quieter", "decrease volume", "turn down"],
    "mute":           ["mute", "silence audio"],
    "screenshot":     ["screenshot", "capture screen", "take a screenshot"],
    "battery":        ["battery", "power level", "how much charge"],
    "wifi":           ["wifi status", "internet status", "network status"],
    "lock":           ["lock screen", "lock computer", "lock the screen"],
    "shutdown":       ["shutdown", "power off", "turn off computer", "shut down"],
    "restart":        ["restart", "reboot"],
    "time":           ["what time", "current time", "tell me the time"],
    "date":           ["what date", "today's date", "what day is it"],
    "cpu_usage":      ["cpu usage", "processor usage", "cpu load"],
    "ram_usage":      ["ram usage", "memory usage", "how much ram"],
    "processes":      ["running processes", "what processes", "task list"],
    "kill_process":   ["kill process", "end process", "terminate process"],
    # Files
    "find_file":      ["find file", "find my ", "search file", "locate file", "where is my"],
    "open_folder":    ["open downloads", "open desktop", "open documents", "open folder", "open pictures"],
    "read_file":      ["read file", "read pdf", "read document", "open and read"],
    "organize_files": ["organize files", "sort files", "clean up downloads"],
    "create_file":    ["create file", "make a file", "new file", "write a file"],
    "download_file":  ["download ", "download file", "save from url", "save this file"],
    # Terminal
    "run_command":    ["run command", "execute ", "terminal ", "cmd ", "run in terminal", "shell "],
    "run_python":     ["run python", "execute python", "python script", "run script"],
    "write_code":     ["write code", "write a script", "code that ", "create a script", "write python"],
    # Web
    "fetch_url":      ["fetch url", "open url", "get page", "fetch page", "read webpage", "read website"],
    "web_search":     ["search the web", "search internet", "search online", "look online for"],
    "summarize_web":  ["summarize", "what does this page say", "tldr"],
    # WhatsApp
    "whatsapp_msg":   ["message ", "whatsapp ", "send message", "text ", " msg "],
    "whatsapp_call":  ["call ", "voice call ", "audio call "],
    "whatsapp_video_call": ["video call ", "videochat ", "video chat "],
    # Tasks / Memory
    "remind":         ["remind me", "set reminder", "alarm "],
    "add_todo":       ["add todo", "todo ", "add task", "to-do"],
    "add_note":       ["note that", "write down", "save this note", "make a note"],
    "list_todos":     ["show todos", "my tasks", "list todos", "show my list"],
    "memory_store":   ["remember that", "remember "],
    "memory_recall":  ["what is my", "do you remember", "recall ", "what did i say"],
    "memory_forget":  ["forget everything", "clear memory", "delete memory"],
    # Vision
    "ocr":            ["read screen", "ocr ", "read text on screen", "what's on screen"],
    "analyze_screen": ["analyze screen", "what do you see", "describe screen"],
    # Clipboard
    "read_clipboard": ["read clipboard", "what's in clipboard", "clipboard content"],
    "copy_to_clipboard": ["copy to clipboard", "copy this"],
}

PLAN_ONLY_INTENTS = {
    "open_youtube_channel",
    "play_youtube_from_channel",
    "youtube_comment",
    "youtube_workflow",
}

SEARCHABLE_SITES = {
    "github", "youtube", "google", "reddit", "wikipedia", "stackoverflow",
    "stack overflow", "maps", "amazon", "drive", "linkedin",
}

CONFIRMATION_REQUIRED = {"shutdown", "restart", "kill_process"}

APP_MAP = {
    "chrome": "chrome", "google chrome": "chrome", "browser": "chrome",
    "firefox": "firefox", "vscode": "vscode", "vs code": "vscode",
    "visual studio code": "vscode", "notepad": "notepad",
    "calculator": "calculator", "calc": "calculator",
    "explorer": "explorer", "file explorer": "explorer",
    "spotify": "spotify", "camera": "camera", "settings": "settings",
    "whatsapp": "whatsapp", "telegram": "telegram", "discord": "discord",
    "vlc": "vlc", "word": "word", "excel": "excel",
    "powerpoint": "powerpoint", "paint": "paint", "taskmanager": "taskmanager",
    "task manager": "taskmanager", "terminal": "terminal", "cmd": "cmd",
    "powershell": "powershell", "notepad++": "notepadpp",
    "youtube": "youtube", "google": "google", "gmail": "gmail",
    "github": "github", "whatsapp web": "whatsapp",
    "instagram": "instagram", "reddit": "reddit", "linkedin": "linkedin",
    "netflix": "netflix", "maps": "maps", "drive": "drive", "meet": "meet",
}


class Brain:
    def __init__(self, ai_client, tools: dict):
        self.ai      = ai_client
        self.tools   = tools
        self.planner = None   # Set by main after init to avoid circular dep
        self.pending = None   # Pending confirmation: (intent, params)
        self._gui_terminal_log = None   # Callback to write to GUI terminal
        self._planner_active = False
        self._last_whatsapp_contact = ""

    def set_terminal_log(self, callback):
        """Allow GUI terminal tab to receive command outputs."""
        self._gui_terminal_log = callback

    def _terminal_log(self, text: str):
        if self._gui_terminal_log:
            self._gui_terminal_log(text)

    def supported_intents(self) -> list[str]:
        return sorted(set(INTENTS.keys()) | PLAN_ONLY_INTENTS)

    def detect_intent(self, text: str):
        text = (text or "").strip()
        return self._detect_intent(text.lower(), text)

    def execute_intent(self, intent: str, params: dict, original: str) -> str:
        return self._execute(intent, params or {}, original)

    # ─────────────────────────────────────────
    def process(self, text: str) -> str:
        """Main entry: detect intent and route to correct handler."""
        text = text.strip()
        text_lower = text.lower()

        # Handle pending confirmation
        if self.pending:
            return self._handle_confirmation(text_lower)

        # Prefer direct WhatsApp message execution over planner/app-open heuristics.
        if self._looks_like_whatsapp_message(text_lower):
            params = self._extract_params("whatsapp_msg", text_lower, text)
            if params.get("contact") and params.get("message"):
                log.info(f"Intent: 'whatsapp_msg'  Params: {params}")
                return self._execute("whatsapp_msg", params, text)

        if self._looks_like_whatsapp_call(text_lower):
            intent = "whatsapp_video_call" if "video call" in text_lower or "videochat" in text_lower or "video chat" in text_lower else "whatsapp_call"
            params = self._extract_params(intent, text_lower, text)
            if params.get("contact"):
                log.info(f"Intent: {intent!r}  Params: {params}")
                return self._execute(intent, params, text)

        # Check for complex multi-step task
        if self.planner and not self._planner_active and self.planner.is_complex_task(text):
            log.info("Complex task detected — using autonomous planner")
            return self.planner.plan_and_execute(text, gui_log=self._terminal_log)

        intent, params = self.detect_intent(text)
        log.info(f"Intent: {intent!r}  Params: {params}")

        if intent in CONFIRMATION_REQUIRED:
            self.pending = (intent, params)
            return self._ask_confirmation(intent, params)

        if intent:
            return self.execute_intent(intent, params, text)

        return self.ai.chat(text)

    # ─────────────────────────────────────────
    def _detect_intent(self, low: str, original: str):
        if self._looks_like_whatsapp_message(low):
            params = self._extract_params("whatsapp_msg", low, original)
            if params.get("contact") and params.get("message"):
                return "whatsapp_msg", params
        if self._looks_like_whatsapp_call(low):
            intent = "whatsapp_video_call" if "video call" in low or "videochat" in low or "video chat" in low else "whatsapp_call"
            params = self._extract_params(intent, low, original)
            if params.get("contact"):
                return intent, params
        if self._looks_like_folder_open(low):
            return "open_folder", self._extract_params("open_folder", low, original)
        if any(kw in low for kw in INTENTS["search_youtube"]):
            return "search_youtube", self._extract_params("search_youtube", low, original)
        if self._looks_like_site_search(low):
            return "site_search", self._extract_params("site_search", low, original)
        if self._looks_like_download(low):
            return "download_file", self._extract_params("download_file", low, original)
        for intent, keywords in INTENTS.items():
            for kw in keywords:
                if kw in low:
                    return intent, self._extract_params(intent, low, original)
        return None, {}

    def _looks_like_whatsapp_message(self, low: str) -> bool:
        has_contact_signal = " to " in low or " saying " in low or " that " in low or " tell " in low
        has_msg_signal = any(w in low for w in ["message", "measage", "msg", "whatsapp", "text"])
        # Exclude email compose from being caught as WhatsApp
        is_email = any(w in low for w in ["email", "mail", "gmail"])
        return has_msg_signal and has_contact_signal and not is_email

    def _looks_like_whatsapp_call(self, low: str) -> bool:
        if "call" not in low:
            return False
        if any(w in low for w in ["email", "mail", "gmail", "meeting", "recall"]):
            return False
        return any(w in low for w in ["whatsapp", "video call", "voice call", "audio call", "call him", "call her", "call them"]) or len(low.split()) <= 4

    def _looks_like_site_search(self, low: str) -> bool:
        if "search youtube" in low or "youtube search" in low or "find on youtube" in low:
            return False
        patterns = [
            r"\bsearch\s+(?:on\s+)?([a-z0-9 .+-]+?)\s+for\s+.+",
            r"\bon\s+([a-z0-9 .+-]+?)\s+search\s+.+",
            r"\bopen\s+([a-z0-9 .+-]+?)\s+and\s+search\s+.+",
        ]
        for pattern in patterns:
            match = re.search(pattern, low, re.IGNORECASE)
            if match and match.group(1).strip() in SEARCHABLE_SITES:
                return True
        return False

    def _looks_like_download(self, low: str) -> bool:
        if not re.search(r"\bdownload\b", low):
            return False
        return not any(word in low for word in ["shutdown", "upload", "speed test"])

    def _looks_like_folder_open(self, low: str) -> bool:
        if "open " not in low:
            return False
        return any(folder in low for folder in ["downloads", "desktop", "documents", "pictures", "music", "videos", "folder"])

    def _clean_contact_name(self, value: str) -> str:
        contact = (value or "").strip()
        contact = re.sub(r'\b(?:on whatsapp|in whatsapp|using whatsapp|on wa|on whats app)\b', "", contact, flags=re.IGNORECASE)
        contact = re.sub(r'\s+', " ", contact).strip(" ,.-")
        return contact.title()

    def _extract_params(self, intent: str, low: str, original: str) -> dict:
        p = {"raw": original}

        if intent in ("open_app", "close_app"):
            for alias, name in APP_MAP.items():
                if alias in low:
                    p["app"] = name
                    break
            if not p.get("app"):
                lowered = original.lower().strip()
                for prefix in ("open ", "launch ", "start ", "run ", "close ", "kill ", "quit "):
                    if lowered.startswith(prefix):
                        candidate = lowered[len(prefix):].strip()
                        if candidate:
                            match = get_close_matches(candidate, list(APP_MAP.keys()), n=1, cutoff=0.7)
                            if match:
                                p["app"] = APP_MAP[match[0]]
                        break

        elif intent in ("search_google", "web_search"):
            for kw in ["search for", "search on google", "google ", "look up",
                        "search the web", "search internet", "search online", "look online for"]:
                if kw in low:
                    p["query"] = low.split(kw, 1)[-1].strip()
                    break

        elif intent == "site_search":
            patterns = [
                r"\bsearch\s+(?:on\s+)?([A-Za-z0-9 .+-]+?)\s+for\s+(.+)",
                r"\bon\s+([A-Za-z0-9 .+-]+?)\s+search\s+(.+)",
                r"\bopen\s+([A-Za-z0-9 .+-]+?)\s+and\s+search\s+(.+)",
            ]
            for pattern in patterns:
                match = re.search(pattern, original, re.IGNORECASE)
                if match:
                    p["site"] = match.group(1).strip()
                    p["query"] = match.group(2).strip()
                    break

        elif intent in ("play_youtube", "search_youtube"):
            for kw in ["play ", "watch ", "search youtube", "youtube search", "find on youtube"]:
                if kw in low:
                    p["query"] = low.split(kw, 1)[-1].strip()
                    break

        elif intent in ("open_website", "fetch_url"):
            for kw in ["go to ", "open website", "visit ", "navigate to",
                        "fetch url", "open url", "get page", "read webpage", "read website"]:
                if kw in low:
                    p["url"] = low.split(kw, 1)[-1].strip()
                    break

        elif intent == "whatsapp_msg":
            # Pattern order: most specific first
            patterns = [
                # "message/text/msg/whatsapp <contact> saying/that/tell <message>"
                ("contact_first", r'(?:message|measage|text|msg|whatsapp)\s+(.+?)\s+(?:saying|that|tell(?:ing)?)\s+(.+)'),
                # "send message/whatsapp message to <contact> saying <message>"
                ("contact_first", r'(?:send\s+(?:whatsapp\s+)?message|send\s+measage|whatsapp)\s+to\s+(.+?)\s+(?:saying|that|:)\s+(.+)'),
                # "send <message> to <contact>"
                ("message_first", r'(?:send\s+message|send\s+measage|message|measage)\s+(.+?)\s+to\s+(.+)'),
                # "text <contact> <message>" (no keyword after contact)
                ("contact_first", r'(?:text|msg)\s+([A-Za-z]+(?:\s+[A-Za-z]+)?)\s+(.+)'),
            ]
            for mode, pattern in patterns:
                m = re.search(pattern, original, re.IGNORECASE)
                if m:
                    first = m.group(1).strip()
                    second = m.group(2).strip()
                    if mode == "message_first":
                        p["message"] = first
                        p["contact"] = self._clean_contact_name(second)
                    else:
                        p["contact"] = self._clean_contact_name(first)
                        p["message"] = second
                    break
            if not p.get("contact") or not p.get("message"):
                tokens = re.split(r'\b(?:message|measage|text|msg|whatsapp|send)\b', original, flags=re.IGNORECASE)
                cleaned = " ".join(t.strip() for t in tokens if t.strip()).strip()
                if " to " in cleaned.lower():
                    message, contact = re.split(r'\bto\b', cleaned, maxsplit=1, flags=re.IGNORECASE)
                    p["message"] = message.strip()
                    p["contact"] = self._clean_contact_name(contact)

        elif intent in ("whatsapp_call", "whatsapp_video_call"):
            stripped = re.sub(r'^(?:please\s+)?(?:whatsapp\s+)?(?:video call|voice call|audio call|call)\s+', "", original, flags=re.IGNORECASE).strip()
            stripped = re.sub(r'\bon whatsapp\b', "", stripped, flags=re.IGNORECASE).strip()
            pronouns = {"him", "her", "them", "that person"}
            if stripped.lower() in pronouns or not stripped:
                p["contact"] = self._last_whatsapp_contact
            else:
                p["contact"] = self._clean_contact_name(stripped)

        elif intent == "compose_email":
            # Extract: to, subject, body from natural speech
            # "write email to rahul@gmail.com subject meeting body let's meet at 5"
            # "send mail to Mom saying I'll be late"
            to_match = re.search(
                r'(?:to|for)\s+([\w._%+\-]+@[\w.\-]+\.[a-z]{2,}|[A-Za-z]+(?:\s+[A-Za-z]+)?)',
                original, re.IGNORECASE
            )
            subject_match = re.search(
                r'(?:subject|about|regarding|re:?)\s+(.+?)(?:\s+(?:body|saying|that|message|content)|$)',
                original, re.IGNORECASE
            )
            body_match = re.search(
                r'(?:body|saying|that|message|content|tell(?:ing)?\s+(?:him|her|them)?)\s+(.+)',
                original, re.IGNORECASE
            )
            if to_match:
                p["to"] = to_match.group(1).strip()
            if subject_match:
                p["subject"] = subject_match.group(1).strip()
            if body_match:
                p["body"] = body_match.group(1).strip()

        elif intent == "remind":
            m = re.search(r'remind(?:\s+me)?\s+(?:to\s+)?(.+?)\s+at\s+(.+)', low)
            if m:
                p["task"] = m.group(1).strip()
                p["time"] = m.group(2).strip()
            else:
                p["task"] = low.replace("remind me", "").replace("set reminder", "").strip()
                p["time"] = "unspecified"

        elif intent in ("memory_store", "add_note"):
            for kw in ["remember that", "remember ", "note that", "write down",
                        "save this note", "make a note"]:
                if kw in low:
                    p["fact"] = original.split(kw, 1)[-1].strip()
                    break

        elif intent == "find_file":
            for kw in ["find file", "find my ", "search file", "locate file", "where is my"]:
                if kw in low:
                    p["name"] = low.split(kw, 1)[-1].strip()
                    break

        elif intent == "open_folder":
            for folder in ["downloads", "desktop", "documents", "pictures", "music", "videos"]:
                if folder in low:
                    p["folder"] = folder
                    break

        elif intent == "download_file":
            url_match = re.search(r'https?://[^\s)>\]"]+', original)
            if url_match:
                p["url"] = url_match.group(0)
            folder_match = re.search(
                r'\b(?:to|in)\s+(downloads|desktop|documents|pictures|music|videos)\b',
                low,
                re.IGNORECASE,
            )
            if folder_match:
                p["folder"] = folder_match.group(1).lower()
            name_match = re.search(
                r'\b(?:as|named)\s+([A-Za-z0-9._ -]+\.[A-Za-z0-9]{2,6})\b',
                original,
                re.IGNORECASE,
            )
            if name_match:
                p["filename"] = name_match.group(1).strip()

            query = re.sub(r'^\s*download\s+', '', original, flags=re.IGNORECASE).strip()
            query = re.sub(r'\bfrom\s+https?://[^\s)>\]"]+', '', query, flags=re.IGNORECASE).strip(" ,.")
            query = re.sub(
                r'\b(?:to|in)\s+(downloads|desktop|documents|pictures|music|videos)\b',
                '',
                query,
                flags=re.IGNORECASE,
            ).strip(" ,.")
            query = re.sub(
                r'\b(?:as|named)\s+[A-Za-z0-9._ -]+\.[A-Za-z0-9]{2,6}\b',
                '',
                query,
                flags=re.IGNORECASE,
            ).strip(" ,.")
            if query and not p.get("url"):
                p["query"] = query

        elif intent in ("run_command", "run_python", "write_code"):
            for kw in ["run command", "execute ", "terminal ", "cmd ", "run in terminal",
                        "shell ", "run python", "execute python", "python script",
                        "write code", "write a script", "code that ", "create a script",
                        "write python", "run script"]:
                if kw in low:
                    p["content"] = original.split(kw, 1)[-1].strip()
                    break
            if not p.get("content"):
                p["content"] = original

        elif intent == "kill_process":
            m = re.search(r'(?:kill|end|terminate)\s+(?:process\s+)?(.+)', low)
            if m:
                p["process"] = m.group(1).strip()

        elif intent == "summarize_web":
            p["content"] = original

        return p

    # ─────────────────────────────────────────
    def _execute(self, intent: str, params: dict, original: str) -> str:
        t = self.tools
        apps     = t.get("apps")
        browser  = t.get("browser")
        system   = t.get("system")
        wa       = t.get("whatsapp")
        files    = t.get("files")
        tasks    = t.get("tasks")
        memory   = t.get("memory")
        vision   = t.get("vision")
        terminal = t.get("terminal")
        web      = t.get("web")

        try:
            # ── Apps ──────────────────────────────────
            if intent == "open_app":
                app = params.get("app")
                if app:
                    if app == "whatsapp" and wa:
                        return wa.open_whatsapp()
                    if app in {"youtube", "google", "gmail", "github", "instagram", "reddit", "linkedin", "netflix", "maps", "drive", "meet"}:
                        return browser.open_url(app)
                    return apps.open(app)
                return f"I couldn't identify which app to open, {USER_NAME}."
            if intent == "close_app":
                app = params.get("app")
                return apps.close(app) if app else f"Which app, {USER_NAME}?"

            # ── Browser ────────────────────────────────
            if intent == "search_google":
                return browser.search_google(params.get("query", ""))
            if intent == "site_search":
                return browser.search_website(
                    params.get("site", ""),
                    params.get("query", ""),
                )
            if intent == "play_youtube":
                return browser.play_youtube(params.get("query", ""))
            if intent == "search_youtube":
                return browser.search_youtube(params.get("query", ""))
            if intent == "open_youtube_channel":
                return browser.open_youtube_channel(
                    params.get("channel", "") or params.get("query", "") or params.get("raw", "")
                )
            if intent == "play_youtube_from_channel":
                return browser.play_from_youtube_channel(
                    channel=params.get("channel", ""),
                    video_query=params.get("video_query", ""),
                    prefer_latest=params.get("play_strategy", "latest") in {"latest", "newest", "recent", "first"},
                )
            if intent == "youtube_comment":
                return browser.comment_on_youtube(
                    params.get("comment", "") or params.get("text", "") or params.get("raw", "")
                )
            if intent == "youtube_workflow":
                return browser.youtube_workflow(
                    channel=params.get("channel", ""),
                    video_query=params.get("video_query", ""),
                    comment=params.get("comment", ""),
                    play_strategy=params.get("play_strategy", "latest"),
                    raw_command=original,
                )
            if intent in ("open_website",):
                return browser.open_url(params.get("url", ""))
            if intent == "open_gmail":
                return browser.open_gmail() if hasattr(browser, "open_gmail") else browser.open_url("gmail")
            if intent == "open_github":
                return browser.open_url("github")
            if intent == "open_whatsapp_web":
                return browser.open_url("whatsapp")
            if intent == "compose_email":
                to      = params.get("to", "")
                subject = params.get("subject", "")
                body    = params.get("body", "")
                if hasattr(browser, "compose_gmail"):
                    return browser.compose_gmail(to=to, subject=subject, body=body)
                # Fallback: open Gmail
                return browser.open_url("gmail")
            if intent == "web_search":
                if web:
                    return web.search(params.get("query", original))
                return browser.search_google(params.get("query", original))

            # ── System ─────────────────────────────────
            if intent == "volume_up":    return system.volume_up()
            if intent == "volume_down":  return system.volume_down()
            if intent == "mute":         return system.mute()
            if intent == "screenshot":   return system.screenshot()
            if intent == "battery":      return system.battery_status()
            if intent == "wifi":         return system.wifi_status()
            if intent == "lock":         return system.lock_screen()
            if intent == "shutdown":     return system.shutdown()
            if intent == "restart":      return system.restart()
            if intent == "time":         return system.get_time()
            if intent == "date":         return system.get_date()
            if intent == "cpu_usage":    return system.cpu_usage()
            if intent == "ram_usage":    return system.ram_usage()
            if intent == "processes":    return system.list_processes()
            if intent == "kill_process":
                return system.kill_process(params.get("process", ""))

            # ── Files ──────────────────────────────────
            if intent == "find_file":
                return files.find_file(params.get("name", ""))
            if intent == "open_folder":
                return files.open_folder(params.get("folder", "downloads"))
            if intent == "read_file":
                return files.read_file(params.get("raw", ""))
            if intent == "organize_files":
                return files.organize_by_type()
            if intent == "create_file":
                return files.create_file_interactive(params.get("raw", original), self.ai)

            # ── Terminal ────────────────────────────────
            if intent == "run_command":
                if terminal:
                    result = terminal.run_command(params.get("content", ""))
                    self._terminal_log(f"$ {params.get('content','')}\n{result}")
                    return f"Command executed. Output:\n{result[:500]}"
                return f"Terminal not available, {USER_NAME}."
            if intent == "run_python":
                if terminal:
                    result = terminal.run_python_code(params.get("content", ""))
                    self._terminal_log(f"[Python]\n{params.get('content','')}\n---\n{result}")
                    return f"Python executed. Output:\n{result[:500]}"
                return f"Python runner not available, {USER_NAME}."
            if intent == "write_code":
                if terminal:
                    return terminal.write_and_run(params.get("content", original), self.ai)
                return self.ai.chat(original)

            # ── Web ────────────────────────────────────
            if intent == "fetch_url":
                if web:
                    url = params.get("url", "")
                    content = web.fetch_page(url)
                    return self.ai.summarize(content)
                return browser.open_url(params.get("url", ""))
            if intent == "download_file":
                if web:
                    url = params.get("url", "")
                    filename = params.get("filename", "")
                    folder = params.get("folder", "downloads")
                    if url:
                        return web.download_file(url, filename=filename, folder=folder)
                    return web.download_from_query(
                        params.get("query", original),
                        filename=filename,
                        folder=folder,
                    )
                return f"Download tools are not available, {USER_NAME}."
            if intent == "summarize_web":
                if web:
                    return web.summarize_with_ai(params.get("content", original), self.ai)
                return self.ai.chat(original)

            # ── WhatsApp ────────────────────────────────
            if intent == "whatsapp_msg":
                contact = params.get("contact", "")
                message = params.get("message", "")
                if wa and contact and message:
                    self._last_whatsapp_contact = contact
                    return wa.send_message(contact, message)
                return f"Specify contact and message, {USER_NAME}."
            if intent == "whatsapp_call":
                contact = params.get("contact", "")
                if wa and contact:
                    self._last_whatsapp_contact = contact
                    return wa.start_call(contact, video=False)
                return f"Which contact should I call on WhatsApp, {USER_NAME}?"
            if intent == "whatsapp_video_call":
                contact = params.get("contact", "")
                if wa and contact:
                    self._last_whatsapp_contact = contact
                    return wa.start_call(contact, video=True)
                return f"Which contact should I video call on WhatsApp, {USER_NAME}?"

            # ── Tasks / Memory ──────────────────────────
            if intent == "remind":
                return memory.add_reminder(params.get("task",""), params.get("time",""))
            if intent == "add_todo":
                item = original
                for prefix in ["add todo", "todo", "to-do", "add task"]:
                    if prefix in original.lower():
                        item = original.lower().split(prefix, 1)[-1].strip()
                        break
                return memory.add_todo(item)
            if intent == "add_note":
                return memory.add_note(params.get("fact", original))
            if intent == "list_todos":
                todos = memory.get_todos()
                if not todos:
                    return f"Your to-do list is empty, {USER_NAME}."
                return "Your tasks:\n" + "\n".join(f"• {t['item']}" for t in todos)
            if intent == "memory_store":
                return memory.store_fact(params.get("fact", original))
            if intent == "memory_recall":
                return memory.recall_fact(original)
            if intent == "memory_forget":
                return memory.forget(original)

            # ── Vision / Clipboard ──────────────────────
            if intent == "ocr":
                return vision.read_screen_text() if vision else "Vision not available."
            if intent == "analyze_screen":
                if vision:
                    text = vision.read_screen_text()
                    return self.ai.chat(f"Describe and analyze this screen content:\n{text}")
                return "Vision not available."
            if intent == "read_clipboard":
                try:
                    import pyperclip
                    content = pyperclip.paste()
                    return f"Clipboard contains: {content[:500]}"
                except Exception:
                    return "Couldn't read clipboard."
            if intent == "copy_to_clipboard":
                try:
                    import pyperclip
                    content = original.replace("copy to clipboard", "").strip()
                    pyperclip.copy(content)
                    return f"Copied to clipboard, {USER_NAME}."
                except Exception:
                    return "Couldn't access clipboard."

        except Exception as e:
            log.error(f"Execution error [intent={intent}]: {e}")
            return f"Error executing '{intent}', {USER_NAME}: {e}"

        return self.ai.chat(original)

    # ─────────────────────────────────────────
    def _ask_confirmation(self, intent: str, params: dict) -> str:
        descs = {
            "shutdown":     "shut down the computer",
            "restart":      "restart the computer",
            "whatsapp_msg": f"send WhatsApp message to {params.get('contact','the contact')}",
            "kill_process": f"kill process '{params.get('process','')}'",
        }
        action = descs.get(intent, intent)
        return f"Confirm: should I {action}? Say yes or no."

    def _handle_confirmation(self, low: str) -> str:
        intent, params = self.pending
        self.pending = None
        if any(w in low for w in ["yes", "yeah", "yep", "do it", "confirm", "sure", "go ahead", "ok"]):
            return self.execute_intent(intent, params, params.get("raw", ""))
        return f"Cancelled, {USER_NAME}."
