"""
setup.py — JARVIS Hand Gesture Control System
Automated environment setup script.
Run: python setup.py
"""
from __future__ import annotations

import os
import platform
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# ANSI colors
C   = "\033[96m"   # cyan
G   = "\033[92m"   # green
Y   = "\033[93m"   # yellow
R   = "\033[91m"   # red
RST = "\033[0m"


# ── Banner ────────────────────────────────────────────────────────────────────

def print_banner() -> None:
    print(f"""{C}
  ╔══════════════════════════════════════════════╗
  ║  J.A.R.V.I.S  Hand Gesture Control System   ║
  ║          Automated Setup Wizard              ║
  ╚══════════════════════════════════════════════╝{RST}
""")


# ── Python version check ──────────────────────────────────────────────────────

def check_python() -> None:
    print(f"{C}[1/8] Checking Python version…{RST}")
    major, minor = sys.version_info[:2]
    if (major, minor) < (3, 9):
        print(f"{R}✗ Python 3.9+ required. Found {major}.{minor}. Exiting.{RST}")
        sys.exit(1)
    print(f"{G}  ✔ Python {major}.{minor} — OK{RST}")


# ── Directory creation ────────────────────────────────────────────────────────

def create_directories() -> None:
    print(f"\n{C}[2/8] Creating project directories…{RST}")
    dirs = [
        "config", "core", "control", "ui",
        "analytics/templates", "calibration",
        "data", "logs", "drawings", "benchmarks",
        "tests", "reports", "docs",
        "training/custom_gestures",
    ]
    for d in dirs:
        path = ROOT / d
        path.mkdir(parents=True, exist_ok=True)

    # .gitkeep for empty tracked dirs
    for keep_dir in ("logs", "data", "drawings"):
        gk = ROOT / keep_dir / ".gitkeep"
        if not gk.exists():
            gk.touch()

    print(f"{G}  ✔ All directories created{RST}")


# ── pip install ───────────────────────────────────────────────────────────────

def install_requirements() -> None:
    print(f"\n{C}[3/8] Installing Python dependencies…{RST}")
    req_file = ROOT / "requirements.txt"
    if not req_file.exists():
        print(f"{Y}  ⚠ requirements.txt not found — skipping{RST}")
        return

    packages = [
        line.strip() for line in req_file.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]

    installed = failed = 0
    for pkg in packages:
        print(f"  Installing {pkg}…", end=" ", flush=True)
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", pkg,
             "--quiet", "--no-warn-script-location"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            print(f"{G}OK{RST}")
            installed += 1
        else:
            print(f"{R}FAILED{RST}")
            if result.stderr:
                for line in result.stderr.strip().splitlines()[-3:]:
                    print(f"    {line}")
            failed += 1

    print(f"\n{G}  ✔ Installed: {installed}  {R}Failed: {failed}{RST}")


# ── .env setup ────────────────────────────────────────────────────────────────

def copy_env() -> None:
    print(f"\n{C}[4/8] Setting up .env configuration…{RST}")
    env_file     = ROOT / ".env"
    example_file = ROOT / ".env.example"

    if env_file.exists():
        print(f"{Y}  ⚠ .env already exists — skipping copy{RST}")
    elif example_file.exists():
        import shutil
        shutil.copy(example_file, env_file)
        print(f"{G}  ✔ .env created from .env.example{RST}")
        print(f"  {Y}→ Edit: {env_file}{RST}")
    else:
        print(f"{Y}  ⚠ .env.example not found — create .env manually{RST}")


# ── Whisper model ─────────────────────────────────────────────────────────────

def download_whisper_model() -> None:
    print(f"\n{C}[5/8] Loading Whisper tiny model…{RST}")
    try:
        import whisper
        print("  Downloading/loading whisper tiny (may take ~1 minute first time)…")
        model = whisper.load_model("tiny")
        print(f"{G}  ✔ Whisper tiny model ready{RST}")
    except ImportError:
        print(f"{Y}  ⚠ whisper not installed. Install with: pip install openai-whisper{RST}")
    except Exception as exc:
        print(f"{Y}  ⚠ Whisper load error: {exc}{RST}")


# ── Virtual camera check ──────────────────────────────────────────────────────

def check_virtual_camera() -> None:
    print(f"\n{C}[6/8] Checking virtual camera backend…{RST}")
    try:
        import pyvirtualcam
        print(f"{G}  ✔ pyvirtualcam installed{RST}")
    except ImportError:
        plat = platform.system()
        if plat == "Windows":
            print(f"{Y}  ⚠ pyvirtualcam not found.{RST}")
            print("    Install OBSVirtualCam from https://obsproject.com/kb/virtual-camera")
            print("    Then: pip install pyvirtualcam")
            # Check OBS registry key
            try:
                import winreg
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                    r"SOFTWARE\OBS Studio")
                winreg.CloseKey(key)
                print(f"{G}    OBS Studio detected in registry ✔{RST}")
            except Exception:
                print(f"{Y}    OBS Studio not found in registry.{RST}")
        elif plat == "Linux":
            print(f"{Y}  ⚠ pyvirtualcam not found.{RST}")
            print("    Install v4l2loopback: sudo apt install v4l2loopback-dkms")
            print("    Load module: sudo modprobe v4l2loopback devices=1 video_nr=10")
            print("    Then: pip install pyvirtualcam")
        else:
            print(f"{Y}  ⚠ pyvirtualcam not found. See: https://github.com/letmaik/pyvirtualcam{RST}")


# ── Setup complete marker ─────────────────────────────────────────────────────

def write_setup_complete() -> None:
    print(f"\n{C}[7/8] Writing setup_complete marker…{RST}")
    out_file = ROOT / "config" / "setup_complete.txt"
    pip_list = subprocess.run(
        [sys.executable, "-m", "pip", "list", "--format=columns"],
        capture_output=True, text=True,
    ).stdout

    with out_file.open("w", encoding="utf-8") as f:
        f.write(f"JARVIS Setup Complete\n")
        f.write(f"Timestamp : {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Python    : {sys.version}\n")
        f.write(f"Platform  : {platform.platform()}\n")
        f.write(f"\n--- pip list ---\n{pip_list}")

    print(f"{G}  ✔ {out_file}{RST}")


# ── Next steps ────────────────────────────────────────────────────────────────

def print_next_steps() -> None:
    env_path  = ROOT / ".env"
    main_path = ROOT / "main.py"
    print(f"""
{C}[8/8] Setup complete! Next steps:{RST}

  {G}1.{RST} Edit your settings:
     {Y}{env_path}{RST}

  {G}2.{RST} Add contacts to:
     {Y}{ROOT / "data" / "contacts.json"}{RST}

  {G}3.{RST} Launch JARVIS:
     {C}python {main_path}{RST}
     or on Windows: {C}run.bat{RST}

  {G}4.{RST} Open Analytics Dashboard:
     {C}http://localhost:5050{RST}

  {G}5.{RST} Run test suite:
     {C}pytest tests/ -v{RST}

{G}  ══════════════════════════════════════════════{RST}
{C}  J.A.R.V.I.S  is ready to deploy.  Good luck.{RST}
{G}  ══════════════════════════════════════════════{RST}
""")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print_banner()
    check_python()
    create_directories()
    install_requirements()
    copy_env()
    download_whisper_model()
    check_virtual_camera()
    write_setup_complete()
    print_next_steps()
