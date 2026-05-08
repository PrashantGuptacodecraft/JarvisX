"""patch_vision.py — insert chat_with_image into ai_client.py"""
import os

path = os.path.join(os.path.dirname(__file__), "brain", "ai_client.py")
content = open(path, "r", encoding="utf-8").read()

NEW_METHOD = r'''
    def chat_with_image(self, user_message: str, image_path: str, voice_mode: bool = False) -> str:
        """Send a REAL camera image to Gemini/OpenAI Vision and answer about what is visible."""
        import os as _os
        if not _os.path.exists(image_path):
            return self.chat(user_message, voice_mode=voice_mode)

        # ── Gemini Vision ────────────────────────────────────────────────
        if self.provider == "gemini" and self.client:
            try:
                from google.genai import types
                with open(image_path, "rb") as f:
                    image_bytes = f.read()
                ext = _os.path.splitext(image_path)[1].lower()
                mime = {".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                        ".png": "image/png", ".webp": "image/webp"}.get(ext, "image/jpeg")
                vision_note = (
                    "You are looking at a REAL live camera frame captured right now. "
                    "Describe and analyze EXACTLY what you genuinely see: actual objects, colors, "
                    "people, facial expressions, hair style, surroundings. "
                    "Be specific and truthful. Never invent or assume things not visible."
                )
                for model_name in self._gemini_models():
                    try:
                        contents = [types.Content(role="user", parts=[
                            types.Part(text=SYSTEM_PROMPT + "\n\n" + vision_note),
                            types.Part(inline_data=types.Blob(mime_type=mime, data=image_bytes)),
                            types.Part(text=user_message),
                        ])]
                        resp = self.client.models.generate_content(model=model_name, contents=contents)
                        reply = (resp.text or "").strip()
                        self._model = model_name
                        self.history.append({"role": "user",  "parts": [{"text": "[Camera] " + user_message}]})
                        self.history.append({"role": "model", "parts": [{"text": reply}]})
                        return reply
                    except Exception as exc:
                        if self._classify_error(exc) != "bad_model":
                            raise
                        log.warning("Gemini vision model '%s' failed: %s", model_name, exc)
            except Exception as e:
                log.warning("Gemini vision failed: %s", e)

        # ── OpenAI / xAI Vision fallback ────────────────────────────────
        if self.provider in ("openai", "xai") and self.client:
            try:
                import base64
                with open(image_path, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode()
                ext = _os.path.splitext(image_path)[1].lower()
                mime = {".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                        ".png": "image/png"}.get(ext, "image/jpeg")
                data_url = "data:" + mime + ";base64," + b64
                messages = [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": [
                        {"type": "text", "text": user_message},
                        {"type": "image_url", "image_url": {"url": data_url}}
                    ]}
                ]
                resp = self.client.chat.completions.create(
                    model=self._provider_model_name(self.provider),
                    messages=messages,
                    max_tokens=VOICE_RESPONSE_MAX_TOKENS if voice_mode else 600,
                )
                reply = (resp.choices[0].message.content or "").strip()
                self.history.append({"role": "user",      "content": "[Camera] " + user_message})
                self.history.append({"role": "assistant", "content": reply})
                return reply
            except Exception as e:
                log.warning("OpenAI vision failed: %s", e)

        # ── Fallback ─────────────────────────────────────────────────────
        return self.chat(
            "The user asked about a camera image: " + repr(user_message) + ". "
            "Tell them honestly you cannot analyse the image right now and suggest "
            "they describe what they see.",
            voice_mode=voice_mode,
        )

'''

target = "    def think(self, task: str)"
if NEW_METHOD.strip()[:30] in content:
    print("chat_with_image already present — skipping")
else:
    content = content.replace(target, NEW_METHOD + target, 1)
    open(path, "w", encoding="utf-8").write(content)
    print("Done — chat_with_image inserted successfully")
