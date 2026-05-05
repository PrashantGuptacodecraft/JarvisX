"""tools/files/controller.py - File operations."""

import os
import subprocess
import sys
from pathlib import Path

from config.logger import get_logger
from config.settings import USER_NAME, WORKSPACE_DIR

log = get_logger("files")
IS_WIN = sys.platform == "win32"

FOLDERS = {
    "downloads": Path.home() / "Downloads",
    "desktop": Path.home() / "Desktop",
    "documents": Path.home() / "Documents",
    "pictures": Path.home() / "Pictures",
    "music": Path.home() / "Music",
    "videos": Path.home() / "Videos",
    "workspace": WORKSPACE_DIR,
}

TYPE_MAP = {
    "Images": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg"],
    "Videos": [".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv"],
    "Documents": [".pdf", ".docx", ".doc", ".txt", ".xlsx", ".pptx", ".csv", ".md"],
    "Music": [".mp3", ".wav", ".flac", ".aac", ".ogg"],
    "Archives": [".zip", ".rar", ".7z", ".tar", ".gz"],
    "Code": [".py", ".js", ".html", ".css", ".java", ".cpp", ".ts"],
}


class FilesController:
    def _resolve_path(self, path_or_query: str) -> Path:
        candidate = Path((path_or_query or "").strip().strip("\"'"))
        search_roots = list(FOLDERS.values()) + [Path.home(), Path.cwd()]

        if candidate.exists():
            return candidate

        if not candidate.is_absolute():
            for root in (Path.cwd(), WORKSPACE_DIR):
                joined = root / candidate
                if joined.exists():
                    return joined

        needle = candidate.name if candidate.name else str(candidate)
        for root in search_roots:
            if not root.exists():
                continue
            for found in root.rglob(f"*{needle}*"):
                return found
        return candidate

    def extract_text(self, path_or_query: str, max_chars: int = 4000) -> tuple[Path | None, str]:
        path = self._resolve_path(path_or_query)
        if not path.exists() or not path.is_file():
            return None, f"File not found, {USER_NAME}."

        try:
            ext = path.suffix.lower()
            if ext == ".pdf":
                import fitz

                doc = fitz.open(str(path))
                text = "".join(page.get_text() for page in doc)
            elif ext in (".docx", ".doc"):
                from docx import Document

                doc = Document(str(path))
                text = "\n".join(paragraph.text for paragraph in doc.paragraphs)
            else:
                text = path.read_text(encoding="utf-8", errors="ignore")
            return path, text[:max_chars]
        except Exception as e:
            return None, f"Couldn't read file: {e}"

    def find_file(self, name: str) -> str:
        if not name:
            return f"What file, {USER_NAME}?"
        results = []
        for folder in list(FOLDERS.values()) + [Path.home()]:
            if not folder.exists():
                continue
            for found in folder.rglob(f"*{name}*"):
                results.append(str(found))
                if len(results) >= 5:
                    break
            if len(results) >= 5:
                break
        if not results:
            return f"No files matching '{name}' found, {USER_NAME}."
        return "Found:\n" + "\n".join(f"- {item}" for item in results)

    def open_folder(self, folder: str) -> str:
        path = FOLDERS.get(folder.lower(), Path.home())
        if not path.exists():
            return f"Folder '{folder}' not found."
        try:
            if IS_WIN:
                os.startfile(str(path))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
            return f"Opened {folder} folder, {USER_NAME}."
        except Exception as e:
            return f"Couldn't open folder: {e}"

    def read_file(self, path_or_query: str) -> str:
        _, content = self.extract_text(path_or_query, max_chars=1500)
        return content

    def create_file_interactive(self, description: str, ai_client) -> str:
        content = ai_client.chat(
            f"Write content for a file that: {description}\nReturn only the file content, no explanation."
        )
        name = "jarvis_created_file.txt"
        path = Path.home() / "Documents" / name
        path.write_text(content, encoding="utf-8")
        return f"File created: {path}"

    def organize_by_type(self, folder: str = "downloads") -> str:
        src = FOLDERS.get(folder, FOLDERS["downloads"])
        moved = 0
        for file in src.iterdir():
            if file.is_dir():
                continue
            for dest_name, exts in TYPE_MAP.items():
                if file.suffix.lower() in exts:
                    dest = src / dest_name
                    dest.mkdir(exist_ok=True)
                    file.rename(dest / file.name)
                    moved += 1
                    break
        return f"Organized {moved} files in {folder}, {USER_NAME}."
