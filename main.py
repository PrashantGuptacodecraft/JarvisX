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
from tools.vision.gesture_controller import GestureController

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
        "apps":     AppController(),
        "browser":  BrowserController(),
        "system":   SystemController(),
        "whatsapp": WhatsAppController(memory=memory),
        "files":    files,
        "vision":   VisionController(),
        "terminal": terminal,
        "web":      WebController(),
        "tasks":    TaskController(memory, speaker=speaker, gui_notify=notify),
        "memory":   memory,
    }

    try:
        sync_result = memory.sync_knowledge_files(files, KNOWLEDGE_DIR)
        log.info(f"Knowledge sync complete: scanned={sync_result['scanned']} saved={sync_result['saved']}")
    except Exception as exc:
        log.warning(f"Knowledge sync skipped: {exc}")

    brain = Brain(ai, tools)
    planner = AutonomousPlanner(ai, brain)
    brain.planner = planner

    # ── Advanced Modules ──────────────────────────────────────────────────────

    # Predictive Engine (intent prediction from history)
    try:
        from brain.predictor import PredictiveEngine
        predictor = PredictiveEngine(memory)
        brain.predictor = predictor
        log.info("PredictiveEngine ready.")
    except Exception as e:
        log.warning(f"PredictiveEngine: {e}")

    # Multi-Agent Orchestrator
    try:
        from brain.agents.orchestrator import AgentOrchestrator
        brain.orchestrator = AgentOrchestrator(ai, brain, tools)
        log.info("AgentOrchestrator ready.")
    except Exception as e:
        log.warning(f"AgentOrchestrator: {e}")

    # Voice Biometric Auth
    try:
        from voice.authenticator import VoiceAuthenticator
        va = VoiceAuthenticator()
        tools["voice_auth"] = va
        log.info(f"VoiceAuthenticator ready (enrolled={va.is_enrolled})")
    except Exception as e:
        log.warning(f"VoiceAuthenticator: {e}")

    # Workflow Recorder (macro record/replay)
    try:
        from tools.automation.workflow_recorder import WorkflowRecorder
        tools["workflow_recorder"] = WorkflowRecorder(memory)
        log.info("WorkflowRecorder ready.")
    except Exception as e:
        log.warning(f"WorkflowRecorder: {e}")

    # Screen Agent (GUI automation via vision)
    try:
        from tools.vision.modules.screen_agent import ScreenAgent
        tools["screen_agent"] = ScreenAgent(ai)
        log.info("ScreenAgent ready.")
    except Exception as e:
        log.warning(f"ScreenAgent: {e}")

    # Screen Memory (AR recall from periodic screenshots)
    try:
        from tools.vision.modules.screen_memory import ScreenMemory
        sm = ScreenMemory(ai_client=ai, memory=memory, interval=90)
        sm.start()
        tools["screen_memory"] = sm
        log.info("ScreenMemory started.")
    except Exception as e:
        log.warning(f"ScreenMemory: {e}")

    # Private Mode (AES encryption + screen capture block)
    try:
        from tools.security.private_mode import PrivateMode
        tools["private_mode"] = PrivateMode(memory=memory, speaker=speaker, gui=gui)
        log.info("PrivateMode ready.")
    except Exception as e:
        log.warning(f"PrivateMode: {e}")

    # Cross-Device REST API
    try:
        from tools.sync.api_server import CrossDeviceServer
        sync_srv = CrossDeviceServer(command_queue=command_queue)
        sync_srv.start()
        tools["sync_server"] = sync_srv
        log.info("CrossDeviceServer started on :7777")
    except Exception as e:
        log.warning(f"CrossDeviceServer: {e}")

    # Code Intelligence (proactive watchdog code review)
    try:
        from tools.code.analyzer import CodeAnalyzer
        import os as _os
        ws = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "workspace")
        ca = CodeAnalyzer(ai_client=ai, speaker=speaker, workspace_dir=ws)
        ca.start()
        tools["code_analyzer"] = ca
        log.info("CodeAnalyzer started.")
    except Exception as e:
        log.warning(f"CodeAnalyzer: {e}")

    # IoT Smart Home Controller
    try:
        from tools.iot.controller import IoTController
        import os as _os
        tools["iot"] = IoTController(
            ha_url=_os.getenv("HA_URL", ""),
            ha_token=_os.getenv("HA_TOKEN", ""),
            mqtt_host=_os.getenv("MQTT_HOST", ""),
        )
        log.info(f"IoTController ready (available={tools['iot'].available})")
    except Exception as e:
        log.warning(f"IoTController: {e}")

    # BCI Controller (EEG mind control — hardware gated)
    try:
        from tools.bci.controller import BCIController
        import os as _os
        bci = BCIController(
            command_queue=command_queue,
            board_id=int(_os.getenv("BCI_BOARD_ID", "-1")),
        )
        if bci.available:
            bci.start()
        tools["bci"] = bci
        log.info(f"BCIController ready (available={bci.available})")
    except Exception as e:
        log.warning(f"BCIController: {e}")

    # ── Core wiring ───────────────────────────────────────────────────────────
    if gui:
        brain.set_terminal_log(gui.terminal_log)

    core = CoreLoop(command_queue, brain, speaker, gui=gui, memory=memory)
    core.listener = None

    def status_cb(status):
        if gui:
            gui.set_status(status)

    listener = Listener(
        command_queue=command_queue,
        status_callback=status_cb,
        wakeword_callback=core.on_wake,
        speaker=speaker,
    )
    core.listener = listener
    if gui:
        gui.listener = listener
        gui.refresh_memory_tab(memory)

    # Gesture controller
    gesture_ctrl = GestureController(command_queue=command_queue, gui=gui)
    if gui and hasattr(gui, "_gesture_ctrl"):
        gui._gesture_ctrl = gesture_ctrl
    # Inject AI + memory into gesture engine for AirDrawing AI analysis
    if hasattr(gesture_ctrl, "engine") and gesture_ctrl.engine:
        gesture_ctrl.engine._ai_client = ai
        gesture_ctrl.engine._memory = memory

    # Vision sub-modules — injected into brain.tools for intent routing
    try:
        from tools.vision.modules.emotion_detector import EmotionDetector
        ed = EmotionDetector()
        tools["emotion_detector"] = ed
    except Exception as e:
        log.debug(f"EmotionDetector not available: {e}")
    try:
        from tools.vision.modules.object_detector import ObjectDetector
        tools["object_detector"] = ObjectDetector()
    except Exception as e:
        log.debug(f"ObjectDetector not available: {e}")
    try:
        from tools.vision.modules.gaze_tracker import GazeTracker
        tools["gaze_tracker"] = GazeTracker()
    except Exception as e:
        log.debug(f"GazeTracker not available: {e}")

    # UI Overlays (HUD, transcript, visualizer, avatar)
    if gui:
        _start_ui_modules(tools, core)

    # Wire speaker word callbacks → transcript and avatar (soft-gated)
    try:
        _wire_speaker_callbacks(speaker, tools)
    except Exception as _e:
        log.warning(f"Speaker callbacks not wired: {_e}")

    return core, listener, speaker, memory, command_queue, gesture_ctrl


def _start_ui_modules(tools: dict, core):
    """Start Iron Man HUD, live transcript, audio visualizer, and avatar."""
    import threading, os

    # HUD Overlay
    try:
        from ui.hud_overlay import HUDOverlay
        if os.getenv("JARVIS_HUD", "true").lower() == "true":
            def _s(): return getattr(core, "_last_status", "sleeping")
            def _e():
                em = tools.get("emotion_detector")
                return (em.current_emotion, em.stress_level) if em else ("neutral", 0.0)
            def _p():
                b = core.brain
                return b.predictor.top_predictions(3) if hasattr(b, "predictor") and b.predictor else []
            hud = HUDOverlay(status_provider=_s, emotion_provider=_e, prediction_provider=_p)
            threading.Thread(target=hud.show, daemon=True).start()
            tools["hud"] = hud
            log.info("HUDOverlay started.")
    except Exception as e:
        log.warning(f"HUDOverlay: {e}")

    # Live Transcript
    try:
        from ui.live_transcript import LiveTranscript
        t = LiveTranscript()
        t.start()
        tools["transcript"] = t
        log.info("LiveTranscript started.")
    except Exception as e:
        log.warning(f"LiveTranscript: {e}")

    # Audio Visualizer
    try:
        from ui.audio_visualizer import AudioVisualizer
        v = AudioVisualizer()
        v.start()
        tools["visualizer"] = v
        log.info("AudioVisualizer started.")
    except Exception as e:
        log.warning(f"AudioVisualizer: {e}")

    # Avatar Face
    try:
        from ui.avatar import AvatarFace
        a = AvatarFace()
        a.start()
        tools["avatar"] = a
        log.info("AvatarFace started.")
    except Exception as e:
        log.warning(f"AvatarFace: {e}")

def _wire_speaker_callbacks(speaker, tools: dict):
    """Connect speaker word/speaking events to live transcript and avatar."""
    transcript = tools.get("transcript")
    avatar = tools.get("avatar")
    visualizer = tools.get("visualizer")

    if transcript and hasattr(speaker, "register_word_callback"):
        # stream_word is the correct method on LiveTranscript
        if hasattr(transcript, "stream_word"):
            speaker.register_word_callback(transcript.stream_word)
            log.info("Speaker → LiveTranscript wired.")
        elif hasattr(transcript, "on_word"):
            speaker.register_word_callback(transcript.on_word)
            log.info("Speaker → LiveTranscript wired (on_word).")

    if avatar and hasattr(speaker, "register_speaking_callback"):
        # Speaking state drives avatar expression
        def _avatar_speaking(speaking: bool):
            try:
                if speaking:
                    avatar.set_expression("speaking")
                else:
                    avatar.set_expression("idle")
            except Exception:
                pass
        speaker.register_speaking_callback(_avatar_speaking)
        log.info("Speaker → Avatar wired.")

    if visualizer and hasattr(speaker, "register_speaking_callback"):
        def _viz_speaking(speaking: bool):
            try:
                visualizer.set_active(speaking)
            except Exception:
                pass
        speaker.register_speaking_callback(_viz_speaking)
        log.info("Speaker → AudioVisualizer wired.")


def boot_message(ai, listener, user_name: str) -> str:
    """Return a time-aware greeting spoken at startup."""
    import datetime, random
    hour = datetime.datetime.now().hour
    if hour < 12:
        greetings = [
            f"Good morning, {user_name}. Systems are online and I'm ready.",
            f"Good morning, {user_name}. All systems up. What's the plan today?",
            f"Morning, {user_name}. I'm online and listening.",
        ]
    elif hour < 17:
        greetings = [
            f"Good afternoon, {user_name}. I'm online. What can I do for you?",
            f"Afternoon, {user_name}. Systems ready. How can I help?",
            f"Good afternoon, {user_name}. Standing by.",
        ]
    else:
        greetings = [
            f"Good evening, {user_name}. I'm online. What do you need?",
            f"Evening, {user_name}. All systems ready.",
            f"Good evening, {user_name}. I'm here whenever you need me.",
        ]
    return random.choice(greetings)


def run_gui():
    from ui.interface import JarvisGUI

    cq = queue.Queue()
    gui = JarvisGUI(command_queue=cq)
    core, listener, speaker, memory, _, gesture_ctrl = build_jarvis(gui=gui, command_queue=cq)
    if hasattr(gui, '_gesture_ctrl'):
        gui._gesture_ctrl = gesture_ctrl

    listener.start()
    core.start()

    log.info(f"{JARVIS_NAME} ready - say '{WAKE_WORD.title()}' to activate.")
    speaker.speak(boot_message(core.brain.ai, listener, USER_NAME), blocking=False)
    gui.run()


def run_headless():
    cq = queue.Queue()
    core, listener, speaker, memory, _, gesture_ctrl = build_jarvis(gui=None, command_queue=cq)
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
