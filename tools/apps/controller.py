"""tools/apps/controller.py — Open/close applications."""
import os, sys, subprocess
from config.settings import USER_NAME
from config.logger import get_logger

log = get_logger("apps")
IS_WIN = sys.platform == "win32"

APP_COMMANDS = {
    "chrome":      ("start chrome",                "google-chrome"),
    "firefox":     ("start firefox",               "firefox"),
    "vscode":      ("code",                        "code"),
    "notepad":     ("notepad",                     "gedit"),
    "calculator":  ("calc",                        "gnome-calculator"),
    "explorer":    ("explorer",                    "nautilus"),
    "spotify":     ("start spotify",               "spotify"),
    "camera":      ("start microsoft.windows.camera:", "cheese"),
    "settings":    ("start ms-settings:",          "gnome-control-center"),
    "whatsapp":    ("start whatsapp:",             "whatsapp"),
    "telegram":    ("start telegram",              "telegram-desktop"),
    "discord":     ("start discord",               "discord"),
    "vlc":         ("start vlc",                   "vlc"),
    "word":        ("start winword",               "libreoffice --writer"),
    "excel":       ("start excel",                 "libreoffice --calc"),
    "powerpoint":  ("start powerpnt",              "libreoffice --impress"),
    "paint":       ("mspaint",                     "pinta"),
    "taskmanager": ("taskmgr",                     "gnome-system-monitor"),
    "terminal":    ("start cmd",                   "xterm"),
    "cmd":         ("start cmd",                   "xterm"),
    "powershell":  ("start powershell",            "bash"),
    "notepadpp":   ("start notepad++",             "gedit"),
}

PROC_NAMES = {
    "chrome": "chrome.exe", "firefox": "firefox.exe", "vscode": "Code.exe",
    "notepad": "notepad.exe", "spotify": "Spotify.exe", "discord": "Discord.exe",
    "vlc": "vlc.exe", "word": "WINWORD.EXE", "excel": "EXCEL.EXE",
}


class AppController:
    def open(self, app: str) -> str:
        cmds = APP_COMMANDS.get((app or "").lower())
        if not cmds:
            return f"Don't know how to open '{app}', {USER_NAME}."
        cmd = cmds[0] if IS_WIN else cmds[1]
        try:
            if IS_WIN:
                if cmd.startswith("start "):
                    target = cmd[len("start "):].strip()
                    subprocess.Popen(
                        ["cmd", "/c", "start", "", target],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                else:
                    subprocess.Popen(
                        cmd.split(),
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
            else:
                subprocess.Popen(cmd.split(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            log.info(f"Opened: {app}")
            return f"Opening {app}, {USER_NAME}."
        except Exception as e:
            return f"Couldn't open {app}: {e}"

    def close(self, app: str) -> str:
        proc = PROC_NAMES.get((app or "").lower())
        if not proc:
            return f"Don't know the process for '{app}', {USER_NAME}."
        try:
            if IS_WIN:
                os.system(f"taskkill /f /im {proc}")
            else:
                os.system(f"pkill -f {app}")
            return f"Closed {app}, {USER_NAME}."
        except Exception as e:
            return f"Couldn't close {app}: {e}"
