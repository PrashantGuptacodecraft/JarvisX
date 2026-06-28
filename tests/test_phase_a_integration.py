"""Phase A integration tests — milestones A7 (three live publishers) + A8 (one live subscriber).

Drives the REAL publisher code paths (core_loop, ContextWatcher, Listener) against the REAL
process-wide bus singleton, with a live subscriber observing. No microphone/camera needed.

Run:  python -m pytest tests/test_phase_a_integration.py -v
"""
from __future__ import annotations

import queue
import threading
import time

from shared_core import get_bus
from core_loop import CoreLoop
from tools.system.context_watcher import ContextWatcher
from voice.listener import Listener


class _Collector:
    """A8: a live subscriber that records every event topic seen on the bus."""

    def __init__(self):
        self.topics: list[str] = []
        self._lock = threading.Lock()

    def __call__(self, event):
        with self._lock:
            self.topics.append(event.topic)

    def seen(self, topic: str) -> bool:
        with self._lock:
            return topic in self.topics


class _StubBrain:
    pending = None

    def process(self, text, voice_mode=False):
        return "stub ok"


def test_three_publishers_and_one_subscriber():
    bus = get_bus()
    collector = _Collector()
    sub = bus.subscribe("*", collector, source="test_collector")   # A8: live subscriber
    try:
        # ── Publisher 1: core_loop -> cognition.intent + action.result ──────────
        core = CoreLoop(queue.Queue(), _StubBrain(), speaker=None, gui=None, memory=None)
        core._process("system status report")

        # ── Publisher 2: ContextWatcher -> perception.os.active_window ──────────
        cw = ContextWatcher(_StubBrain())
        cw._get_active_window_title = lambda: "IntegrationTest Window"   # no real window needed
        cw.start()
        time.sleep(0.3)
        cw.stop()

        # ── Publisher 3: Listener.inject_text -> perception.voice.heard ─────────
        original_init_mic = Listener._init_mic
        Listener._init_mic = lambda self: None          # skip hardware for the test
        try:
            lis = Listener(command_queue=queue.Queue())
            lis.always_listening = True                 # route straight to the publish path
            lis.active_mode = True
            lis.inject_text("what time is it")
        finally:
            Listener._init_mic = original_init_mic

        # ── A7: all three publishers observed at runtime ───────────────────────
        bus.drain(timeout=3.0)
        assert collector.seen("cognition.intent"),         "core_loop intent not observed"
        assert collector.seen("action.result"),            "core_loop result not observed"
        assert collector.seen("perception.os.active_window"), "ContextWatcher not observed"
        assert collector.seen("perception.voice.heard"),   "Listener not observed"
    finally:
        bus.unsubscribe(sub)
