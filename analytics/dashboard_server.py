"""
analytics/dashboard_server.py
Flask-based real-time analytics dashboard.
Serves live gesture stats as JSON + an HTML dashboard page.
Run in a background thread — does NOT block the gesture engine.
"""
from __future__ import annotations
import json
import logging
import os
import threading
import time
from typing import Optional

log = logging.getLogger("dashboard_server")

_TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")


class DashboardServer:
    """
    Lightweight Flask server serving gesture analytics.
    Runs in a daemon thread so it never blocks the main gesture loop.

    Usage
    -----
    server = DashboardServer(heatmap_engine, port=5050)
    server.start()
    """

    def __init__(self, heatmap_engine=None,
                 port: int = 5050,
                 settings=None) -> None:
        self._engine  = heatmap_engine
        self._port    = port
        if settings:
            self._port = settings.analytics.dashboard_port
        self._thread: Optional[threading.Thread] = None
        self._app     = None
        self._session_start = time.time()
        self._gesture_log: list[dict] = []  # rolling log (last 200)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        try:
            from flask import Flask, jsonify, send_from_directory
        except ImportError:
            log.warning("Flask not installed — dashboard disabled. pip install flask")
            return

        app = Flask(__name__, template_folder=_TEMPLATE_DIR,
                    static_folder=_TEMPLATE_DIR)
        self._app = app

        @app.route("/")
        def index():
            return send_from_directory(_TEMPLATE_DIR, "index.html")

        @app.route("/api/stats")
        def api_stats():
            stats = self._engine.get_stats() if self._engine else {}
            return jsonify({
                "uptime_s":     round(time.time() - self._session_start, 1),
                "total_events": stats.get("total", 0),
                "by_gesture":   stats.get("by_gesture", {}),
                "recent_log":   self._gesture_log[-50:],
                "timestamp":    time.time(),
            })

        @app.route("/api/reset", methods=["POST"])
        def api_reset():
            if self._engine:
                self._engine.reset()
            self._gesture_log.clear()
            return jsonify({"status": "ok"})

        self._thread = threading.Thread(
            target=lambda: app.run(host="127.0.0.1", port=self._port,
                                   debug=False, use_reloader=False),
            daemon=True, name="dashboard-server"
        )
        self._thread.start()
        log.info("Dashboard running at http://127.0.0.1:%d", self._port)

    def log_gesture(self, gesture: str, x: int = 0, y: int = 0) -> None:
        """Call from the main engine each time a gesture fires."""
        entry = {"gesture": gesture, "x": x, "y": y, "t": round(time.time(), 3)}
        self._gesture_log.append(entry)
        if len(self._gesture_log) > 200:
            self._gesture_log.pop(0)

    def stop(self) -> None:
        pass  # daemon thread exits with process
