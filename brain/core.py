"""
brain/core.py
Intent detection → action router.
Routes 40+ command types including terminal, web, and code execution.
"""
import json
import random
import re
from difflib import get_close_matches
from config.logger import get_logger
from config.settings import (
    KNOWLEDGE_DIR,
    OPERATOR_MODE,
    USER_NAME,
    VOICE_HISTORY_ITEMS,
    VOICE_MEMORY_CONTEXT_ITEMS,
)

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
    "add_whatsapp_contact": ["add whatsapp contact", "save whatsapp contact", "remember whatsapp contact"],
    "list_whatsapp_contacts": ["list whatsapp contacts", "show whatsapp contacts", "my whatsapp contacts"],
    "save_profile": ["remember profile", "save profile", "my profile is"],
    "show_profile": ["show my profile", "list my profile", "what is in my profile"],
    "save_project_memory": ["save project", "remember project", "update project"],
    "show_project_memory": ["show project", "project details for", "what do you know about project"],
    "list_projects": ["list projects", "show projects", "my projects"],
    "ingest_knowledge_file": ["learn file", "ingest file", "import knowledge file", "remember this file"],
    "list_knowledge_files": ["list knowledge files", "show knowledge files", "list brain files"],
    "brain_status": ["brain status", "memory status", "knowledge status"],
    "save_workflow": ["save workflow", "remember workflow", "create workflow"],
    "run_workflow": ["run workflow", "start workflow", "execute workflow"],
    "list_workflows": ["list workflows", "show workflows", "my workflows"],
    "start_mission": ["start mission", "create mission", "save mission"],
    "show_mission": ["show mission", "mission details", "active mission", "current mission"],
    "list_missions": ["list missions", "show missions", "my missions"],
    "complete_mission": ["complete mission", "finish mission", "close mission"],
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
    "tell_joke": ["tell me a joke", "some jokes", "make me laugh"],
    "comfort_support": ["not feeling good", "feeling low", "i am sad", "i'm sad"],
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
        self._pending_whatsapp_contact = ""
        self._pending_whatsapp_message = ""
        self._last_cam_image = ""   # Path to last camera frame for vision queries

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

    def execute_intent(self, intent: str, params: dict, original: str, voice_mode: bool = False) -> str:
        return self._execute(intent, params or {}, original, voice_mode=voice_mode)

    # ─────────────────────────────────────────
    def process(self, text: str, voice_mode: bool = False) -> str:
        """Main entry: detect intent and route to correct handler."""
        text = text.strip()
        text_lower = text.lower()


        # ── Camera vision: intercept queries about what camera sees ──────
        # Commands from UI: "look at camera image <path> and answer: <question>"
        import re as _re
        cam_match = _re.match(
            r'look at camera image (.+?) and answer:\s*(.+)', text, _re.IGNORECASE | _re.DOTALL
        )
        if cam_match:
            import pathlib as _pl
            try:
                img_path = str(_pl.Path(cam_match.group(1).strip()).resolve())
            except Exception:
                img_path = cam_match.group(1).strip()
            question = cam_match.group(2).strip()
            self._last_cam_image = img_path
            log.info(f"Camera vision query: {question!r} on {img_path}")
            return self.ai.chat_with_image(question, img_path, voice_mode=voice_mode)

        # Natural camera questions: use last saved frame if one exists
        _camera_phrases = [
            "what do you see", "what can you see", "what's in the camera",
            "what is in the camera", "what's in picture", "what in picture",
            "what the object", "what object", "describe what you see",
            "look at me", "look at my face", "how do i look",
            "my expression", "my face", "my hair", "hairstyle",
            "suggest hair", "suggest hairstyle", "haircut suggestion",
            "what am i wearing", "what color", "tell me about",
            "analyze my", "read my face", "my mood", "my emotion",
            "what other things", "anything else in", "describe the scene",
            "whats around", "what's around",
        ]
        if self._last_cam_image and any(ph in text_lower for ph in _camera_phrases):
            log.info(f"Camera context query (natural): {text!r}")
            return self.ai.chat_with_image(text, self._last_cam_image, voice_mode=voice_mode)

        # ── End camera vision ────────────────────────────────────────────
        # Handle pending confirmation
        if self.pending:
            return self._handle_confirmation(text_lower)

        follow_up = self._handle_pending_whatsapp_follow_up(text, voice_mode=voice_mode)
        if follow_up is not None:
            return follow_up

        self._learn_from_user_text(text)

        contact_only = self._resolve_whatsapp_contact_name(text)
        if contact_only and len(text_lower.split()) <= 4 and not any(token in text_lower for token in ("open", "call", "play", "search", "send", "message", "text", "whatsapp")):
            self._pending_whatsapp_contact = contact_only
            self._pending_whatsapp_message = ""
            return f"What message should I send to {contact_only}, {USER_NAME}?"

        # Prefer direct WhatsApp message execution over planner/app-open heuristics.
        if self._looks_like_whatsapp_message(text_lower):
            params = self._extract_params("whatsapp_msg", text_lower, text)
            if params.get("contact") and params.get("message"):
                log.info(f"Intent: 'whatsapp_msg'  Params: {params}")
                return self._execute("whatsapp_msg", params, text, voice_mode=voice_mode)

        if self._looks_like_whatsapp_call(text_lower):
            intent = "whatsapp_video_call" if "video call" in text_lower or "videochat" in text_lower or "video chat" in text_lower else "whatsapp_call"
            params = self._extract_params(intent, text_lower, text)
            if params.get("contact"):
                log.info(f"Intent: {intent!r}  Params: {params}")
                return self._execute(intent, params, text, voice_mode=voice_mode)

        if self._looks_like_joke_request(text_lower):
            return self._execute("tell_joke", {"raw": text}, text, voice_mode=voice_mode)

        if self._looks_like_comfort_request(text_lower):
            return self._execute("comfort_support", {"raw": text}, text, voice_mode=voice_mode)

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
            return self.execute_intent(intent, params, text, voice_mode=voice_mode)

        return self._chat_with_memory(text, voice_mode=voice_mode)

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
        if self._looks_like_profile_save(low):
            return "save_profile", self._extract_params("save_profile", low, original)
        if self._looks_like_profile_show(low):
            return "show_profile", self._extract_params("show_profile", low, original)
        if self._looks_like_project_save(low):
            return "save_project_memory", self._extract_params("save_project_memory", low, original)
        if self._looks_like_project_show(low):
            return "show_project_memory", self._extract_params("show_project_memory", low, original)
        if self._looks_like_project_list(low):
            return "list_projects", self._extract_params("list_projects", low, original)
        if self._looks_like_workflow_save(low):
            return "save_workflow", self._extract_params("save_workflow", low, original)
        if self._looks_like_workflow_run(low):
            return "run_workflow", self._extract_params("run_workflow", low, original)
        if self._looks_like_workflow_list(low):
            return "list_workflows", self._extract_params("list_workflows", low, original)
        if self._looks_like_mission_start(low):
            return "start_mission", self._extract_params("start_mission", low, original)
        if self._looks_like_mission_show(low):
            return "show_mission", self._extract_params("show_mission", low, original)
        if self._looks_like_mission_list(low):
            return "list_missions", self._extract_params("list_missions", low, original)
        if self._looks_like_mission_complete(low):
            return "complete_mission", self._extract_params("complete_mission", low, original)
        if self._looks_like_knowledge_ingest(low):
            return "ingest_knowledge_file", self._extract_params("ingest_knowledge_file", low, original)
        if self._looks_like_knowledge_list(low):
            return "list_knowledge_files", self._extract_params("list_knowledge_files", low, original)
        if self._looks_like_brain_status(low):
            return "brain_status", self._extract_params("brain_status", low, original)
        if self._looks_like_recent_file_open_request(low):
            return "open_recent_file", self._extract_params("open_recent_file", low, original)
        if self._looks_like_document_creation_request(low):
            return "create_file", self._extract_params("create_file", low, original)
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

    def _looks_like_joke_request(self, low: str) -> bool:
        return bool(
            "joke" in low
            or "jokes" in low
            or "make me laugh" in low
            or "something funny" in low
        )

    def _looks_like_comfort_request(self, low: str) -> bool:
        phrases = [
            "not feeling good",
            "don't feeling good",
            "dont feeling good",
            "don't feel good",
            "dont feel good",
            "feeling low",
            "feeling sad",
            "i am sad",
            "i'm sad",
            "i am stressed",
            "i'm stressed",
            "i am anxious",
            "i'm anxious",
        ]
        return any(phrase in low for phrase in phrases)

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

    def _looks_like_recent_file_open_request(self, low: str) -> bool:
        if "open" not in low:
            return False
        phrases = [
            "open it",
            "open that",
            "open the file",
            "the file you created",
            "the file you create",
            "open recent file",
            "last file",
        ]
        if any(phrase in low for phrase in phrases):
            return True
        if "resume" in low and ("open" in low or "created" in low):
            return True
        return low.startswith("the file ") and "open" in low

    def _looks_like_document_creation_request(self, low: str) -> bool:
        if any(
            word in low
            for word in [
                "email",
                "mail",
                "gmail",
                "script",
                "code",
                "python",
                "terminal",
                "command",
                "todo",
                "to-do",
                "note that",
                "whatsapp",
            ]
        ):
            return False

        create_signals = ["create", "make", "write", "draft", "prepare", "generate"]
        document_signals = [
            "word file",
            "word document",
            "docx",
            "document",
            "essay",
            "report",
            "letter",
            "resume",
            "cv",
            "curriculum vitae",
            "biodata",
            "bio data",
        ]

        if any(signal in low for signal in document_signals) and any(signal in low for signal in create_signals):
            return True

        if "essay" in low and re.search(r"\b\d+\s*words?\b", low):
            return True

        if len(low.split()) <= 4 and any(signal in low for signal in ("resume", "cv", "biodata", "bio data")):
            return True

        return False

    def _learn_from_user_text(self, text: str):
        memory = self.tools.get("memory")
        if not memory or not hasattr(memory, "learn_profile_from_text"):
            return
        try:
            learned = memory.learn_profile_from_text(text)
            if learned:
                log.info("Learned profile details from conversation: %s", " | ".join(learned))
        except Exception as exc:
            log.warning(f"Profile auto-learn skipped: {exc}")

    def _looks_like_profile_save(self, low: str) -> bool:
        return bool(
            re.search(r"\b(?:remember|save)\s+profile\b", low)
            or low.startswith("my profile is ")
        )

    def _looks_like_profile_show(self, low: str) -> bool:
        return bool(
            re.search(r"\b(?:show|list)\s+(?:my\s+)?profile\b", low)
            or "what is in my profile" in low
        )

    def _looks_like_project_save(self, low: str) -> bool:
        return bool(re.search(r"\b(?:save|remember|update)\s+project\b", low))

    def _looks_like_project_show(self, low: str) -> bool:
        return bool(
            re.search(r"\b(?:show|open)\s+project\b", low)
            or "project details for" in low
            or "what do you know about project" in low
        )

    def _looks_like_project_list(self, low: str) -> bool:
        return bool(re.search(r"\b(?:list|show)\s+projects\b", low) or "my projects" in low)

    def _looks_like_workflow_save(self, low: str) -> bool:
        return bool(re.search(r"\b(?:save|remember|create)\s+workflow\b", low))

    def _looks_like_workflow_run(self, low: str) -> bool:
        return bool(re.search(r"\b(?:run|start|execute)\s+workflow\b", low))

    def _looks_like_workflow_list(self, low: str) -> bool:
        return bool(re.search(r"\b(?:list|show)\s+workflows\b", low) or "my workflows" in low)

    def _looks_like_mission_start(self, low: str) -> bool:
        return bool(re.search(r"\b(?:start|create|save)\s+mission\b", low))

    def _looks_like_mission_show(self, low: str) -> bool:
        return bool(
            re.search(r"\b(?:show)\s+mission\b", low)
            or "mission details" in low
            or "active mission" in low
            or "current mission" in low
        )

    def _looks_like_mission_list(self, low: str) -> bool:
        return bool(re.search(r"\b(?:list|show)\s+missions\b", low) or "my missions" in low)

    def _looks_like_mission_complete(self, low: str) -> bool:
        return bool(re.search(r"\b(?:complete|finish|close)\s+mission\b", low))

    def _looks_like_knowledge_ingest(self, low: str) -> bool:
        return bool(
            re.search(r"\b(?:learn|ingest|import|remember)\s+(?:knowledge\s+)?file\b", low)
            or "remember this file" in low
        )

    def _looks_like_knowledge_list(self, low: str) -> bool:
        return bool(
            re.search(r"\b(?:list|show)\s+(?:knowledge|brain)\s+files\b", low)
            or "knowledge files" in low
        )

    def _looks_like_brain_status(self, low: str) -> bool:
        return "brain status" in low or "memory status" in low or "knowledge status" in low

    def _looks_like_folder_open(self, low: str) -> bool:
        if "open " not in low:
            return False
        return any(folder in low for folder in ["downloads", "desktop", "documents", "pictures", "music", "videos", "workspace", "folder"])

    def _handle_pending_whatsapp_follow_up(self, text: str, voice_mode: bool = False):
        low = (text or "").lower().strip()
        if not low:
            return None

        if low in {"cancel", "never mind", "forget it", "abort"}:
            if self._pending_whatsapp_contact or self._pending_whatsapp_message:
                self._clear_pending_whatsapp()
                return f"Cancelled, {USER_NAME}."
            return None

        if self._pending_whatsapp_contact:
            intent, _ = self.detect_intent(text)
            if intent and intent != "whatsapp_msg":
                self._clear_pending_whatsapp()
                return None
            if intent == "whatsapp_msg":
                fresh_params = self._extract_params("whatsapp_msg", low, text)
                if fresh_params.get("contact") and fresh_params.get("contact").lower() != self._pending_whatsapp_contact.lower():
                    self._clear_pending_whatsapp()
                    return None
            message = self._normalize_pending_message(text)
            if not message:
                return f"What should I send to {self._pending_whatsapp_contact}, {USER_NAME}?"
            contact = self._pending_whatsapp_contact
            self._clear_pending_whatsapp()
            return self._execute(
                "whatsapp_msg",
                {"contact": contact, "message": message, "raw": text},
                text,
                voice_mode=voice_mode,
            )

        if self._pending_whatsapp_message:
            intent, fresh_params = self.detect_intent(text)
            if intent == "whatsapp_msg" and fresh_params.get("contact") and fresh_params.get("message"):
                self._clear_pending_whatsapp()
                return None
            contact = self._resolve_whatsapp_contact_name(text)
            if contact:
                message = self._pending_whatsapp_message
                self._clear_pending_whatsapp()
                return self._execute(
                    "whatsapp_msg",
                    {"contact": contact, "message": message, "raw": text},
                    text,
                    voice_mode=voice_mode,
                )
            if intent and intent != "whatsapp_msg":
                self._clear_pending_whatsapp()
                return None
            return f"Who should I send that message to, {USER_NAME}?"

        return None

    def _normalize_pending_message(self, text: str) -> str:
        cleaned = (text or "").strip()
        for prefix in ("message ", "send ", "text ", "whatsapp ", "msg "):
            if cleaned.lower().startswith(prefix):
                cleaned = cleaned[len(prefix):].strip()
                break
        return cleaned.strip(" :,-")

    def _clear_pending_whatsapp(self):
        self._pending_whatsapp_contact = ""
        self._pending_whatsapp_message = ""

    def _known_whatsapp_contacts(self) -> list[str]:
        names = []
        memory = self.tools.get("memory")
        if memory:
            try:
                names.extend(item["name"] for item in memory.list_contacts(channel="whatsapp"))
            except Exception:
                pass
        if self._last_whatsapp_contact:
            names.append(self._last_whatsapp_contact.lower())
        deduped = []
        for name in names:
            clean = (name or "").strip().lower()
            if clean and clean not in deduped:
                deduped.append(clean)
        return deduped

    def _resolve_whatsapp_contact_name(self, text: str) -> str:
        candidate = (text or "").strip().lower()
        if not candidate:
            return ""
        contacts = self._known_whatsapp_contacts()
        if not contacts:
            return ""
        for saved in contacts:
            if candidate == saved:
                return saved.title()
        partial = ""
        if len(candidate) >= 4:
            partial = next((saved for saved in contacts if candidate in saved or saved in candidate), "")
        if partial:
            return partial.title()
        match = get_close_matches(candidate, contacts, n=1, cutoff=0.72)
        if match:
            return match[0].title()
        return ""

    def _split_known_contact_message(self, body: str) -> tuple[str, str]:
        clean_body = (body or "").strip()
        if not clean_body:
            return "", ""
        lower_body = clean_body.lower()
        contacts = sorted(self._known_whatsapp_contacts(), key=len, reverse=True)

        for saved in contacts:
            if lower_body == saved:
                return saved.title(), ""
            if lower_body.startswith(saved + " "):
                return saved.title(), clean_body[len(saved):].strip()

        tokens = clean_body.split()
        for size in range(min(4, len(tokens)), 0, -1):
            suffix = " ".join(tokens[-size:])
            resolved = self._resolve_whatsapp_contact_name(suffix)
            if resolved and len(tokens) > size:
                return resolved, " ".join(tokens[:-size]).strip()

        return "", ""

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
            if not p.get("contact"):
                body = re.sub(
                    r'^(?:please\s+)?(?:send\s+)?(?:whatsapp\s+)?(?:message|measage|text|msg)\s+',
                    "",
                    original,
                    flags=re.IGNORECASE,
                ).strip()
                contact_guess, message_guess = self._split_known_contact_message(body)
                if contact_guess:
                    p["contact"] = contact_guess
                    p["message"] = message_guess
            if not p.get("contact") or not p.get("message"):
                tokens = re.split(r'\b(?:message|measage|text|msg|whatsapp|send)\b', original, flags=re.IGNORECASE)
                cleaned = " ".join(t.strip() for t in tokens if t.strip()).strip()
                if " to " in cleaned.lower():
                    message, contact = re.split(r'\bto\b', cleaned, maxsplit=1, flags=re.IGNORECASE)
                    p["message"] = message.strip()
                    p["contact"] = self._clean_contact_name(contact)
                elif cleaned and not p.get("message"):
                    resolved_contact = self._resolve_whatsapp_contact_name(cleaned)
                    if resolved_contact:
                        p["contact"] = resolved_contact
                    else:
                        p["message"] = cleaned
            if not p.get("contact"):
                p["contact"] = self._resolve_whatsapp_contact_name(original)

        elif intent in ("whatsapp_call", "whatsapp_video_call"):
            stripped = re.sub(r'^(?:please\s+)?(?:whatsapp\s+)?(?:video call|voice call|audio call|call)\s+', "", original, flags=re.IGNORECASE).strip()
            stripped = re.sub(r'\bon whatsapp\b', "", stripped, flags=re.IGNORECASE).strip()
            pronouns = {"him", "her", "them", "that person"}
            if stripped.lower() in pronouns or not stripped:
                p["contact"] = self._last_whatsapp_contact
            else:
                p["contact"] = self._resolve_whatsapp_contact_name(stripped) or self._clean_contact_name(stripped)

        elif intent == "add_whatsapp_contact":
            match = re.search(
                r'(?:add|save|remember)\s+whatsapp\s+contact\s+(.+?)\s+(\+?\d[\d\s-]{7,}\d)\s*$',
                original,
                re.IGNORECASE,
            )
            if match:
                p["contact"] = self._clean_contact_name(match.group(1))
                p["phone"] = match.group(2).strip()

        elif intent == "save_profile":
            text = re.sub(r'^(?:remember|save)\s+profile(?:\s+that)?\s+', "", original, flags=re.IGNORECASE).strip()
            text = re.sub(r'^my\s+profile\s+is\s+', "", text, flags=re.IGNORECASE).strip()
            p["text"] = text.strip(" :-")

        elif intent == "show_profile":
            p["text"] = original

        elif intent == "save_project_memory":
            body = re.sub(r'^(?:save|remember|update)\s+project\s+', "", original, flags=re.IGNORECASE).strip()
            match = re.match(r'(.+?)(?:\s*[:|-]\s*|\s+that\s+|\s+is\s+)(.+)', body, flags=re.IGNORECASE)
            if match:
                p["name"] = match.group(1).strip(" ,.-")
                p["details"] = match.group(2).strip()
            else:
                p["name"] = body.strip(" ,.-")
                p["details"] = ""
            status_match = re.search(r'\bstatus\s*[:=-]?\s*([^;|]+)', p.get("details", ""), re.IGNORECASE)
            next_steps_match = re.search(r'\bnext\s+steps?\s*[:=-]?\s*([^;|]+)', p.get("details", ""), re.IGNORECASE)
            tags_match = re.search(r'\btags?\s*[:=-]?\s*([^;|]+)', p.get("details", ""), re.IGNORECASE)
            if status_match:
                p["status"] = status_match.group(1).strip(" ,.")
            if next_steps_match:
                p["next_steps"] = next_steps_match.group(1).strip(" ,.")
            if tags_match:
                p["tags"] = tags_match.group(1).strip(" ,.")
            cleaned_details = p.get("details", "")
            cleaned_details = re.sub(r'\bstatus\s*[:=-]?\s*[^;|]+', "", cleaned_details, flags=re.IGNORECASE)
            cleaned_details = re.sub(r'\bnext\s+steps?\s*[:=-]?\s*[^;|]+', "", cleaned_details, flags=re.IGNORECASE)
            cleaned_details = re.sub(r'\btags?\s*[:=-]?\s*[^;|]+', "", cleaned_details, flags=re.IGNORECASE)
            cleaned_details = re.sub(r'[|;]+', " ", cleaned_details)
            cleaned_details = re.sub(r'\s+', " ", cleaned_details).strip(" ,.-")
            if cleaned_details:
                p["details"] = cleaned_details

        elif intent == "save_workflow":
            body = re.sub(r'^(?:save|remember|create)\s+workflow\s+', "", original, flags=re.IGNORECASE).strip()
            match = re.match(r'(.+?)(?:\s*[:|-]\s*|\s+that\s+)(.+)', body, flags=re.IGNORECASE)
            if match:
                p["name"] = match.group(1).strip(" ,.-")
                steps_blob = match.group(2).strip()
            else:
                p["name"] = body.strip(" ,.-")
                steps_blob = ""
            if steps_blob:
                parts = re.split(r'\s*\|\s*|\s+\bthen\b\s+|\s+\band then\b\s+', steps_blob, flags=re.IGNORECASE)
                p["steps"] = [part.strip(" ,.-") for part in parts if part.strip(" ,.-")]
                p["description"] = " -> ".join(p["steps"][:2]) if p.get("steps") else ""

        elif intent == "run_workflow":
            name = re.sub(r'^(?:run|start|execute)\s+workflow\s+', "", original, flags=re.IGNORECASE).strip()
            p["name"] = name.strip(" ,.-")

        elif intent == "list_workflows":
            p["text"] = original

        elif intent == "start_mission":
            body = re.sub(r'^(?:start|create|save)\s+mission\s+', "", original, flags=re.IGNORECASE).strip()
            match = re.match(r'(.+?)(?:\s*[:|-]\s*|\s+that\s+|\s+to\s+)(.+)', body, flags=re.IGNORECASE)
            if match:
                p["name"] = match.group(1).strip(" ,.-")
                p["objective"] = match.group(2).strip()
            else:
                p["name"] = body.strip(" ,.-")
                p["objective"] = ""
            next_match = re.search(r'\bnext\s+action\s*[:=-]?\s*([^;|]+)', p.get("objective", ""), re.IGNORECASE)
            if next_match:
                p["next_action"] = next_match.group(1).strip(" ,.")
                p["objective"] = re.sub(r'\bnext\s+action\s*[:=-]?\s*[^;|]+', "", p["objective"], flags=re.IGNORECASE).strip(" |,.-")

        elif intent == "show_mission":
            if "active mission" in low or "current mission" in low:
                p["name"] = ""
                p["active"] = True
            else:
                name = re.sub(r'^(?:show\s+mission|mission\s+details)\s*', "", original, flags=re.IGNORECASE).strip()
                name = name.strip(" ,.-")
                if not name:
                    p["name"] = ""
                    p["active"] = True
                else:
                    p["name"] = name

        elif intent == "list_missions":
            p["text"] = original

        elif intent == "complete_mission":
            name = re.sub(r'^(?:complete|finish|close)\s+mission\s+', "", original, flags=re.IGNORECASE).strip()
            p["name"] = name.strip(" ,.-")

        elif intent == "show_project_memory":
            name = re.sub(
                r'^(?:show\s+project|project\s+details\s+for|what\s+do\s+you\s+know\s+about\s+project)\s+',
                "",
                original,
                flags=re.IGNORECASE,
            ).strip()
            p["name"] = name.strip(" ,.-")

        elif intent == "list_projects":
            p["text"] = original

        elif intent == "ingest_knowledge_file":
            path_text = re.sub(
                r'^(?:learn|ingest|import|remember)\s+(?:knowledge\s+)?file\s+',
                "",
                original,
                flags=re.IGNORECASE,
            ).strip()
            path_text = re.sub(r'^remember\s+this\s+file\s+', "", path_text, flags=re.IGNORECASE).strip()
            p["path"] = path_text.strip(" :")

        elif intent == "list_knowledge_files":
            p["text"] = original

        elif intent == "brain_status":
            p["text"] = original

        elif intent == "open_recent_file":
            p["query"] = original

        elif intent == "compose_email":
            # Extract: to, subject, body from natural speech
            # "write email to rahul@gmail.com subject meeting body let's meet at 5"
            # "send mail to Mom saying I'll be late"
            p["action"] = "send" if re.search(r'\bsend\s+(?:an?\s+)?(?:email|mail)\b', original, re.IGNORECASE) else "compose"
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
            if to_match and not p.get("body"):
                remainder = original
                remainder = re.sub(r'^(?:please\s+)?(?:send|write|compose|draft)\s+(?:an?\s+)?(?:email|mail)\s+', '', remainder, flags=re.IGNORECASE)
                remainder = re.sub(
                    r'^(?:to|for)\s+[\w._%+\-]+@[\w.\-]+\.[a-z]{2,}\s*',
                    '',
                    remainder,
                    flags=re.IGNORECASE,
                )
                remainder = re.sub(
                    r'^(?:to|for)\s+[A-Za-z]+(?:\s+[A-Za-z]+)?\s*',
                    '',
                    remainder,
                    flags=re.IGNORECASE,
                )
                remainder = re.sub(
                    r'\b(?:subject|about|regarding|re:?)\s+.+?(?:\s+(?:body|saying|that|message|content)|$)',
                    '',
                    remainder,
                    flags=re.IGNORECASE,
                ).strip(" ,:-")
                if remainder:
                    p["body"] = remainder

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
            for folder in ["downloads", "desktop", "documents", "pictures", "music", "videos", "workspace"]:
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
    def _execute(self, intent: str, params: dict, original: str, voice_mode: bool = False) -> str:
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
            if intent == "add_whatsapp_contact":
                contact = params.get("contact", "")
                phone = params.get("phone", "")
                if wa and contact and phone:
                    self._last_whatsapp_contact = contact
                    return wa.add_contact(contact, phone)
                return f"Tell me the contact name and phone number, {USER_NAME}."
            if intent == "list_whatsapp_contacts":
                if wa:
                    return wa.list_contacts()
                return f"WhatsApp contact manager is not available, {USER_NAME}."
            if intent == "save_profile":
                if memory:
                    return memory.save_profile_item(params.get("text", ""))
                return f"Memory manager is not available, {USER_NAME}."
            if intent == "show_profile":
                if memory:
                    return memory.profile_summary()
                return f"Memory manager is not available, {USER_NAME}."
            if intent == "save_project_memory":
                if memory:
                    return memory.save_project(
                        params.get("name", ""),
                        params.get("details", ""),
                        status=params.get("status", ""),
                        next_steps=params.get("next_steps", ""),
                        tags=params.get("tags", ""),
                    )
                return f"Project memory is not available, {USER_NAME}."
            if intent == "show_project_memory":
                if memory:
                    project = memory.get_project(params.get("name", ""))
                    if not project:
                        return f"I couldn't find that project in memory, {USER_NAME}."
                    parts = [
                        f"Project: {project['name']}",
                        f"Summary: {project['summary']}",
                    ]
                    if project.get("status"):
                        parts.append(f"Status: {project['status']}")
                    if project.get("next_steps"):
                        parts.append(f"Next steps: {project['next_steps']}")
                    if project.get("tags"):
                        parts.append(f"Tags: {project['tags']}")
                    if project.get("details") and project["details"] != project["summary"]:
                        parts.append(f"Details: {project['details']}")
                    return "\n".join(parts)
                return f"Project memory is not available, {USER_NAME}."
            if intent == "list_projects":
                if memory:
                    projects = memory.list_projects()
                    if not projects:
                        return f"No projects saved yet, {USER_NAME}."
                    lines = []
                    for item in projects[:10]:
                        line = f"- {item['name']}: {item['summary']}"
                        if item.get("status"):
                            line += f" | Status: {item['status']}"
                        lines.append(line)
                    return "Tracked projects:\n" + "\n".join(lines)
                return f"Project memory is not available, {USER_NAME}."
            if intent == "save_workflow":
                if memory:
                    return memory.save_workflow(
                        params.get("name", ""),
                        params.get("steps", []),
                        description=params.get("description", ""),
                    )
                return f"Workflow memory is not available, {USER_NAME}."
            if intent == "run_workflow":
                if memory:
                    return self._run_saved_workflow(memory, params.get("name", ""))
                return f"Workflow engine is not available, {USER_NAME}."
            if intent == "list_workflows":
                if memory:
                    workflows = memory.list_workflows()
                    if not workflows:
                        return f"No workflows saved yet, {USER_NAME}."
                    lines = []
                    for item in workflows[:10]:
                        line = f"- {item['name']}"
                        if item["description"]:
                            line += f": {item['description']}"
                        if item["last_run"]:
                            line += f" | Last run: {item['last_run']}"
                        lines.append(line)
                    return "Saved workflows:\n" + "\n".join(lines)
                return f"Workflow memory is not available, {USER_NAME}."
            if intent == "start_mission":
                if memory:
                    objective = params.get("objective", "")
                    name = params.get("name", "")
                    plan = self.planner._split_task(objective) if self.planner and objective else []
                    return memory.save_mission(
                        name,
                        objective,
                        next_action=params.get("next_action", ""),
                        plan=plan,
                        status="active",
                    )
                return f"Mission memory is not available, {USER_NAME}."
            if intent == "show_mission":
                if memory:
                    mission = memory.get_active_mission() if params.get("active") else memory.get_mission(params.get("name", ""))
                    if not mission:
                        return f"I couldn't find that mission, {USER_NAME}."
                    parts = [
                        f"Mission: {mission['name']}",
                        f"Objective: {mission['objective']}",
                        f"Status: {mission['status']}",
                    ]
                    if mission.get("next_action"):
                        parts.append(f"Next action: {mission['next_action']}")
                    if mission.get("plan"):
                        parts.append("Plan: " + " | ".join(mission["plan"][:6]))
                    if mission.get("notes"):
                        parts.append(f"Notes: {mission['notes']}")
                    return "\n".join(parts)
                return f"Mission memory is not available, {USER_NAME}."
            if intent == "list_missions":
                if memory:
                    missions = memory.list_missions()
                    if not missions:
                        return f"No missions saved yet, {USER_NAME}."
                    lines = []
                    for item in missions[:10]:
                        line = f"- {item['name']}: {item['objective']} | Status: {item['status']}"
                        if item["next_action"]:
                            line += f" | Next: {item['next_action']}"
                        lines.append(line)
                    return "Mission board:\n" + "\n".join(lines)
                return f"Mission memory is not available, {USER_NAME}."
            if intent == "complete_mission":
                if memory:
                    return memory.complete_mission(params.get("name", ""))
                return f"Mission memory is not available, {USER_NAME}."
            if intent == "ingest_knowledge_file":
                if not files or not memory:
                    return f"Knowledge ingestion is not available, {USER_NAME}."
                path, content = files.extract_text(params.get("path", ""), max_chars=8000)
                if not path:
                    return content
                if not content or not content.strip():
                    return f"I couldn't extract usable text from {params.get('path', 'that file')}, {USER_NAME}."
                return memory.save_knowledge_document(path.stem, str(path), content)
            if intent == "list_knowledge_files":
                if memory:
                    docs = memory.list_knowledge_documents()
                    if not docs:
                        return (
                            f"No knowledge files saved yet, {USER_NAME}. "
                            f"Drop files into {KNOWLEDGE_DIR} and say 'learn file <name>'."
                        )
                    lines = [f"- {item['title']}: {item['source_path']}" for item in docs[:10]]
                    return "Knowledge files:\n" + "\n".join(lines)
                return f"Knowledge library is not available, {USER_NAME}."
            if intent == "brain_status":
                if memory:
                    stats = memory.brain_overview()
                    return (
                        f"Brain status, {USER_NAME}:\n"
                        f"- Profile entries: {stats['profile_entries']}\n"
                        f"- Projects: {stats['projects']}\n"
                        f"- Knowledge files: {stats['knowledge_docs']}\n"
                        f"- Workflows: {stats['workflows']}\n"
                        f"- Missions: {stats['missions']}\n"
                        f"- Contacts: {stats['contacts']}\n"
                        f"- Notes: {stats['notes']}\n"
                        f"- Facts: {stats['facts']}\n"
                        f"- Conversations stored: {stats['history']}\n"
                        f"- Active mission: {stats['active_mission'] or 'none'}\n"
                        f"- Operator mode: {'enabled' if OPERATOR_MODE else 'disabled'}\n"
                        f"- Memory DB: {stats['db_path']}\n"
                        f"- Knowledge folder: {KNOWLEDGE_DIR}"
                    )
                return f"Brain status is unavailable, {USER_NAME}."
            if intent == "compose_email":
                to      = params.get("to", "")
                subject = params.get("subject", "")
                body    = params.get("body", "")
                action  = params.get("action", "compose")
                if action == "send" and hasattr(browser, "send_gmail"):
                    return browser.send_gmail(to=to, subject=subject, body=body)
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
            if intent == "open_recent_file":
                return files.open_recent_file(params.get("query", original))
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
                return self.ai.chat(original, voice_mode=voice_mode)

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
                return self.ai.chat(original, voice_mode=voice_mode)

            if intent == "tell_joke":
                jokes = [
                    "Why do programmers prefer dark mode? Because light attracts bugs.",
                    "I told my laptop to take a break. It said it needed one byte.",
                    "Why did the browser go to therapy? Too many tabs open.",
                    "I would tell you a UDP joke, but you might not get it.",
                    "Why was the computer cold? It left its Windows open.",
                ]
                if voice_mode:
                    return random.choice(jokes)
                picks = random.sample(jokes, k=min(3, len(jokes)))
                return "\n".join(picks)

            if intent == "comfort_support":
                if any(
                    phrase in original.lower()
                    for phrase in ("what can you do", "what you can do", "can you help", "help me")
                ):
                    return (
                        f"I'm here with you, {USER_NAME}. "
                        f"I can play calming music, open a breathing video, or just stay and talk."
                    )
                if browser:
                    return browser.play_youtube("calming music for stress relief")
                return (
                    f"I'm here with you, {USER_NAME}. "
                    f"Take a slow breath with me and tell me if you want music, breathing help, or just to talk."
                )

            # ── WhatsApp ────────────────────────────────
            if intent == "whatsapp_msg":
                contact = params.get("contact", "")
                message = params.get("message", "")
                if wa and contact and message:
                    self._clear_pending_whatsapp()
                    self._last_whatsapp_contact = contact
                    return wa.send_message(contact, message)
                if contact and not message:
                    self._pending_whatsapp_contact = contact
                    self._pending_whatsapp_message = ""
                    return f"What message should I send to {contact}, {USER_NAME}?"
                if message and not contact:
                    self._pending_whatsapp_message = message
                    self._pending_whatsapp_contact = ""
                    return f"Who should I send that message to, {USER_NAME}?"
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
                    return self.ai.chat(
                        f"Describe and analyze this screen content:\n{text}",
                        voice_mode=voice_mode,
                    )
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

        return self.ai.chat(original, voice_mode=voice_mode)

    def _run_saved_workflow(self, memory, name: str) -> str:
        workflow = memory.get_workflow(name)
        if not workflow:
            return f"I couldn't find that workflow, {USER_NAME}."

        previous_state = self._planner_active
        self._planner_active = True
        results = []
        try:
            for step in workflow["steps"]:
                intent, params = self.detect_intent(step)
                if intent:
                    result = self.execute_intent(intent, params, step)
                else:
                    result = self.ai.chat(step)
                results.append(result)
            memory.mark_workflow_run(workflow["name"])
        finally:
            self._planner_active = previous_state

        tail = " ".join(result for result in results[-2:] if result)
        if tail:
            return f"Workflow '{workflow['name']}' complete. {tail}"
        return f"Workflow '{workflow['name']}' complete, {USER_NAME}."

    def _chat_with_memory(self, text: str, voice_mode: bool = False) -> str:
        memory = self.tools.get("memory")
        if not memory:
            return self.ai.chat(text, voice_mode=voice_mode)

        context_parts = []

        memory_context = memory.build_context(
            text,
            max_items=VOICE_MEMORY_CONTEXT_ITEMS if voice_mode else 6,
        )
        if memory_context:
            context_parts.append(memory_context)

        recent_history = memory.get_history(limit=VOICE_HISTORY_ITEMS if voice_mode else 4)
        if recent_history:
            convo_lines = []
            tail_size = VOICE_HISTORY_ITEMS if voice_mode else 4
            for item in recent_history[-tail_size:]:
                convo_lines.append(f"User: {item['user']}")
                convo_lines.append(f"Jarvis: {item['jarvis']}")
            context_parts.append("Recent conversation:\n" + "\n".join(convo_lines))

        if voice_mode:
            context_parts.append(
                "Voice mode:\n"
                "- Reply in one short sentence for normal commands.\n"
                "- Keep confirmations ultra-brief.\n"
                "- Only give longer detail when the request truly needs it."
            )

        context = "\n\n".join(context_parts)
        return self.ai.chat(text, context=context, voice_mode=voice_mode)

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
