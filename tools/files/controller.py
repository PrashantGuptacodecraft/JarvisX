"""tools/files/controller.py — File operations."""
import os, sys, subprocess
from pathlib import Path
from config.settings import USER_NAME
from config.logger import get_logger

log = get_logger("files")
IS_WIN = sys.platform == "win32"

FOLDERS = {
    "downloads": Path.home() / "Downloads",
    "desktop": Path.home() / "Desktop",
    "documents": Path.home() / "Documents",
    "pictures": Path.home() / "Pictures",
    "music": Path.home() / "Music",
    "videos": Path.home() / "Videos",
}

TYPE_MAP = {
    "Images":    [".jpg",".jpeg",".png",".gif",".bmp",".webp",".svg"],
    "Videos":    [".mp4",".mkv",".avi",".mov",".wmv",".flv"],
    "Documents": [".pdf",".docx",".doc",".txt",".xlsx",".pptx",".csv"],
    "Music":     [".mp3",".wav",".flac",".aac",".ogg"],
    "Archives":  [".zip",".rar",".7z",".tar",".gz"],
    "Code":      [".py",".js",".html",".css",".java",".cpp",".ts"],
}


class FilesController:
    def find_file(self, name: str) -> str:
        if not name:
            return f"What file, {USER_NAME}?"
        results = []
        for d in list(FOLDERS.values()) + [Path.home()]:
            if d.exists():
                for f in d.rglob(f"*{name}*"):
                    results.append(str(f))
                    if len(results) >= 5:
                        break
            if len(results) >= 5:
                break
        if not results:
            return f"No files matching '{name}' found, {USER_NAME}."
        return "Found:\n" + "\n".join(f"• {r}" for r in results)

    def open_folder(self, folder: str) -> str:
        path = FOLDERS.get(folder.lower(), Path.home())
        if not path.exists():
            return f"Folder '{folder}' not found."
        try:
            if IS_WIN: os.startfile(str(path))
            elif sys.platform == "darwin": subprocess.Popen(["open", str(path)])
            else: subprocess.Popen(["xdg-open", str(path)])
            return f"Opened {folder} folder, {USER_NAME}."
        except Exception as e:
            return f"Couldn't open folder: {e}"

    def read_file(self, path_or_query: str) -> str:
        path = Path(path_or_query)
        if not path.exists():
            for d in FOLDERS.values():
                if d.exists():
                    for f in d.rglob(f"*{path_or_query}*"):
                        path = f; break
                if path.exists(): break
        if not path.exists():
            return f"File not found, {USER_NAME}."
        try:
            ext = path.suffix.lower()
            if ext == ".pdf":
                import fitz
                doc = fitz.open(str(path))
                return "".join(p.get_text() for p in doc)[:1500]
            elif ext in (".docx", ".doc"):
                from docx import Document
                doc = Document(str(path))
                return "\n".join(p.text for p in doc.paragraphs)[:1500]
            else:
                return path.read_text(encoding="utf-8", errors="ignore")[:1500]
        except Exception as e:
            return f"Couldn't read file: {e}"

    def create_file_interactive(self, description: str, ai_client) -> str:
        """Ask AI what content to put in a new file, then create it."""
        content = ai_client.chat(f"Write content for a file that: {description}\nReturn only the file content, no explanation.")
        name = "jarvis_created_file.txt"
        path = Path.home() / "Documents" / name
        path.write_text(content, encoding="utf-8")
        return f"File created: {path}"

    def organize_by_type(self, folder: str = "downloads") -> str:
        src = FOLDERS.get(folder, FOLDERS["downloads"])
        moved = 0
        for file in src.iterdir():
            if file.is_dir(): continue
            for dest_name, exts in TYPE_MAP.items():
                if file.suffix.lower() in exts:
                    dest = src / dest_name
                    dest.mkdir(exist_ok=True)
                    file.rename(dest / file.name)
                    moved += 1; break
        return f"Organized {moved} files in {folder}, {USER_NAME}."
