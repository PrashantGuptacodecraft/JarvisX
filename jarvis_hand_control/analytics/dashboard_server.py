"""
analytics/dashboard_server.py
Flask + SocketIO real-time analytics dashboard server.
Runs in a daemon thread — never blocks the gesture loop.
"""
from __future__ import annotations

import logging
import threading
import time
import webbrowser
from typing import Optional

log = logging.getLogger(__name__)


def create_app(heatmap_engine):
    """
    Build and return the Flask application + SocketIO instance.

    Parameters
    ----------
    heatmap_engine : HeatmapEngine instance

    Returns
    -------
    (app, socketio)
    """
    try:
        from flask import Flask, jsonify, render_template, request, send_from_directory
        from flask_socketio import SocketIO, emit
    except ImportError:
        log.error("flask or flask-socketio not installed. Run: pip install flask flask-socketio")
        return None, None

    from pathlib import Path
    template_dir = Path(__file__).resolve().parent / "templates"

    app     = Flask(__name__, template_folder=str(template_dir))
    socketio = SocketIO(app, async_mode="threading", cors_allowed_origins="*",
                        logger=False, engineio_logger=False)

    # ── REST routes ───────────────────────────────────────────────────────────

    @app.route("/")
    def index():
        return send_from_directory(str(template_dir), "index.html")

    @app.route("/heatmap")
    def heatmap():
        window = int(request.args.get("minutes", 60))
        try:
            b64 = heatmap_engine.generate_heatmap_b64(window)
            return jsonify({"image": b64, "minutes": window})
        except Exception as exc:
            log.error("/heatmap error: %s", exc)
            return jsonify({"image": "", "minutes": window})

    @app.route("/stats")
    def stats():
        try:
            return jsonify(heatmap_engine.get_session_stats())
        except Exception as exc:
            log.error("/stats error: %s", exc)
            return jsonify({})

    @app.route("/history")
    def history():
        try:
            days = int(request.args.get("days", 7))
            from datetime import date, timedelta
            result = []
            for i in range(days):
                d = date.today() - timedelta(days=i)
                result.append({"date": str(d), "placeholder": True})
            return jsonify(result)
        except Exception as exc:
            log.error("/history error: %s", exc)
            return jsonify([])

    @app.route("/fatigue")
    def fatigue():
        try:
            return jsonify(heatmap_engine.get_fatigue_curve())
        except Exception as exc:
            log.error("/fatigue error: %s", exc)
            return jsonify([])

    @app.route("/distribution")
    def distribution():
        try:
            return jsonify(heatmap_engine.get_gesture_distribution())
        except Exception as exc:
            log.error("/distribution error: %s", exc)
            return jsonify({})

    @app.route("/hourly")
    def hourly():
        try:
            return jsonify(heatmap_engine.get_hourly_counts())
        except Exception as exc:
            log.error("/hourly error: %s", exc)
            return jsonify([])

    @app.route("/compare")
    def compare():
        sid1 = request.args.get("session_id_1", "")
        sid2 = request.args.get("session_id_2", "")
        if not sid1 or not sid2:
            return jsonify({"error": "Provide session_id_1 and session_id_2"}), 400
        try:
            return jsonify(heatmap_engine.compare_sessions(sid1, sid2))
        except Exception as exc:
            log.error("/compare error: %s", exc)
            return jsonify({})

    # ── SocketIO events ───────────────────────────────────────────────────────

    @socketio.on("connect")
    def on_connect():
        """Send initial full dataset when a client connects."""
        try:
            emit("stats",        heatmap_engine.get_session_stats())
            emit("distribution", heatmap_engine.get_gesture_distribution())
            emit("fatigue",      heatmap_engine.get_fatigue_curve())
            emit("hourly",       heatmap_engine.get_hourly_counts())
            emit("heatmap",      {"image": heatmap_engine.generate_heatmap_b64(60)})
        except Exception as exc:
            log.debug("on_connect emit error: %s", exc)

    # Background push task
    def _push_loop():
        while True:
            time.sleep(2.0)
            try:
                socketio.emit("stats",        heatmap_engine.get_session_stats())
                socketio.emit("distribution", heatmap_engine.get_gesture_distribution())
                socketio.emit("heatmap",      {"image": heatmap_engine.generate_heatmap_b64(60)})
            except Exception as exc:
                log.debug("push_loop error: %s", exc)

    push_thread = threading.Thread(target=_push_loop, daemon=True,
                                   name="socketio-push")
    push_thread.start()

    return app, socketio


def launch_dashboard(heatmap_engine, port: int = 5050,
                     auto_open: bool = True) -> Optional[threading.Thread]:
    """
    Create app, start SocketIO server in a daemon thread.
    If auto_open=True, open browser after 1.5s delay.
    Returns the server thread (or None on failure).
    """
    app, socketio = create_app(heatmap_engine)
    if app is None:
        return None

    def _run():
        try:
            socketio.run(app, host="127.0.0.1", port=port,
                         debug=False, use_reloader=False, log_output=False)
        except Exception as exc:
            log.error("Dashboard server error: %s", exc)

    server_thread = threading.Thread(target=_run, daemon=True,
                                     name="dashboard-server")
    server_thread.start()
    log.info("Dashboard launched at http://127.0.0.1:%d", port)

    if auto_open:
        def _open_browser():
            time.sleep(1.5)
            url = f"http://127.0.0.1:{port}"
            try:
                webbrowser.open(url)
                log.info("Browser opened: %s", url)
            except Exception as exc:
                log.debug("webbrowser.open error: %s", exc)

        threading.Thread(target=_open_browser, daemon=True,
                         name="browser-opener").start()

    return server_thread
