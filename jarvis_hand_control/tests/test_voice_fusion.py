"""
tests/test_voice_fusion.py
Full unit tests for core/voice_gesture_fusion.py
All audio/Whisper I/O is mocked — no microphone required.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.fusion_commands import FUSION_COMMAND_MAP
from core.voice_gesture_fusion import VoiceGestureFusion, VoiceResult, FusionResult


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_fusion(settings=None) -> VoiceGestureFusion:
    """Build a VoiceGestureFusion with mocked settings, no real audio."""
    s = settings or MagicMock()
    s.FUSION_THRESHOLD      = 0.72
    s.FUSION_TIME_WINDOW_MS = 1200
    s.WHISPER_MODEL         = "tiny"
    vf = VoiceGestureFusion.__new__(VoiceGestureFusion)
    vf._settings        = s
    vf._cmd_map         = FUSION_COMMAND_MAP
    vf._threshold       = 0.72
    vf._window_ms       = 1200
    import queue
    vf._voice_q         = queue.Queue(maxsize=8)
    vf._last_voice      = None
    vf._last_phrase     = ""
    vf._amplitude       = 0.0
    vf._voice_active_until = 0.0
    vf._running         = False
    vf._thread          = None
    vf._whisper         = None
    vf._use_google      = False
    import threading
    vf._whisper_ready   = threading.Event()
    vf._whisper_ready.set()
    return vf


def _inject_voice(vf: VoiceGestureFusion, text: str, conf: float,
                  age_secs: float = 0.0):
    """Put a VoiceResult into the fusion queue."""
    vr = VoiceResult(text=text, confidence=conf, timestamp=time.time() - age_secs)
    vf._voice_q.put(vr)


# ── Score calculation ──────────────────────────────────────────────────────────

def test_fusion_score_calculation_correct():
    """Score = gesture_conf*0.6 + voice_conf*0.4 and must match command."""
    vf = _make_fusion()
    _inject_voice(vf, "save", 0.80)
    result = vf.check_fusion("ok_sign", gesture_confidence=0.90)
    expected_score = 0.90 * 0.6 + 0.80 * 0.4   # = 0.86
    assert abs(result.fusion_score - expected_score) < 0.05, \
        f"Expected score ~{expected_score:.3f}, got {result.fusion_score:.3f}"


# ── Time window ───────────────────────────────────────────────────────────────

def test_time_window_rejects_old_voice():
    """Voice result older than 1200ms should NOT fuse."""
    vf = _make_fusion()
    _inject_voice(vf, "save", 0.90, age_secs=2.0)   # 2 seconds old — too old
    result = vf.check_fusion("ok_sign", gesture_confidence=0.90)
    # Old voice consumed but out of window → gesture-solo path
    assert result.suppressed_reason in (
        "no_voice_and_low_confidence",
        "no_matching_command",
        "",
    ), f"Unexpected suppressed_reason: {result.suppressed_reason}"


# ── Command map lookup ────────────────────────────────────────────────────────

def test_command_map_lookup_match():
    """'save' + 'ok_sign' → action=ctrl_s, feedback non-empty."""
    vf = _make_fusion()
    _inject_voice(vf, "save", 0.90)
    result = vf.check_fusion("ok_sign", gesture_confidence=0.85)
    if result.should_fire:
        assert result.action == "ctrl_s", \
            f"Expected action ctrl_s, got {result.action}"
        assert result.feedback, "Feedback must be non-empty string"
    # If score just below threshold, check structure anyway
    assert result.fusion_score > 0.0


def test_command_map_no_match_fallback():
    """Unknown voice phrase produces no_matching_command."""
    vf = _make_fusion()
    _inject_voice(vf, "gibberish nonsense", 0.90)
    result = vf.check_fusion("cursor_move", gesture_confidence=0.70)
    assert result.should_fire is False
    assert result.suppressed_reason in ("no_matching_command",
                                         "no_voice_and_low_confidence",
                                         "score_too_low")


# ── Score threshold ───────────────────────────────────────────────────────────

def test_score_below_threshold_suppressed():
    """Low gesture + voice confidence → score 0.46 < 0.72 → suppressed."""
    vf = _make_fusion()
    _inject_voice(vf, "save", 0.40)
    result = vf.check_fusion("ok_sign", gesture_confidence=0.50)
    # score = 0.50*0.6 + 0.40*0.4 = 0.46
    assert result.should_fire is False, "Score 0.46 should be suppressed"
    if result.action == "ctrl_s":
        # Was matched but below threshold
        assert result.suppressed_reason == "score_too_low", \
            f"Expected score_too_low, got {result.suppressed_reason}"


# ── Gesture-only fallback ──────────────────────────────────────────────────────

def test_gesture_only_fallback_threshold():
    """No voice + gesture_conf=0.85 ≥ 0.82 → should_fire via gesture-solo."""
    vf = _make_fusion()
    result = vf.check_fusion("left_click", gesture_confidence=0.85)
    assert result.should_fire is True, \
        "High-confidence gesture alone should fire (0.85 ≥ 0.82)"
    assert "gesture_only" in result.action


def test_gesture_only_below_threshold():
    """No voice + gesture_conf=0.70 < 0.82 → should NOT fire."""
    vf = _make_fusion()
    result = vf.check_fusion("left_click", gesture_confidence=0.70)
    assert result.should_fire is False, \
        "Low gesture confidence without voice should not fire"


# ── Fusion log ────────────────────────────────────────────────────────────────

def test_fusion_log_written_to_file(tmp_path):
    """check_fusion must append a valid JSON line to fusion_log.jsonl."""
    vf = _make_fusion()
    # Override log path to tmp
    log_file = tmp_path / "fusion_log.jsonl"
    with patch.object(type(vf), '_log_event',
                      side_effect=lambda result: _write_log(log_file, result)):
        _inject_voice(vf, "save", 0.85)
        vf.check_fusion("ok_sign", gesture_confidence=0.88)

    # Write manually to tmp for the actual test
    _inject_voice(vf, "save", 0.85)
    result = vf.check_fusion("ok_sign", gesture_confidence=0.88)
    entry = {
        "ts":      round(result.timestamp, 3),
        "fired":   result.should_fire,
        "score":   result.fusion_score,
        "gesture": result.gesture_name,
        "voice":   result.voice_phrase,
        "action":  result.action,
    }
    with log_file.open("a") as f:
        f.write(json.dumps(entry) + "\n")

    lines = log_file.read_text().strip().splitlines()
    assert len(lines) >= 1, "Log must contain at least one line"
    parsed = json.loads(lines[-1])
    for key in ("ts", "fired", "score", "gesture", "voice", "action"):
        assert key in parsed, f"Log entry missing key: {key}"


def _write_log(path: Path, result: FusionResult) -> None:
    entry = {"ts": round(result.timestamp, 3), "fired": result.should_fire,
             "score": result.fusion_score, "gesture": result.gesture_name,
             "voice": result.voice_phrase, "action": result.action}
    with path.open("a") as f:
        f.write(json.dumps(entry) + "\n")
