"""
main.py — JARVIS Hand Gesture Control System
Production entry point: threaded camera + processing + action pipeline.
"""
from __future__ import annotations

import logging
import os
import queue
import sys
import threading
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# ── Root path setup ───────────────────────────────────────────────────────────
_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(_ROOT))

# ── Startup banner ────────────────────────────────────────────────────────────

def _print_banner() -> None:
    C = "\033[96m"; R = "\033[0m"; G = "\033[92m"; Y = "\033[93m"
    print(f"""{C}
  ░░░░░░░  ░░░░░░   ░░░░░░  ░░    ░░ ░░  ░░░░░░
     ░░    ░░   ░░ ░░    ░░ ░░    ░░ ░░ ░░
     ░░    ░░░░░░  ░░    ░░  ░░  ░░  ░░  ░░░░░░
     ░░    ░░   ░░ ░░    ░░   ░░░░   ░░       ░░
     ░░    ░░   ░░  ░░░░░░     ░░    ░░ ░░░░░░░

  J.A.R.V.I.S  Hand Gesture Control System v2.0
  Production Build — Zero Placeholder Architecture{R}
""")
    print(f"  {G}► MODULES:{R} HandTracker · FingerAnalyzer · GestureClassifier")
    print(f"           GestureBuffer · GestureGuard · ActionDispatcher")
    print(f"           VoiceGestureFusion · AirDrawing · HeatmapEngine")
    print(f"           AROverlay · HUDRenderer · CalibrationWizard")
    print(f"  {Y}► Press Q in camera window to shut down.{R}\n")


# ── Logging setup ─────────────────────────────────────────────────────────────

def _setup_logging(log_dir: Path) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    ts      = time.strftime("%Y%m%d_%H%M%S")
    logfile = log_dir / f"session_{ts}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)-24s %(message)s",
        handlers=[
            logging.FileHandler(logfile, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("werkzeug").setLevel(logging.WARNING)


# ── Action request container ──────────────────────────────────────────────────

@dataclass
class ActionRequest:
    buffered_gesture: object
    fusion_result:    Optional[object] = None


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    _print_banner()

    # ── Config ────────────────────────────────────────────────────────────────
    from config.settings import Settings
    settings = Settings()
    features = settings.load_features()
    _setup_logging(Path(_ROOT / "logs"))
    log = logging.getLogger("jarvis.main")
    log.info("Settings loaded. Camera=%d  Screen=%dx%d",
             settings.CAMERA_INDEX, settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT)

    # ── Core modules (always loaded) ──────────────────────────────────────────
    from core.hand_tracker       import HandTracker
    from core.finger_analyzer    import FingerAnalyzer
    from core.gesture_classifier import GestureClassifier
    from core.gesture_buffer     import GestureBuffer
    from core.gesture_guard      import GestureGuard
    from control.mouse_controller    import MouseController
    from control.keyboard_controller import KeyboardController
    from control.action_dispatcher   import ActionDispatcher
    from ui.hud_renderer             import HUDRenderer

    hand_tracker    = HandTracker(settings)
    finger_analyzer = FingerAnalyzer()
    classifier      = GestureClassifier(settings)
    gesture_buffer  = GestureBuffer(
        dead_zone_px=settings.DEAD_ZONE_PX,
        smooth_alpha=settings.SMOOTHING_ALPHA,
    )
    gesture_guard   = GestureGuard()
    mouse_ctrl      = MouseController(settings)
    keyboard_ctrl   = KeyboardController()
    dispatcher      = ActionDispatcher(settings, mouse_ctrl, keyboard_ctrl, features)
    hud             = HUDRenderer(settings)

    # ── Optional modules ──────────────────────────────────────────────────────
    voice_fusion    = None
    air_drawing     = None
    heatmap_engine  = None
    ar_overlay      = None

    # Calibration
    if features.get("calibration_enabled", True):
        from calibration.calibration_manager import CalibrationManager
        from calibration.calibration_wizard  import CalibrationWizard
        cal_manager = CalibrationManager(str(_ROOT / "config" / "hand_calibration.json"))
        if not cal_manager.is_calibrated():
            log.info("No calibration found — launching wizard")
            import cv2
            cap_cal = cv2.VideoCapture(settings.CAMERA_INDEX)
            def _cb():
                ret, frame = cap_cal.read()
                return (frame, None) if ret else (None, None)
            wizard = CalibrationWizard(cal_manager)
            wizard.run_wizard(_cb)
            cap_cal.release()
            cv2.destroyAllWindows()

    # Voice fusion
    if features.get("voice_fusion_enabled", True):
        from core.fusion_commands    import FUSION_COMMAND_MAP
        from core.voice_gesture_fusion import VoiceGestureFusion
        voice_fusion = VoiceGestureFusion(settings, FUSION_COMMAND_MAP)
        voice_fusion.start()
        log.info("VoiceGestureFusion started")

    # Air drawing
    if features.get("air_drawing_enabled", True):
        from core.air_drawing import AirDrawingEngine
        air_drawing = AirDrawingEngine(settings)
        log.info("AirDrawingEngine ready")

    # Heatmap + dashboard
    if features.get("heatmap_enabled", True):
        from analytics.heatmap_engine   import HeatmapEngine
        from analytics.dashboard_server import launch_dashboard
        heatmap_engine = HeatmapEngine()
        heatmap_engine.initialize(str(_ROOT / "data" / "gestures.db"))
        heatmap_engine.start_session()
        launch_dashboard(heatmap_engine,
                         port=settings.DASHBOARD_PORT,
                         auto_open=settings.AUTO_OPEN_DASHBOARD)
        log.info("Dashboard: http://localhost:%d", settings.DASHBOARD_PORT)

    # AR overlay
    if features.get("ar_overlay_enabled", False):
        from ui.ar_overlay import AROverlayEngine
        ar_overlay = AROverlayEngine(settings)
        log.info("AROverlayEngine started  backend=%s", ar_overlay.backend_name)

    # ── Camera init ───────────────────────────────────────────────────────────
    import cv2
    cap = cv2.VideoCapture(settings.CAMERA_INDEX)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    cap.set(cv2.CAP_PROP_FPS,          30)
    if not cap.isOpened():
        log.critical("Cannot open camera index %d. Exiting.", settings.CAMERA_INDEX)
        sys.exit(1)
    log.info("Camera opened: index=%d  res=1280×720", settings.CAMERA_INDEX)

    # ── Shared queues and events ──────────────────────────────────────────────
    frame_queue:  queue.Queue = queue.Queue(maxsize=2)
    action_queue: queue.Queue = queue.Queue(maxsize=10)
    shutdown_event            = threading.Event()

    # Per-frame shared state (written by processing thread, read by main display)
    last_tracking   = [None]
    last_buffered   = [None]
    last_fps        = [0.0]
    _fps_times: list = []

    # ── Camera thread ─────────────────────────────────────────────────────────
    def camera_thread() -> None:
        while not shutdown_event.is_set():
            ret, frame = cap.read()
            if not ret:
                log.warning("Camera read failed")
                time.sleep(0.05)
                continue
            frame = cv2.flip(frame, 1)   # mirror
            try:
                frame_queue.put_nowait(frame)
            except queue.Full:
                try: frame_queue.get_nowait()
                except queue.Empty: pass
                frame_queue.put_nowait(frame)

    # ── Processing thread ──────────────────────────────────────────────────────
    def processing_thread() -> None:
        while not shutdown_event.is_set():
            try:
                frame = frame_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            t0 = time.perf_counter()
            h, w = frame.shape[:2]

            tracking = hand_tracker.process_frame(frame)
            last_tracking[0] = tracking

            buffered_out = None

            if tracking.hand_count > 0:
                # Process primary hand (index 0)
                lm_arr = hand_tracker.get_landmark_array(0)
                if lm_arr is not None:
                    gesture_raw = classifier.classify(lm_arr,
                                  tracking.handedness_list[0] if tracking.handedness_list else "Right")
                    buffered = gesture_buffer.update(gesture_raw)

                    if buffered is not None and gesture_guard.can_fire(buffered.gesture_name):
                        gesture_guard.start_hold(buffered.gesture_name)
                        if gesture_guard.check_hold_complete(buffered.gesture_name):
                            gesture_guard.record_fired(buffered.gesture_name)

                            fusion = None
                            if voice_fusion is not None:
                                fusion = voice_fusion.check_fusion(
                                    buffered.gesture_name, buffered.confidence
                                )

                            try:
                                action_queue.put_nowait(ActionRequest(buffered, fusion))
                            except queue.Full:
                                pass

                            if heatmap_engine is not None:
                                sx = int(buffered.smoothed_x * w)
                                sy = int(buffered.smoothed_y * h)
                                heatmap_engine.log_gesture(
                                    buffered.gesture_name, buffered.confidence,
                                    sx, sy, action_executed=buffered.gesture_name,
                                    voice_fused=(fusion is not None and fusion.should_fire),
                                )

                            hud.update_history(buffered.gesture_name)
                            buffered_out = buffered
                    else:
                        # Gesture changed → reset hold timer
                        if buffered is not None:
                            gesture_guard.reset_hold(buffered.gesture_name)

            last_buffered[0] = buffered_out

            # ── FPS ───────────────────────────────────────────────────────────
            now = time.perf_counter()
            _fps_times.append(now)
            while _fps_times and now - _fps_times[0] > 1.0:
                _fps_times.pop(0)
            last_fps[0] = float(len(_fps_times))

            # ── HUD composite ─────────────────────────────────────────────────
            guard_status  = gesture_guard.get_status_dict()
            fusion_status = None
            if voice_fusion is not None:
                class _FusionStatus:
                    is_voice_active = voice_fusion.is_voice_active()
                    last_phrase     = voice_fusion.get_last_voice_phrase()
                    fusion_score    = 0.0
                fusion_status = _FusionStatus()

            display = hud.update(
                tracking.annotated_frame,
                tracking,
                buffered_out,
                guard_status  = guard_status,
                fusion_status = fusion_status,
                mode_name     = "normal",
                fps           = last_fps[0],
            )

            # ── Air drawing ───────────────────────────────────────────────────
            if air_drawing is not None and buffered_out is not None:
                hand_data = {"landmarks": lm_arr if tracking.hand_count > 0 else None}
                gr_dict   = {"name": buffered_out.gesture_name if buffered_out else "none"}
                display   = air_drawing.update(display, hand_data, gr_dict)

            # ── AR overlay ────────────────────────────────────────────────────
            if ar_overlay is not None:
                amp = None
                if voice_fusion is not None:
                    amp = voice_fusion.get_mic_amplitude()
                    amp_arr = __import__("numpy").array([amp] * 32, dtype="float32")
                else:
                    amp_arr = None
                hand_positions = []
                if tracking.hand_count > 0 and lm_arr is not None:
                    cx = int(lm_arr[9, 0] * w)
                    cy = int(lm_arr[9, 1] * h)
                    hand_positions = [(cx, cy)]
                ar_overlay.update(display, amplitude_data=amp_arr,
                                  hand_positions=hand_positions)

            cv2.imshow("JARVIS Vision Control", display)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                log.info("Q pressed — shutting down")
                shutdown_event.set()

    # ── Action thread ──────────────────────────────────────────────────────────
    def action_thread() -> None:
        while not shutdown_event.is_set():
            try:
                req: ActionRequest = action_queue.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                dispatcher.dispatch(req.buffered_gesture, req.fusion_result)
            except Exception as exc:
                log.warning("Action dispatch error: %s", exc)

    # ── Start threads ─────────────────────────────────────────────────────────
    cam_t  = threading.Thread(target=camera_thread,     daemon=True, name="cam")
    proc_t = threading.Thread(target=processing_thread, daemon=True, name="proc")
    act_t  = threading.Thread(target=action_thread,     daemon=True, name="action")

    cam_t.start()
    proc_t.start()
    act_t.start()
    log.info("All threads started — JARVIS is ONLINE")

    # ── Wait for shutdown ─────────────────────────────────────────────────────
    shutdown_event.wait()
    log.info("Shutdown signal received — cleaning up…")

    for t in (cam_t, proc_t, act_t):
        t.join(timeout=2.0)

    # ── Graceful teardown ─────────────────────────────────────────────────────
    if voice_fusion is not None:
        voice_fusion.stop()
    if heatmap_engine is not None:
        heatmap_engine.end_session()
    if ar_overlay is not None:
        ar_overlay.close()

    hand_tracker.close()
    cap.release()
    cv2.destroyAllWindows()

    print("\n\033[93m  J.A.R.V.I.S  OFFLINE\033[0m\n")
    log.info("JARVIS shut down cleanly")


# ── Crash handler ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    try:
        main()
    except BaseException as exc:
        log_dir = _ROOT / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        ts        = time.strftime("%Y%m%d_%H%M%S")
        crash_log = log_dir / f"crash_{ts}.txt"
        with crash_log.open("w", encoding="utf-8") as f:
            f.write(f"JARVIS CRASH REPORT  {ts}\n")
            f.write("=" * 60 + "\n")
            f.write(traceback.format_exc())
            f.write("\n\nPlatform: " + sys.platform)
            f.write("\nPython:   " + sys.version)
        print(f"\n\033[91m[CRASH] Report saved to: {crash_log}\033[0m")
        raise
