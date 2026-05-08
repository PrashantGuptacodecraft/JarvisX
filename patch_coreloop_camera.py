"""patch_coreloop_camera.py — wire camera snapshot into core_loop voice commands"""
import os, re

path = os.path.join(os.path.dirname(__file__), "core_loop.py")
content = open(path, "r", encoding="utf-8").read()

CAMERA_VOICE_INTERCEPT = """
        # ── Camera voice command intercept ──────────────────────────────
        _cam_snap_phrases = [
            "click a photo", "take a photo", "take photo", "click photo",
            "capture photo", "take a picture", "click a picture",
            "take picture", "capture image", "take snapshot",
        ]
        _cam_question_phrases = [
            "what do you see", "what can you see", "look at me",
            "what's in camera", "what is in camera", "describe what you see",
            "what the object", "what in picture", "what object",
            "my expression", "my face", "how do i look", "my hair",
            "suggest hairstyle", "suggest hair", "analyze my face",
            "what am i wearing", "what other things", "what around",
        ]
        cmd_low = command.lower()
        _cam_frame_path = os.path.join(
            __import__("tempfile").gettempdir(), "jarvis_cam_ask.jpg"
        )
        _has_live_frame = os.path.exists(_cam_frame_path)

        # Snapshot request via voice → capture frame from GUI camera
        if any(ph in cmd_low for ph in _cam_snap_phrases):
            if self.gui and hasattr(self.gui, "_cam_last_img") and self.gui._cam_last_img:
                self.gui._cam_last_img.save(_cam_frame_path)
                self.brain._last_cam_image = _cam_frame_path
                _has_live_frame = True
                response = f"Got it — I've captured the photo, {USER_NAME}. What would you like to know about it?"
                if self.gui:
                    self.gui.add_jarvis_message(response)
                self._deliver_reply(response, turn_token)
                return
            elif self.gui and not (hasattr(self.gui, "_cam_running") and self.gui._cam_running):
                response = f"The camera isn't open yet, {USER_NAME}. Click the CAMERA tab and press START CAMERA first."
                if self.gui:
                    self.gui.add_jarvis_message(response)
                self._deliver_reply(response, turn_token)
                return

        # Camera question via voice → use last frame for vision
        if any(ph in cmd_low for ph in _cam_question_phrases) and _has_live_frame:
            # Auto-capture latest frame if camera is running
            if self.gui and hasattr(self.gui, "_cam_last_img") and self.gui._cam_last_img:
                self.gui._cam_last_img.save(_cam_frame_path)
                self.brain._last_cam_image = _cam_frame_path
            if hasattr(self.brain, "_last_cam_image") and self.brain._last_cam_image:
                if self.gui:
                    self.gui.set_status("thinking")
                try:
                    response = self.brain.ai.chat_with_image(command, self.brain._last_cam_image, voice_mode=voice_source)
                except Exception as exc:
                    log.error(f"Vision query error: {exc}")
                    response = f"I couldn't analyze the camera image, {USER_NAME}: {exc}"
                if self.memory:
                    self.memory.add_history(command, response)
                if self.gui:
                    self.gui.add_jarvis_message(response)
                self._deliver_reply(response, turn_token)
                return
        # ── End camera voice intercept ───────────────────────────────────
"""

TARGET = "        if self.gui:\n            self.gui.set_status(\"thinking\")\n            self.gui.add_user_message(command)"
if "_cam_snap_phrases" in content:
    print("Camera intercept already present — skipping")
else:
    # Add 'import os' at top if missing
    if "import os" not in content:
        content = content.replace("import queue\n", "import os\nimport queue\n", 1)
        print("Added 'import os'")
    content = content.replace(TARGET, CAMERA_VOICE_INTERCEPT + TARGET, 1)
    open(path, "w", encoding="utf-8").write(content)
    print("core_loop.py patched — camera voice intercept added")
