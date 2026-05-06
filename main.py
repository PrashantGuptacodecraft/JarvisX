#!/usr/bin/env python3
"""
main.py - JARVIS entry point
Run:          python main.py
Headless:     python main.py --headless
"""
import argparse
import queue
import shutil
from pathlib import Path

from config.settings import JARVIS_NAME, KNOWLEDGE_DIR, OPERATOR_MODE, USER_NAME, VOICE_ALWAYS_ON, WAKE_WORD
from config.logger import get_logger

from brain.ai_client import AIClient
from brain.core import Brain
from brain.planner import AutonomousPlanner

from voice.speaker import Speaker
from voice.listener import Listener

from memory.manager import MemoryManager

from tools.apps.controller import AppController
from tools.browser.controller import BrowserController
from tools.system.controller import SystemController
from tools.whatsapp.controller import WhatsAppController
from tools.files.controller import FilesController
from tools.vision.controller import VisionController
from tools.tasks.controller import TaskController
from tools.terminal.controller import TerminalController
from tools.web.controller import WebController

from core_loop import CoreLoop

log = get_logger("main")


def ensure_env_file():
    env_path = Path(__file__).resolve().parent / ".env"
    example_path = Path(__file__).resolve().parent / ".env.example"
    if not env_path.exists() and example_path.exists():
        shutil.copy(example_path, env_path)
        log.info("Created .env from .env.example")


def build_jarvis(gui=None, command_queue=None):
    if command_queue is None:
        command_queue = queue.Queue()

    speaker = Speaker()
    memory = MemoryManager()
    ai = AIClient()
    files = FilesController(memory=memory)

    def notify(title, msg):
        if gui:
            gui.show_notification(title, msg)

    terminal = TerminalController()
    tools = {
        "apps": AppController(),
        "browser": BrowserController(),
        "system": SystemController(),
        "whatsapp": WhatsAppController(memory=memory),
        "files": files,
        "vision": VisionController(),
        "terminal": terminal,
        "web": WebController(),
        "tasks": TaskController(memory, speaker=speaker, gui_notify=notify),
        "memory": memory,
    }

    try:
        sync_result = memory.sync_knowledge_files(files, KNOWLEDGE_DIR)
        log.info(f"Knowledge sync complete: scanned={sync_result['scanned']} saved={sync_result['saved']}")
    except Exception as exc:
        log.warning(f"Knowledge sync skipped: {exc}")

    brain = Brain(ai, tools)
    planner = AutonomousPlanner(ai, brain)
    brain.planner = planner

    if gui:
        brain.set_terminal_log(gui.terminal_log)

    core = CoreLoop(command_queue, brain, speaker, gui=gui, memory=memory)
    core.listener = None   # assigned below after listener is created

    def status_cb(status):
        if gui:
            gui.set_status(status)

    listener = Listener(
        command_queue=command_queue,
        status_callback=status_cb,
        wakeword_callback=core.on_wake,
        speaker=speaker,
    )
    core.listener = listener   # enables keep_active() after every reply
    if gui:
        gui.listener = listener
        gui.refresh_memory_tab(memory)

    return core, listener, speaker, memory, command_queue


def boot_message(ai, listener, user_name: str) -> str:
    issues = []
    if not ai.providers:
        issues.append("no working AI provider is configured")
    if not listener.available:
        issues.append("voice input is unavailable")

    if issues:
        return f"JARVIS online in limited mode, {user_name}: " + " and ".join(issues) + "."
    if VOICE_ALWAYS_ON:
        mode = "Operator mode is enabled." if OPERATOR_MODE else "Safe mode is enabled."
        return f"JARVIS online. Always listening mode is active. {mode} {user_name}."
    return (
        f"JARVIS online. All systems operational. "
        f"{'Operator mode is enabled. ' if OPERATOR_MODE else 'Safe mode is enabled. '}"
        f"Say Hello Jarvis to begin, or say always listen for hands-free mode, {user_name}."
    )


def run_gui():
    from ui.interface import JarvisGUI

    cq = queue.Queue()
    gui = JarvisGUI(command_queue=cq)
    core, listener, speaker, memory, _ = build_jarvis(gui=gui, command_queue=cq)

    listener.start()
    core.start()

    log.info(f"{JARVIS_NAME} ready - say '{WAKE_WORD.title()}' to activate.")
    speaker.speak(boot_message(core.brain.ai, listener, USER_NAME), blocking=False)
    gui.run()


def run_headless():
    cq = queue.Queue()
    core, listener, speaker, memory, _ = build_jarvis(gui=None, command_queue=cq)
    listener.start()
    core.start()

    print(f"\n{'=' * 55}")
    print(f"  {JARVIS_NAME}  -  Headless Mode")
    print(f"  Say '{WAKE_WORD.title()}' or type commands below")
    print("  Type 'quit' to exit")
    print(f"{'=' * 55}\n")
    speaker.speak(boot_message(core.brain.ai, listener, USER_NAME), blocking=False)

    while True:
        try:
            text = input("[You] > ").strip()
            if not text:
                continue
            if text.lower() in ("quit", "exit", "q"):
                speaker.speak(f"Goodbye, {USER_NAME}.")
                break
            listener.inject_text(text)
        except (KeyboardInterrupt, EOFError):
            print("\nShutting down...")
            break


if __name__ == "__main__":
    ensure_env_file()
    parser = argparse.ArgumentParser(description=f"{JARVIS_NAME} Advanced AI Assistant")
    parser.add_argument("--headless", action="store_true", help="Run without GUI")
    args = parser.parse_args()

    if args.headless:
        run_headless()
    else:
        try:
            run_gui()
        except Exception as e:
            log.warning(f"GUI failed ({e}) - switching to headless.")
            run_headless()
