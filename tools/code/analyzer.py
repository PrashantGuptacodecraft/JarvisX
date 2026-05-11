"""
tools/code/analyzer.py
Proactive Code Intelligence Engine for JarvisX.

Watches workspace files with watchdog.
On change: diffs the file → sends to AI for code review.
Speaks proactive suggestions.
Voice trigger: "Jarvis, review this file"
"""
from __future__ import annotations
import os, time, threading, hashlib, logging
from typing import Optional, Callable

log = logging.getLogger("code_analyzer")

_WATCH_EXTENSIONS = {".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".cpp", ".c", ".go", ".rs"}
_REVIEW_COOLDOWN  = 30   # seconds between auto-reviews of same file
_MAX_SNIPPET      = 3000  # characters to send to AI


class CodeAnalyzer:
    """
    Watches source files and provides proactive AI code review.

    Usage:
        analyzer = CodeAnalyzer(ai_client, speaker, workspace_dir)
        analyzer.start()
        analyzer.review_file("path/to/file.py")  # manual trigger
        analyzer.stop()
    """

    def __init__(
        self,
        ai_client=None,
        speaker=None,
        workspace_dir: str = "",
        auto_review: bool = True,
    ):
        self.ai = ai_client
        self.speaker = speaker
        self.workspace_dir = workspace_dir or os.getcwd()
        self.auto_review = auto_review
        self.available: bool = False
        self._observer = None
        self._file_hashes: dict[str, str] = {}
        self._last_review: dict[str, float] = {}
        self._lock = threading.Lock()
        self._init_backend()

    def _init_backend(self):
        try:
            import watchdog  # noqa: F401
            self.available = True
            log.info("CodeAnalyzer: watchdog ready.")
        except ImportError:
            log.warning(
                "CodeAnalyzer: watchdog not installed. "
                "Run: pip install watchdog   (auto code review disabled)"
            )

    def start(self) -> str:
        if not self.available or not self.auto_review:
            return "Code analyzer not available." if not self.available else "Auto review disabled."
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler

            analyzer_ref = self

            class _Handler(FileSystemEventHandler):
                def on_modified(self, event):
                    if event.is_directory:
                        return
                    path = event.src_path
                    ext = os.path.splitext(path)[1].lower()
                    if ext in _WATCH_EXTENSIONS:
                        threading.Thread(
                            target=analyzer_ref._on_file_changed,
                            args=(path,), daemon=True,
                        ).start()

            self._observer = Observer()
            self._observer.schedule(_Handler(), self.workspace_dir, recursive=True)
            self._observer.start()
            log.info(f"CodeAnalyzer watching: {self.workspace_dir}")
            return f"Code intelligence active — watching {self.workspace_dir}"
        except Exception as e:
            log.error(f"CodeAnalyzer start failed: {e}")
            return f"Code analyzer failed to start: {e}"

    def stop(self):
        if self._observer:
            try:
                self._observer.stop()
                self._observer.join(timeout=2)
            except Exception:
                pass

    def review_file(self, filepath: str) -> str:
        """Manually trigger AI code review for a file."""
        if not self.ai:
            return "AI client not available for code review."
        try:
            if not os.path.exists(filepath):
                return f"File not found: {filepath}"
            with open(filepath, encoding="utf-8", errors="replace") as f:
                content = f.read()
            return self._analyse(filepath, content)
        except Exception as e:
            return f"Code review failed: {e}"

    def review_snippet(self, code: str, language: str = "Python") -> str:
        """Review a code snippet directly."""
        if not self.ai:
            return "AI client not available."
        return self._analyse_snippet(code, language)

    # ── Internal ───────────────────────────────────────────────────────────────

    def _on_file_changed(self, path: str):
        """Called when a watched file changes."""
        now = time.time()
        with self._lock:
            last = self._last_review.get(path, 0)
            if now - last < _REVIEW_COOLDOWN:
                return
            self._last_review[path] = now

        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                content = f.read()
            new_hash = hashlib.md5(content.encode()).hexdigest()
            with self._lock:
                old_hash = self._file_hashes.get(path, "")
                if new_hash == old_hash:
                    return
                self._file_hashes[path] = new_hash
        except Exception:
            return

        log.info(f"CodeAnalyzer: auto-reviewing {os.path.basename(path)}")
        result = self._analyse(path, content)
        if result and self.speaker and hasattr(self.speaker, "speak"):
            brief = result[:200].split(".")[0] + "."
            try:
                self.speaker.speak(brief, blocking=False)
            except Exception:
                pass

    def _analyse(self, filepath: str, content: str) -> str:
        if not self.ai:
            return ""
        snippet = content[:_MAX_SNIPPET]
        filename = os.path.basename(filepath)
        prompt = (
            f"You are reviewing the file '{filename}'. "
            f"Analyze this code for bugs, inefficiencies, security issues, "
            f"or style improvements. Be specific about line-level issues. "
            f"Keep response under 150 words.\n\n```\n{snippet}\n```"
        )
        try:
            return self.ai.chat(prompt)
        except Exception as e:
            return f"Code review error: {e}"

    def _analyse_snippet(self, code: str, language: str) -> str:
        if not self.ai:
            return ""
        prompt = (
            f"Review this {language} code snippet. "
            f"Identify bugs, improvements, or best practices. "
            f"Be specific and concise (under 120 words).\n\n```{language.lower()}\n{code[:_MAX_SNIPPET]}\n```"
        )
        try:
            return self.ai.chat(prompt)
        except Exception as e:
            return f"Code review error: {e}"
