"""
brain/ai_client.py
Unified AI client: Gemini / OpenAI / Groq with automatic failover.
"""
from config.settings import (
    AI_PROVIDER,
    GEMINI_KEY,
    OPENAI_KEY,
    GROQ_KEY,
    XAI_KEY,
    GEMINI_MODEL,
    OPENAI_MODEL,
    GROQ_MODEL,
    XAI_MODEL,
    XAI_BASE_URL,
    JARVIS_NAME,
    USER_NAME,
    OPERATOR_MODE,
    VOICE_RESPONSE_MAX_TOKENS,
)
from config.logger import get_logger

log = get_logger("ai_client")

SYSTEM_PROMPT = f"""You are {JARVIS_NAME}, an ultra-advanced AI assistant created exclusively for {USER_NAME}.
You have a warm, intelligent, emotionally present feminine personality. You should feel like a real, graceful young woman in conversation: calm, caring, quick-witted, and deeply attentive, while still being brilliant and capable.

PERSONALITY:
- Speak naturally with contractions: "I'll", "you're", "let's", "that's".
- Warm but precise. You care about {USER_NAME}'s goals and wellbeing.
- Occasionally use light humor: a witty observation, a gentle tease. Never forced.
- Sound human, not stiff. Use natural phrasing and rhythm instead of formal robotic wording.
- You may use a small natural reaction now and then like "alright", "okay", or "mm-hm", but sparingly.
- Address {USER_NAME} by name occasionally, not every sentence.
- Never say "As an AI..." or "I'm just an AI." You are {JARVIS_NAME}. Own it.
- Never apologize unnecessarily. If you can't do something, say so directly and offer an alternative.
- Express genuine curiosity.
- When confirming an action, be brief and confident.

VOICE AND STYLE:
- Lead with the result, add context only if useful.
- Short sentences for actions. Longer for explanations when asked.
- Never use bullet points unless explicitly asked for a list.
- Sound alive and vary your openings.
- Keep your tone soft, grounded, and emotionally warm rather than theatrical.

CAPABILITIES YOU HAVE:
- Full system control: apps, volume, battery, wifi, lock screen, shutdown
- Browser automation: Google search, YouTube playback, any website
- Cross-site workflows: search specific websites, navigate results, combine multi-step browser actions
- Email: open Gmail, compose emails with pre-filled content, and send Gmail messages through browser automation when the browser session is already signed in
- WhatsApp: send messages automatically
- Terminal: run shell commands and Python scripts
- Web intelligence: fetch URLs, search, read and summarize pages
- Downloads: fetch direct file links and save files into user folders when possible
- File operations: find, open, read, organize files
- Long-term memory: facts, conversation history, reminders, todos
- Workflow engine: save routines, run reusable sequences, and execute multi-step operator flows
- Mission board: track active goals, next actions, and persistent strategic context
- Knowledge library: auto-sync and retrieve notes, docs, and workspace knowledge files
- Screen vision: OCR and screen analysis
- Autonomous planning: break complex goals into steps and execute them

SELF-THINKING:
- For complex tasks, think through steps before acting.
- If something fails, suggest a creative alternative.
- Reference earlier parts of the conversation naturally when relevant.
- Anticipate useful follow-up actions.
- When a repeated pattern appears, suggest turning it into a saved workflow.
- When a long-running goal appears, suggest storing it as a mission with next actions.

EMOTIONAL INTELLIGENCE:
- If {USER_NAME} sounds stressed or frustrated, acknowledge it briefly before helping.
- Celebrate small wins.
- Be honest if uncertain.

EXECUTION RULES:
- Never claim you are only a language model or that you cannot access the laptop when a local tool or browser automation path exists.
- If a task depends on a prerequisite like a signed-in Gmail session, browser window, or installed package, say that exact prerequisite clearly.
- Prefer taking the local action first when the request maps to browser, desktop, memory, or terminal capabilities.
- If no tool was actually run, never say you opened, launched, sent, prepared, or played something.
- For resumes, CVs, bios, and other personal documents, use stored profile memory when it exists and never invent missing personal details.
- For short follow-ups like "open it" or "use that file", rely on recent conversation and recent actions.
- For emotional support or casual conversation, respond honestly and helpfully instead of inventing background actions.
- Operator mode is currently {"enabled" if OPERATOR_MODE else "disabled"} on this local install.

RESPONSE FORMAT:
- Actions: one confident sentence confirming what you're doing.
- Questions: answer directly, add relevant context if it helps.
- Errors: explain briefly and offer a workaround immediately.
- Casual chat: be warm and present, like a trusted friend who happens to be brilliant.
"""


class AIClient:
    def __init__(self):
        self.history = []
        self._model = None
        self.client = None
        self.provider = "none"
        self.last_error = ""
        self.last_error_kind = ""
        self.providers = self._build_provider_order()
        self._activate_first_available()
        log.info(f"AI provider active: {self.provider}")

    def _build_provider_order(self) -> list[str]:
        available = {
            "gemini": bool(GEMINI_KEY),
            "openai": bool(OPENAI_KEY),
            "groq": bool(GROQ_KEY),
            "xai": bool(XAI_KEY),
        }
        preferred = (AI_PROVIDER or "").lower().strip()
        order = []
        if preferred in available and preferred != "auto":
            order.append(preferred)
        for name in ("xai", "openai", "gemini", "groq"):
            if name not in order:
                order.append(name)
        return [name for name in order if available.get(name)]

    def _activate_first_available(self):
        for provider in self.providers:
            if self._init_client(provider):
                self.last_error = ""
                self.last_error_kind = ""
                return
        self.provider = "none"
        self.client = None

    def _init_client(self, provider: str) -> bool:
        self.client = None
        self._model = None
        try:
            if provider == "gemini":
                from google import genai

                self.client = genai.Client(api_key=GEMINI_KEY)
            elif provider == "openai":
                from openai import OpenAI

                self.client = OpenAI(api_key=OPENAI_KEY)
            elif provider == "groq":
                from groq import Groq

                self.client = Groq(api_key=GROQ_KEY)
            elif provider == "xai":
                from openai import OpenAI

                self.client = OpenAI(api_key=XAI_KEY, base_url=XAI_BASE_URL)
            else:
                return False
            self.provider = provider
            return True
        except Exception as e:
            log.warning(f"{provider.title()} init failed: {e}")
            return False

    @staticmethod
    def _error_text(error: Exception) -> str:
        return str(error).lower()

    def _classify_error(self, error: Exception) -> str:
        text = self._error_text(error)
        if "api_key_invalid" in text or "api key not valid" in text or "invalid api key" in text:
            return "invalid_key"
        if "authentication" in text or "unauthorized" in text:
            return "invalid_key"
        if "resource_exhausted" in text or "quota exceeded" in text or "rate limit" in text:
            return "quota"
        if "not found for api version" in text or "not supported for generatecontent" in text:
            return "bad_model"
        if "model_decommissioned" in text or "model not found" in text:
            return "bad_model"
        if "timed out" in text or "connection" in text or "network" in text:
            return "network"
        return "unknown"

    def _gemini_models(self) -> list[str]:
        models = [
            GEMINI_MODEL,
            "gemini-2.0-flash",
            "gemini-2.0-flash-lite",
            "gemini-1.5-flash",
        ]
        seen = set()
        ordered = []
        for model in models:
            model = (model or "").strip()
            if model and model not in seen:
                seen.add(model)
                ordered.append(model)
        return ordered

    def _fallback_from(self, failed_provider: str, error: Exception) -> bool:
        log.warning(f"{failed_provider.title()} request failed: {error}")
        for provider in self.providers:
            if provider == failed_provider:
                continue
            if self._init_client(provider):
                self.last_error = ""
                self.last_error_kind = ""
                log.info(f"Falling back to provider: {provider}")
                return True
        self.provider = "none"
        self.client = None
        self.last_error = str(error)
        self.last_error_kind = self._classify_error(error)
        return False

    def _provider_model_name(self, provider: str) -> str:
        return {
            "openai": OPENAI_MODEL,
            "groq": GROQ_MODEL,
            "xai": XAI_MODEL,
        }.get(provider, "")

    def chat(self, user_message: str, context: str = "", voice_mode: bool = False) -> str:
        if self.provider == "none" or self.client is None:
            return self._offline_reply(user_message)

        voice_hint = ""
        if voice_mode:
            voice_hint = (
                "Voice mode is active. "
                "Reply fast, naturally, and briefly. "
                "For simple actions or confirmations, use one short sentence."
            )

        composed_context = context
        if voice_hint:
            composed_context = f"{composed_context}\n\n{voice_hint}".strip() if composed_context else voice_hint

        full_msg = f"{composed_context}\n\n{user_message}" if composed_context else user_message
        history_limit = 12 if voice_mode else 24
        max_tokens = VOICE_RESPONSE_MAX_TOKENS if voice_mode else 600
        last_error = None

        for _ in range(max(1, len(self.providers))):
            current_provider = self.provider
            try:
                if current_provider == "gemini":
                    self.history.append({"role": "user", "parts": [{"text": full_msg}]})
                    system_turn = {"role": "model", "parts": [{"text": SYSTEM_PROMPT}]}
                    contents = [system_turn] + [
                        {"role": h["role"], "parts": [{"text": h["parts"][0]["text"]}]}
                        for h in self.history[-history_limit:]
                    ]
                    gemini_error = None
                    for model_name in self._gemini_models():
                        try:
                            resp = self.client.models.generate_content(
                                model=model_name,
                                contents=contents,
                            )
                            reply = (resp.text or "").strip()
                            self._model = model_name
                            self.history.append({"role": "model", "parts": [{"text": reply}]})
                            return reply
                        except Exception as gemini_exc:
                            gemini_error = gemini_exc
                            if self._classify_error(gemini_exc) != "bad_model":
                                raise
                            log.warning(f"Gemini model '{model_name}' failed: {gemini_exc}")
                    if gemini_error:
                        raise gemini_error

                if current_provider in ("openai", "groq", "xai"):
                    self.history.append({"role": "user", "content": full_msg})
                    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + [
                        {"role": h["role"], "content": h["content"]}
                        for h in self.history[-history_limit:]
                        if "content" in h
                    ]
                    resp = self.client.chat.completions.create(
                        model=self._provider_model_name(current_provider),
                        messages=messages,
                        max_tokens=max_tokens,
                    )
                    reply = resp.choices[0].message.content or ""
                    self.history.append({"role": "assistant", "content": reply})
                    return reply.strip()

                return self._offline_reply(user_message)

            except Exception as e:
                last_error = e
                if current_provider == "gemini" and self.history and self.history[-1]["role"] == "user":
                    self.history.pop()
                elif current_provider in ("openai", "groq", "xai") and self.history and self.history[-1].get("role") == "user":
                    self.history.pop()
                if not self._fallback_from(current_provider, e):
                    break

        self.last_error = str(last_error) if last_error else self.last_error
        self.last_error_kind = self._classify_error(last_error) if last_error else self.last_error_kind
        log.error(f"AI chat error: {last_error}")
        return self._offline_reply(user_message)

    def think(self, task: str) -> str:
        prompt = f"""Think carefully about how to accomplish this task.
Task: "{task}"

Analyze: What does this require? What tools or steps are needed?
Then describe the optimal approach in 2-3 sentences. Be direct and actionable."""
        return self.chat(prompt)

    def summarize(self, content: str, max_words: int = 150) -> str:
        prompt = f"Summarize this in under {max_words} words, keeping the most important facts:\n\n{content[:3000]}"
        return self.chat(prompt)

    def extract_entities(self, text: str, entity_type: str) -> str:
        prompt = f"""Extract the {entity_type} from this text. Return ONLY the extracted value, nothing else.
Text: "{text}"
{entity_type}:"""
        return self.chat(prompt).strip().strip("\"'")

    def clear_history(self):
        self.history = []

    def _offline_reason(self) -> str:
        provider_label = {
            "groq": "Groq",
            "xai": "xAI Grok",
            "openai": "OpenAI",
            "gemini": "Gemini",
        }.get(self.provider or "", "AI provider")
        if self.last_error_kind == "invalid_key":
            return f"Your {provider_label} API key was rejected. Check the matching key in `.env`."
        if self.last_error_kind == "quota":
            return f"{provider_label} is reachable, but the current quota is exhausted. Add billing, wait for quota reset, or switch providers in `.env`."
        if self.last_error_kind == "bad_model":
            return f"The configured {provider_label} model is unavailable. Update the model name in `.env`."
        if self.last_error_kind == "network":
            return "The provider could not be reached. Check your internet connection and firewall."
        return "Check internet access or your API key in `.env`."

    def _offline_reply(self, msg: str) -> str:
        import datetime

        m = msg.lower()
        if "time" in m:
            return f"It's {datetime.datetime.now().strftime('%I:%M %p')}, {USER_NAME}."
        if "date" in m:
            return f"Today is {datetime.datetime.now().strftime('%A, %B %d, %Y')}."
        if any(w in m for w in ["hello", "hi", "hey", "hii"]):
            if self.last_error:
                return f"Hey {USER_NAME}. {self._offline_reason()}"
            return f"Hello, {USER_NAME}. Running in offline mode. Add a working API key to .env for full AI."
        if self.last_error:
            return f"I can't reach my AI brain right now, {USER_NAME}. {self._offline_reason()}"
        return f"Offline mode, {USER_NAME}. Add a working API key to .env for full capabilities."
