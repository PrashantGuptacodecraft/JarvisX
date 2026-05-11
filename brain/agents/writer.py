"""
brain/agents/writer.py
WriterAgent: Generates structured documents, reports, emails, and content.
"""
from __future__ import annotations
import os
import threading
import time
from config.logger import get_logger
from config.settings import USER_NAME

log = get_logger("agent.writer")


class WriterAgent:
    """Generates documents and structured content from research."""

    def __init__(self, ai_client, memory=None):
        self.ai = ai_client
        self.memory = memory
        self.result: str = ""
        self.done: bool = False
        self.error: str = ""

    def run(self, task: str, context: str = "") -> str:
        """Synchronous run — returns generated content."""
        self.done = False
        self.result = ""
        self.error = ""
        log.info(f"[Writer] Task: {task[:80]}")
        try:
            profile_ctx = ""
            if self.memory and hasattr(self.memory, "profile_summary"):
                try:
                    profile_ctx = self.memory.profile_summary(limit=5)
                except Exception:
                    pass

            ctx_parts = []
            if profile_ctx and "No profile" not in profile_ctx:
                ctx_parts.append(f"User profile:\n{profile_ctx}")
            if context:
                ctx_parts.append(f"Research context:\n{context}")

            full_context = "\n\n".join(ctx_parts)
            prompt = (
                f"You are generating content for {USER_NAME}. "
                f"Task: {task}\n\n"
                f"{'Context:\n' + full_context if full_context else ''}\n\n"
                "Write clear, professional, well-structured content. "
                "Be comprehensive but concise."
            )
            self.result = self.ai.chat(prompt)
            self.done = True
            return self.result
        except Exception as e:
            self.error = str(e)
            self.done = True
            log.error(f"[Writer] Error: {e}")
            return f"Writing failed: {e}"

    def save_to_file(self, content: str, filename: str, save_dir: str = None) -> str:
        """Save generated content to a file."""
        if not save_dir:
            save_dir = os.path.join(os.path.expanduser("~"), "Documents", "JarvisX")
        os.makedirs(save_dir, exist_ok=True)
        filepath = os.path.join(save_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        log.info(f"[Writer] Saved: {filepath}")
        return filepath

    def run_async(self, task: str, context: str = "") -> threading.Thread:
        """Run writing in a background thread."""
        t = threading.Thread(target=self.run, args=(task, context), daemon=True)
        t.start()
        return t

    def wait(self, timeout: float = 20.0) -> str:
        """Wait for async result."""
        deadline = time.time() + timeout
        while not self.done and time.time() < deadline:
            time.sleep(0.1)
        return self.result
