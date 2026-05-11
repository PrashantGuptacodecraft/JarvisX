"""
brain/agents/researcher.py
ResearcherAgent: Searches the web + summarizes results for multi-agent tasks.
"""
from __future__ import annotations
import threading
import time
from config.logger import get_logger

log = get_logger("agent.researcher")


class ResearcherAgent:
    """Fetches and summarizes information from the web or memory."""

    def __init__(self, ai_client, web_controller=None, memory=None):
        self.ai = ai_client
        self.web = web_controller
        self.memory = memory
        self.result: str = ""
        self.done: bool = False
        self.error: str = ""

    def run(self, task: str) -> str:
        """Synchronous run — returns summarized research result."""
        self.done = False
        self.result = ""
        self.error = ""
        log.info(f"[Researcher] Task: {task[:80]}")
        try:
            # Try web search first
            if self.web and hasattr(self.web, "search"):
                try:
                    raw = self.web.search(task)
                    if raw and len(raw) > 50:
                        summarized = self.ai.summarize(raw, max_words=120)
                        self.result = summarized
                        self.done = True
                        return self.result
                except Exception as we:
                    log.warning(f"[Researcher] Web search failed: {we}")

            # Fallback: ask AI directly
            prompt = (
                f"Research the following topic thoroughly and summarize key findings "
                f"in 3-5 bullet points:\n\n{task}"
            )
            self.result = self.ai.chat(prompt)
            self.done = True
            return self.result
        except Exception as e:
            self.error = str(e)
            self.done = True
            log.error(f"[Researcher] Error: {e}")
            return f"Research failed: {e}"

    def run_async(self, task: str) -> threading.Thread:
        """Run research in a background thread."""
        t = threading.Thread(target=self.run, args=(task,), daemon=True)
        t.start()
        return t

    def wait(self, timeout: float = 15.0) -> str:
        """Wait for async result."""
        deadline = time.time() + timeout
        while not self.done and time.time() < deadline:
            time.sleep(0.1)
        return self.result
