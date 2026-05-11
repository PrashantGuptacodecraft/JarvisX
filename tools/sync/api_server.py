"""
tools/sync/api_server.py
Cross-device REST API server for JarvisX.

Runs a local FastAPI server on port 7777.
Mobile apps or other devices can POST commands and GET status.

Endpoints:
  POST /command         {"text": "open gmail"}
  GET  /status          → {"status": "listening", "last_reply": "..."}
  POST /clipboard       {"content": "text to sync"}
  GET  /notifications   → list of recent notifications
"""
from __future__ import annotations
import threading
import logging
import time
from typing import Optional, Callable
from collections import deque

log = logging.getLogger("api_server")

_DEFAULT_PORT = 7777
_MAX_NOTIFICATIONS = 20


class CrossDeviceServer:
    """
    Lightweight FastAPI server for cross-device JarvisX control.
    Runs in a background thread.
    """

    def __init__(
        self,
        command_queue=None,
        port: int = _DEFAULT_PORT,
        status_provider: Optional[Callable] = None,
    ):
        self.command_queue = command_queue
        self.port = port
        self.status_provider = status_provider
        self.available: bool = False
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_reply: str = ""
        self._notifications: deque = deque(maxlen=_MAX_NOTIFICATIONS)
        self._app = None

    def start(self) -> str:
        """Start the API server in a background thread."""
        try:
            import fastapi  # noqa: F401
            import uvicorn  # noqa: F401
            self.available = True
        except ImportError:
            log.warning(
                "CrossDeviceServer: fastapi or uvicorn not installed. "
                "Run: pip install fastapi uvicorn   (cross-device sync disabled)"
            )
            return "Cross-device sync not available."

        self._build_app()
        self._running = True
        self._thread = threading.Thread(
            target=self._serve, daemon=True, name="jarvis-api-server"
        )
        self._thread.start()
        log.info(f"CrossDeviceServer started on port {self.port}.")
        return f"Cross-device API running on http://0.0.0.0:{self.port}"

    def stop(self):
        self._running = False

    def push_notification(self, title: str, message: str):
        """Add a notification for cross-device delivery."""
        self._notifications.append({
            "title": title,
            "message": message,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        })

    def update_last_reply(self, reply: str):
        """Update the last Jarvis reply for status endpoint."""
        self._last_reply = reply[:300] if reply else ""

    def _build_app(self):
        from fastapi import FastAPI
        from fastapi.responses import JSONResponse
        from fastapi.middleware.cors import CORSMiddleware
        import pydantic

        app = FastAPI(title="JarvisX API", version="1.0")
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )

        class CommandRequest(pydantic.BaseModel):
            text: str

        class ClipboardRequest(pydantic.BaseModel):
            content: str

        @app.get("/")
        def root():
            return {"service": "JarvisX", "status": "online"}

        @app.post("/command")
        def command(req: CommandRequest):
            if self.command_queue and req.text.strip():
                self.command_queue.put(f"__VOICE__:{req.text.strip()}")
                return {"queued": True, "command": req.text}
            return JSONResponse(status_code=400, content={"error": "No text or queue."})

        @app.get("/status")
        def status():
            current = ""
            if self.status_provider:
                try:
                    current = self.status_provider()
                except Exception:
                    pass
            return {
                "status": current or "unknown",
                "last_reply": self._last_reply,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }

        @app.post("/clipboard")
        def clipboard(req: ClipboardRequest):
            try:
                import pyperclip
                pyperclip.copy(req.content)
                return {"synced": True}
            except Exception as e:
                return JSONResponse(status_code=500, content={"error": str(e)})

        @app.get("/notifications")
        def notifications():
            return {"notifications": list(self._notifications)}

        self._app = app

    def _serve(self):
        import uvicorn
        try:
            uvicorn.run(
                self._app,
                host="0.0.0.0",
                port=self.port,
                log_level="error",
                access_log=False,
            )
        except Exception as e:
            log.error(f"CrossDeviceServer error: {e}")
