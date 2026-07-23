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

from shared_core import get_bus

from brain.ai_client import AIClient
from brain.core import Brain
from brain.planner import AutonomousPlanner

from voice.speaker import Speaker
from voice.listener import Listener

from memory.manager import MemoryManager
from shared_core.memory_engine.execution_history import ExecutionRecorder

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

    # ── Shared Core Event Bus (Phase A) ───────────────────────────────────────
    # The machine's central nervous system. Subsystems publish onto it; the logger
    # below is the first live subscriber (proves end-to-end). Additive + crash-proof.
    bus = get_bus()

    def _bus_logger(event):
        log.debug(f"[bus] {event.topic} <- {event.source} :: {event.payload}")

    try:
        bus.subscribe("*", _bus_logger, source="event_logger")
        log.info("Event Bus online; event_logger subscribed.")
    except Exception as e:
        log.warning(f"Event Bus logger not wired: {e}")

    # ── State Manager + World-State History Ledger (Phase B) ───────────────────
    # Live machine snapshot + chronological transition ledger (rolling persistence).
    # Additive + crash-proof: failure here never blocks boot.
    state_manager = None
    os_sampler = None
    try:
        from shared_core.state_manager import build_state_manager, OSSampler
        state_manager = build_state_manager(bus, persist=True)
        state_manager.start()
        os_sampler = OSSampler(bus, interval=2.0)
        # Driven by the central Scheduler (below); legacy .start() is the fallback path.
        log.info(f"StateManager + History Ledger online (ledger size={state_manager.ledger.size()}).")
    except Exception as e:
        log.warning(f"StateManager not started: {e}")

    # ── Central Scheduler (Phase B · B5) ──────────────────────────────────────
    # One multi-rate scheduler replaces fragmented polling loops. Additive + crash-proof:
    # if it fails to start, the OS sampler falls back to its own legacy polling thread.
    scheduler = None
    try:
        from shared_core.scheduler import Scheduler, Priority
        scheduler = Scheduler(max_workers=6)
        scheduler.start()
        if os_sampler is not None:
            def _os_sampler_tick():
                snap = os_sampler.sample_once()
                bus.publish("perception.os.snapshot", snap, source="os_sampler")
            scheduler.register_task("os_sampler", "OS perception sampler", _os_sampler_tick,
                                    interval=2.0, priority=Priority.BACKGROUND, source_module="main")

        def _scheduler_health():
            if scheduler is not None:
                bus.publish("system.health", scheduler.health(), source="scheduler")
        scheduler.register_task("scheduler_health", "scheduler health heartbeat",
                                _scheduler_health, interval=10.0, priority=Priority.LOGGING,
                                source_module="main")
        if state_manager is not None:
            state_manager.set_scheduler(scheduler)
        log.info("Scheduler online; OS sampler migrated onto scheduler.")
    except Exception as e:
        log.warning(f"Scheduler not started: {e}")
        try:
            if os_sampler is not None:
                os_sampler.start()  # legacy fallback: own polling thread
                log.info("OS sampler on legacy polling thread (scheduler fallback).")
        except Exception:
            pass

    # ── State Compaction Job (Phase B · BC3) ──────────────────────────────────
    if scheduler is not None and state_manager is not None:
        try:
            from shared_core.state_manager import CompactionJob, DEFAULT_COMPACTION_INTERVAL_SECONDS
            from shared_core.scheduler import Priority
            
            compaction_job = CompactionJob(store=state_manager.ledger.store, bus=bus, scheduler=scheduler)
            scheduler.register_task(
                task_id="state_compaction",
                name="State Compaction Maintenance",
                fn=compaction_job.run_cycle,
                interval=DEFAULT_COMPACTION_INTERVAL_SECONDS,
                priority=Priority.LOGGING,
                source_module="main"
            )
            log.info(f"State Compaction Job registered (interval={DEFAULT_COMPACTION_INTERVAL_SECONDS}s).")
        except Exception as e:
            log.warning(f"State Compaction Job not registered: {e}")

    # ── Telemetry Engine (Phase B · B6) ───────────────────────────────────────
    # Continuous CPU/RAM/Disk/GPU sampling + filesystem watcher, run as scheduler tasks,
    # published to perception.system.* / perception.filesystem.change. Additive + crash-proof.
    telemetry = None
    if scheduler is not None:
        try:
            import os as _os
            from shared_core.telemetry import TelemetryEngine
            watch_dirs = [_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "workspace")]
            telemetry = TelemetryEngine(bus, scheduler, watch_paths=watch_dirs)
            telemetry.start()
            log.info("TelemetryEngine online (CPU/RAM/Disk/GPU + filesystem watcher).")
        except Exception as e:
            log.warning(f"TelemetryEngine not started: {e}")

    speaker = Speaker()
    memory = MemoryManager()
    
    # ── Phase C7: Execution History Recorder ──
    execution_recorder = ExecutionRecorder(memory_manager=memory, event_bus=bus)
    execution_recorder.start()
    
    # ── Phase C9: Consolidation Job ──
    if scheduler is not None:
        try:
            from shared_core.memory_engine.consolidation import ConsolidationJob
            from shared_core.memory_engine.kg_query import KGQueryService
            from shared_core.scheduler import Priority
            
            c_job = ConsolidationJob(memory_manager=memory, kg_query_service=KGQueryService(memory))
            scheduler.register_task(
                task_id="consolidation_job",
                name="Phase C9 Consolidation",
                fn=c_job.run_once,
                interval=86400.0,
                priority=Priority.BACKGROUND,
                source_module="main"
            )
            log.info("ConsolidationJob registered (interval=86400.0s).")
        except Exception as e:
            log.warning(f"ConsolidationJob not registered: {e}")
            
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
    brain.state_manager = state_manager   # Phase B: live WorldState + History Ledger (may be None)
    brain.scheduler = scheduler           # Phase B: central multi-rate scheduler (may be None)

    # ── Continuity (Phase B B10/B11): restart = pause/resume, not fresh boot ────
    # Crash-safe: atomic writes + autosave + atexit save. Additive; failure never blocks boot.
    try:
        from shared_core.state_manager import ContinuityManager
        continuity = ContinuityManager()
        if state_manager is not None:
            continuity.register_provider(
                "world_state", state_manager.snapshot, state_manager.restore_snapshot)

        def _get_brain_state():
            st = {}
            vm = getattr(brain, "volatile_memory", None)
            if isinstance(vm, dict):
                st["volatile_memory"] = {k: vm[k] for i, k in enumerate(vm) if i < 1000}
            pend = getattr(brain, "pending", None)
            if pend is not None:
                if isinstance(pend, list):
                    st["pending"] = pend[-1000:]
                elif isinstance(pend, dict):
                    st["pending"] = {k: pend[k] for i, k in enumerate(pend) if i < 1000}
                else:
                    st["pending"] = pend     # reasoning state; persisted only if serializable
            return st

        def _set_brain_state(data):
            if not isinstance(data, dict):
                return
            if isinstance(data.get("volatile_memory"), dict):
                brain.volatile_memory = data["volatile_memory"]
            if "pending" in data and data["pending"] is not None:
                p = data["pending"]
                brain.pending = tuple(p) if isinstance(p, list) else p

        continuity.register_provider("brain", _get_brain_state, _set_brain_state)
        if scheduler is not None:
            # B5↔continuity: scheduler runtime state persisted + restored across restarts.
            continuity.register_provider("scheduler", scheduler.snapshot, scheduler.restore)
        restored = continuity.restore()          # B11: resume prior runtime state
        continuity.start_autosave()
        import atexit
        atexit.register(continuity.stop)
        brain.continuity = continuity
        if state_manager is not None:
            state_manager.set_continuity(continuity)
        log.info(f"ContinuityManager online (restored {restored} slice(s)).")
    except Exception as e:
        log.warning(f"ContinuityManager not started: {e}")

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

    # Universal Agent (Gemini native tools)
    try:
        from brain.agents.universal_agent import UniversalAgent
        brain.universal_agent = UniversalAgent(ai, brain)
        log.info("UniversalAgent ready.")
    except Exception as e:
        log.warning(f"UniversalAgent: {e}")

    # Multi-Agent Swarm
    try:
        from brain.agents.swarm import SwarmManager
        brain.swarm_manager = SwarmManager(ai, brain)
        log.info("SwarmManager ready.")
    except Exception as e:
        log.warning(f"SwarmManager: {e}")

    # Proactive Context Watcher
    try:
        from tools.system.context_watcher import ContextWatcher
        cw = ContextWatcher(brain)
        cw.start()
        log.info("ContextWatcher started.")
    except Exception as e:
        log.warning(f"ContextWatcher: {e}")

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
        log.info("HUDOverlay disabled.")
    except Exception as e:
        log.warning(f"HUDOverlay: {e}")

    # Live Transcript
    try:
        # from ui.live_transcript import LiveTranscript
        # t = LiveTranscript()
        # t.start()
        # tools["transcript"] = t
        log.info("LiveTranscript disabled.")
    except Exception as e:
        log.warning(f"LiveTranscript: {e}")

    # Audio Visualizer
    try:
        log.info("AudioVisualizer disabled.")
    except Exception as e:
        log.warning(f"AudioVisualizer: {e}")

    # Avatar Face
    try:
        log.info("AvatarFace disabled.")
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
