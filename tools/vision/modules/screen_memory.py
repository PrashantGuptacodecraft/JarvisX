"""
tools/vision/modules/screen_memory.py
AR Screen Memory — JarvisX continuous screen capture + AI indexing.

Takes a screenshot every N seconds, sends to vision AI for semantic tagging,
stores in memory as searchable episodes.

Voice query: "Jarvis, find that code I was looking at" → semantic search.
"""
from __future__ import annotations
import os
import time
import threading
import tempfile
import logging
from pathlib import Path
from typing import Optional

log = logging.getLogger("screen_memory")

_DEFAULT_INTERVAL = 60   # seconds between captures
_MAX_STORED = 200        # max episodes to keep


class ScreenMemory:
    """
    Background screen capture + AI tagging service.

    Usage:
        sm = ScreenMemory(ai_client, memory_manager)
        sm.start()
        sm.stop()
        results = sm.search("python code error")
    """

    def __init__(
        self,
        ai_client=None,
        memory=None,
        interval: float = _DEFAULT_INTERVAL,
        save_screenshots: bool = False,
    ):
        self.ai = ai_client
        self.memory = memory
        self.interval = interval
        self.save_screenshots = save_screenshots

        self.available: bool = False
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._capture_count = 0

        self._init_backend()

    def _init_backend(self):
        try:
            import PIL.ImageGrab  # noqa: F401
            self.available = True
            log.info("ScreenMemory: PIL ImageGrab ready.")
        except ImportError:
            log.warning("ScreenMemory: Pillow not installed. Run: pip install Pillow")

    def start(self):
        if not self.available or not self.ai:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="screen-memory"
        )
        self._thread.start()
        log.info(f"ScreenMemory started (interval={self.interval}s).")

    def stop(self):
        self._running = False

    def capture_now(self) -> str:
        """Manually trigger a screen capture and return the tags/description."""
        if not self.available:
            return "Screen memory not available."
        try:
            path, desc = self._capture_and_tag()
            return desc or "Screen captured."
        except Exception as e:
            return f"Capture failed: {e}"

    def search(self, query: str) -> str:
        """Search screen memory episodes for a query."""
        if not self.memory:
            return "Screen memory search requires memory manager."
        try:
            if hasattr(self.memory, "search_episodes"):
                results = self.memory.search_episodes(query, source="screen", limit=5)
                if not results:
                    return "Nothing found in screen memory for that query."
                lines = []
                for ep in results[:3]:
                    ts = ep.get("timestamp", "")[:16].replace("T", " ")
                    desc = ep.get("description", "")[:120]
                    lines.append(f"[{ts}] {desc}")
                return "Screen memory results:\n" + "\n".join(lines)
            return "Screen memory search not yet indexed."
        except Exception as e:
            return f"Search failed: {e}"

    # ── Internal ───────────────────────────────────────────────────────────────

    def _loop(self):
        """Background capture loop."""
        while self._running:
            time.sleep(self.interval)
            if not self._running:
                break
            try:
                self._capture_and_tag()
            except Exception as e:
                log.debug(f"ScreenMemory capture error: {e}")

    def _capture_and_tag(self):
        """Capture screen → AI tag → store in memory."""
        import PIL.ImageGrab

        # Capture screenshot
        screen = PIL.ImageGrab.grab()
        tmppath = os.path.join(tempfile.gettempdir(), "jarvis_screen_mem.jpg")
        screen.save(tmppath, "JPEG", quality=70)

        # Save screenshot if requested
        if self.save_screenshots:
            save_dir = Path(__file__).resolve().parent.parent.parent.parent / "data" / "screen_memory"
            save_dir.mkdir(parents=True, exist_ok=True)
            ts = time.strftime("%Y%m%d_%H%M%S")
            screen.save(str(save_dir / f"screen_{ts}.jpg"), "JPEG", quality=60)

        # AI tagging
        description = ""
        if self.ai:
            try:
                description = self.ai.chat_with_image(
                    "Describe this screen capture in 2-3 sentences. "
                    "Focus on: what app is open, what content is visible, "
                    "key text or code visible, and what the user appears to be doing. "
                    "Be specific and factual.",
                    tmppath,
                )
                description = (description or "").strip()[:500]
            except Exception as e:
                log.debug(f"ScreenMemory AI tag error: {e}")

        # Store episode in memory
        if self.memory and description:
            try:
                if hasattr(self.memory, "add_episode"):
                    self.memory.add_episode(
                        description=description,
                        source="screen",
                        tags=self._extract_tags(description),
                    )
            except Exception as e:
                log.debug(f"ScreenMemory store error: {e}")

        self._capture_count += 1
        log.debug(f"ScreenMemory captured #{self._capture_count}: {description[:60]}")
        return tmppath, description

    @staticmethod
    def _extract_tags(description: str) -> str:
        """Extract simple keyword tags from description."""
        keywords = []
        desc_lower = description.lower()
        tag_words = [
            "python", "code", "error", "browser", "chrome", "firefox",
            "vscode", "terminal", "excel", "word", "email", "youtube",
            "github", "whatsapp", "file", "folder", "image", "video",
        ]
        for word in tag_words:
            if word in desc_lower:
                keywords.append(word)
        return ",".join(keywords[:8])
