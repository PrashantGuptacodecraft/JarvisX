"""patch_ask_camera_robust.py — make _ask_about_camera work even before first frame renders"""
import os

path = os.path.join(os.path.dirname(__file__), "ui", "interface.py")
content = open(path, "r", encoding="utf-8").read()

OLD = '''    def _ask_about_camera(self):
        """Capture current frame and ask JARVIS to analyze it."""
        question = self._cam_ask_var.get().strip()
        if not question:
            question = "What do you see? Describe everything in detail."

        if self._cam_last_img is None:
            self.show_notification("Camera", "Start the camera first so I can see something.")
            return

        # Save frame to temp file
        import os, tempfile
        frame_path = os.path.join(tempfile.gettempdir(), "jarvis_cam_ask.jpg")
        self._cam_last_img.save(frame_path)
        self._cam_ask_var.set("")

        # Build a command for the brain that includes the image path
        cmd = f"look at camera image {frame_path} and answer: {question}"
        self.add_user_message(f"[Camera] {question}")
        self.command_queue.put(cmd)
        self._cam_status_var.set("Analyzing frame...")'''

NEW = '''    def _ask_about_camera(self):
        """Capture current frame and ask JARVIS to analyze it."""
        import os as _os, tempfile
        question = self._cam_ask_var.get().strip()
        if not question:
            question = "What do you see? Describe everything in detail."

        # Try to grab the latest frame directly from the live capture
        if self._cam_cap and self._cam_running:
            try:
                import cv2
                ret, frame = self._cam_cap.read()
                if ret:
                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    from PIL import Image
                    self._cam_last_img = Image.fromarray(rgb)
                    self._cam_last_frame_raw = frame.copy()
            except Exception:
                pass

        if self._cam_last_img is None:
            if not self._cam_running:
                self.show_notification("Camera", "Start the camera first — press the START CAMERA button.")
            else:
                self.show_notification("Camera", "Camera is starting up, please wait a moment and try again.")
            return

        frame_path = _os.path.join(tempfile.gettempdir(), "jarvis_cam_ask.jpg")
        try:
            self._cam_last_img.save(frame_path)
        except Exception as e:
            self.show_notification("Camera", f"Could not save frame: {e}")
            return

        self._cam_ask_var.set("")
        cmd = "look at camera image " + frame_path + " and answer: " + question
        self.add_user_message("[Camera] " + question)
        self.command_queue.put(cmd)
        self._cam_status_var.set("Analyzing frame...")'''

if OLD in content:
    content = content.replace(OLD, NEW, 1)
    open(path, "w", encoding="utf-8").write(content)
    print("FIXED: _ask_about_camera — now captures fresh frame on demand")
else:
    print("Partial match search...")
    OLD_KEY = 'if self._cam_last_img is None:\n            self.show_notification("Camera", "Start the camera first so I can see something.")\n            return'
    if OLD_KEY in content:
        content = content.replace(OLD_KEY,
            'if self._cam_last_img is None:\n'
            '            if not self._cam_running:\n'
            '                self.show_notification("Camera", "Start the camera first \u2014 press START CAMERA.")\n'
            '            else:\n'
            '                self.show_notification("Camera", "Camera is warming up, try again in a second.")\n'
            '            return', 1)
        open(path, "w", encoding="utf-8").write(content)
        print("PARTIAL FIX: ask_about_camera null check improved")
    else:
        print("Could not find target — check interface.py manually")
