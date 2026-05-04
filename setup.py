#!/usr/bin/env python3
"""setup.py — One-command JARVIS installer.  Run: python setup.py"""
import os, sys, subprocess, shutil
from pathlib import Path

BASE = Path(__file__).parent

def run(cmd):
    print(f"  >> {cmd}")
    return subprocess.run(cmd, shell=True).returncode == 0

def main():
    print("\n" + "="*56)
    print("  J.A.R.V.I.S  ─  Setup & Installation")
    print("="*56 + "\n")

    print("[1] Creating directories...")
    for d in ["logs", "config", "brain", "voice", "memory",
              "tools/apps", "tools/browser", "tools/system",
              "tools/whatsapp", "tools/files", "tools/vision",
              "tools/tasks", "tools/terminal", "tools/web",
              "tools/code", "ui"]:
        (BASE / d).mkdir(parents=True, exist_ok=True)
    print("    Done.\n")

    print("[2] Creating __init__.py files...")
    pkgs = ["config", "brain", "voice", "memory", "tools",
            "tools/apps", "tools/browser", "tools/system",
            "tools/whatsapp", "tools/files", "tools/vision",
            "tools/tasks", "tools/terminal", "tools/web",
            "tools/code", "ui"]
    for pkg in pkgs:
        init = BASE / pkg / "__init__.py"
        if not init.exists():
            init.write_text("# JARVIS module\n")
    print("    Done.\n")

    print("[3] Setting up .env ...")
    env = BASE / ".env"
    ex  = BASE / ".env.example"
    if not env.exists() and ex.exists():
        shutil.copy(ex, env)
        print("    Created .env from template. Add your API keys!\n")
    else:
        print("    .env already exists.\n")

    print("[4] Creating JarvisWorkspace...")
    (BASE / "JarvisWorkspace").mkdir(exist_ok=True)
    print("    Done.\n")

    print("[5] Installing dependencies...")
    pip = f"{sys.executable} -m pip install -q"

    core = ["python-dotenv", "requests", "colorama", "psutil",
            "customtkinter", "Pillow", "pyperclip", "schedule",
            "pyautogui", "beautifulsoup4"]
    ai   = ["google-genai", "openai", "groq"]
    tts  = ["pyttsx3", "gTTS", "pygame"]
    doc  = ["python-docx", "PyMuPDF", "pytesseract"]

    for group, label in [(core,"Core"), (ai,"AI"), (tts,"TTS"), (doc,"Docs")]:
        print(f"  Installing {label} packages...")
        for pkg in group:
            run(f"{pip} {pkg}")

    print("\n  Installing SpeechRecognition...")
    run(f"{pip} SpeechRecognition")
    print("  Installing PyAudio (may need extra steps on some systems)...")
    if not run(f"{pip} PyAudio"):
        print("  PyAudio failed. On Windows: pip install pipwin && pipwin install pyaudio")

    print("\n" + "="*56)
    print("  SETUP COMPLETE!")
    print("\n  Next steps:")
    print("  1. Edit .env — add your API key:")
    print("     GEMINI_API_KEY=your_key  (Google AI Studio)")
    print("     USER_NAME=YourName")
    print("\n  2. Run JARVIS:")
    print("     python main.py")
    print("\n  3. Say 'Hello Jarvis' to activate!")
    print("="*56 + "\n")

if __name__ == "__main__":
    main()
