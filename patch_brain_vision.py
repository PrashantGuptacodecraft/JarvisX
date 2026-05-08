"""patch_brain_vision.py — wire chat_with_image into Brain.process()"""
import os, re

path = os.path.join(os.path.dirname(__file__), "brain", "core.py")
content = open(path, "r", encoding="utf-8").read()

# ── 1. Add _last_cam_image attribute to Brain.__init__ ───────────────────
OLD_INIT = '        self._last_whatsapp_contact = ""\n        self._pending_whatsapp_contact = ""\n        self._pending_whatsapp_message = ""'
NEW_INIT = (
    '        self._last_whatsapp_contact = ""\n'
    '        self._pending_whatsapp_contact = ""\n'
    '        self._pending_whatsapp_message = ""\n'
    '        self._last_cam_image = ""   # Path to last camera frame for vision queries'
)
if "_last_cam_image" in content:
    print("Step 1 already applied")
else:
    content = content.replace(OLD_INIT, NEW_INIT, 1)
    print("Step 1 done — _last_cam_image added to __init__")

# ── 2. Camera vision interception at top of process() ────────────────────
CAMERA_INJECT = '''
        # ── Camera vision: intercept queries about what camera sees ──────
        # Commands from UI: "look at camera image <path> and answer: <question>"
        import re as _re
        cam_match = _re.match(
            r'look at camera image (.+?) and answer:\\s*(.+)', text, _re.IGNORECASE | _re.DOTALL
        )
        if cam_match:
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
'''

TARGET_LINE = "        # Handle pending confirmation"
if "_camera_phrases" in content:
    print("Step 2 already applied")
else:
    content = content.replace(TARGET_LINE, CAMERA_INJECT + TARGET_LINE, 1)
    print("Step 2 done — camera vision interception added to process()")

open(path, "w", encoding="utf-8").write(content)
print("brain/core.py patched successfully")
