"""Phase A acceptance tests for the Event Bus (milestones A1-A6, A9, + unsubscribe/drain).

Run:  python -m pytest tests/test_event_bus.py -v
      python -m unittest tests.test_event_bus      (also works; pure stdlib asserts)
"""
from __future__ import annotations

import threading
import time

from shared_core import get_bus
from shared_core.event_bus import ASYNC, SYNC, EventBus, topics
from shared_core.event_bus.subscription import _BoundedBuffer
from shared_core.event_bus.event import Event


# ── A1: thread-safe publish/subscribe ────────────────────────────────────────
def test_basic_pubsub_sync():
    bus = EventBus("t")
    got = []
    bus.subscribe("action.result", got.append, mode=SYNC, source="t")
    bus.publish("action.result", {"ok": True}, source="test")
    assert len(got) == 1
    assert got[0].payload == {"ok": True}
    assert got[0].topic == "action.result"


def test_thread_safety_concurrent_publishers():
    bus = EventBus("t")
    received = []
    lock = threading.Lock()

    def handler(ev):
        with lock:
            received.append(ev.id)

    bus.subscribe("perception.*", handler, mode=ASYNC, source="t", maxlen=100000)

    N_THREADS, PER = 8, 250

    def worker(i):
        for j in range(PER):
            bus.publish(f"perception.os.x{i}", {"j": j}, source=f"w{i}")

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(N_THREADS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert bus.drain(timeout=5.0)
    assert len(received) == N_THREADS * PER          # nothing lost, nothing duplicated
    assert len(set(received)) == N_THREADS * PER     # unique ids


# ── A2: wildcard subscriptions ───────────────────────────────────────────────
def test_wildcard_matching():
    assert topics.matches("*", "anything.here")
    assert topics.matches("perception.*", "perception.os.snapshot")
    assert topics.matches("perception.*", "perception.screen.ocr")
    assert topics.matches("perception.os.*", "perception.os.snapshot")
    assert topics.matches("action.result", "action.result")
    assert not topics.matches("perception.*", "action.result")
    assert not topics.matches("perception.os.*", "perception.screen.ocr")


def test_wildcard_delivery():
    bus = EventBus("t")
    got = []
    bus.subscribe("perception.*", got.append, mode=SYNC, source="t")
    bus.publish("perception.os.x", {}, source="s")
    bus.publish("perception.screen.y", {}, source="s")
    bus.publish("action.result", {}, source="s")   # must NOT be delivered
    assert [e.topic for e in got] == ["perception.os.x", "perception.screen.y"]


# ── A3: SYNC delivery runs inline on the publisher thread ─────────────────────
def test_sync_runs_on_publisher_thread():
    bus = EventBus("t")
    seen = {}

    def handler(ev):
        seen["tid"] = threading.get_ident()

    bus.subscribe("x", handler, mode=SYNC, source="t")
    bus.publish("x", {}, source="s")
    assert seen["tid"] == threading.get_ident()     # same thread = inline/ordered


# ── A4: ASYNC delivery runs off-thread and never blocks the publisher ─────────
def test_async_nonblocking():
    bus = EventBus("t")
    started = threading.Event()
    release = threading.Event()
    handler_thread = {}

    def slow(ev):
        handler_thread["tid"] = threading.get_ident()
        started.set()
        release.wait(2.0)

    bus.subscribe("x", slow, mode=ASYNC, source="t")
    t0 = time.monotonic()
    bus.publish("x", {}, source="s")
    publish_elapsed = time.monotonic() - t0
    assert publish_elapsed < 0.2                    # publisher returned immediately
    assert started.wait(2.0)
    assert handler_thread["tid"] != threading.get_ident()   # ran on a worker thread
    release.set()
    assert bus.drain(timeout=3.0)


# ── A5: backpressure / drop-oldest (white-box on the bounded buffer) ──────────
def test_backpressure_drop_oldest():
    buf = _BoundedBuffer(maxlen=3, coalesce_key=None)
    for i in range(5):                              # 5 into a size-3 buffer
        buf.put(Event(topic="x", payload={"i": i}))
    assert buf.dropped == 2                         # exactly 2 oldest dropped
    assert buf.pending() == 3
    remaining = [buf.get(0.01).payload["i"] for _ in range(3)]
    assert remaining == [2, 3, 4]                   # oldest (0,1) gone, newest kept, FIFO


# ── A6: coalescing / latest-wins per key ─────────────────────────────────────
def test_coalescing_latest_wins():
    buf = _BoundedBuffer(maxlen=10, coalesce_key=lambda e: e.payload["k"])
    for i in range(6):
        buf.put(Event(topic="x", payload={"k": "same", "v": i}))
    assert buf.pending() == 1                       # collapsed to one
    assert buf.coalesced == 5
    ev = buf.get(0.01)
    assert ev.payload["v"] == 5                     # the latest value survived


def test_coalescing_multiple_keys_order():
    buf = _BoundedBuffer(maxlen=10, coalesce_key=lambda e: e.payload["k"])
    buf.put(Event(topic="x", payload={"k": "a", "v": 1}))
    buf.put(Event(topic="x", payload={"k": "b", "v": 1}))
    buf.put(Event(topic="x", payload={"k": "a", "v": 2}))   # updates a, keeps order
    assert buf.pending() == 2
    first = buf.get(0.01)
    second = buf.get(0.01)
    assert (first.payload["k"], first.payload["v"]) == ("a", 2)
    assert (second.payload["k"], second.payload["v"]) == ("b", 1)


# ── unsubscribe ──────────────────────────────────────────────────────────────
def test_unsubscribe_stops_delivery():
    bus = EventBus("t")
    got = []
    sub = bus.subscribe("x", got.append, mode=SYNC, source="t")
    bus.publish("x", {}, source="s")
    bus.unsubscribe(sub)
    bus.publish("x", {}, source="s")
    assert len(got) == 1                            # only the pre-unsubscribe event
    assert bus.subscription_count() == 0


# ── stats / drain ────────────────────────────────────────────────────────────
def test_stats_reports_counts_and_drops():
    bus = EventBus("t")
    bus.subscribe("x", lambda e: None, mode=SYNC, source="t")
    for _ in range(4):
        bus.publish("x", {}, source="s")
    st = bus.stats()
    assert st["published_total"] == 4
    assert st["published_by_topic"]["x"] == 4
    assert "subscriptions" in st


def test_singleton_get_bus():
    assert get_bus() is get_bus()
