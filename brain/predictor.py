"""
brain/predictor.py
PredictiveEngine: Learns command patterns and predicts what the user will ask next.

Stores co-occurrence matrix in SQLite (via memory.manager).
Uses frequency analysis to surface the most likely next command.
"""
from __future__ import annotations
import time
import threading
from collections import defaultdict, deque
from config.logger import get_logger

log = get_logger("predictor")

# Minimum co-occurrence count before predicting
MIN_CONFIDENCE = 3
# Recent command window for context
CONTEXT_WINDOW = 5


class PredictiveEngine:
    """
    Tracks command sequences and predicts the user's next command.

    Usage:
        engine = PredictiveEngine(memory_manager)
        engine.record("open gmail")          # Called after each command
        prediction = engine.predict("open gmail")   # Returns likely next cmd
    """

    def __init__(self, memory=None):
        self.memory = memory
        self._lock = threading.Lock()
        # In-memory co-occurrence: {prev_cmd: {next_cmd: count}}
        self._matrix: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        # Recent command ring buffer for multi-step context
        self._recent: deque = deque(maxlen=CONTEXT_WINDOW)
        # Load from DB on startup
        self._load_patterns()
        log.info("PredictiveEngine ready.")

    # ── Public API ─────────────────────────────────────────────────────────────

    def record(self, command: str):
        """
        Record a new command execution.
        Updates co-occurrence with the previous command.
        """
        if not command or len(command) < 3:
            return
        normalized = self._normalize(command)
        with self._lock:
            if self._recent:
                prev = self._recent[-1]
                self._matrix[prev][normalized] += 1
                self._persist_pattern(prev, normalized)
            self._recent.append(normalized)
        log.debug(f"[Predictor] Recorded: {normalized}")

    def predict(self, last_command: str, top_n: int = 1) -> list[str]:
        """
        Predict the most likely next command(s) given the last command.
        Returns list of (command, confidence_score) tuples.
        """
        normalized = self._normalize(last_command)
        with self._lock:
            candidates = dict(self._matrix.get(normalized, {}))
        if not candidates:
            return []
        # Sort by frequency, filter by minimum confidence
        ranked = sorted(candidates.items(), key=lambda x: x[1], reverse=True)
        results = [
            cmd for cmd, count in ranked
            if count >= MIN_CONFIDENCE and cmd != normalized
        ]
        return results[:top_n]

    def get_confidence(self, last_cmd: str, next_cmd: str) -> float:
        """Returns 0.0–1.0 confidence that next_cmd follows last_cmd."""
        last = self._normalize(last_cmd)
        next_ = self._normalize(next_cmd)
        with self._lock:
            row = self._matrix.get(last, {})
            total = sum(row.values())
            if total == 0:
                return 0.0
            return row.get(next_, 0) / total

    def top_predictions(self, limit: int = 3) -> list[str]:
        """Return globally most frequent next-commands across all contexts."""
        global_counts: dict[str, int] = defaultdict(int)
        with self._lock:
            for next_cmds in self._matrix.values():
                for cmd, count in next_cmds.items():
                    global_counts[cmd] += count
        ranked = sorted(global_counts.items(), key=lambda x: x[1], reverse=True)
        return [cmd for cmd, _ in ranked[:limit]]

    # ── Persistence ────────────────────────────────────────────────────────────

    def _persist_pattern(self, prev: str, next_: str):
        """Save or update a co-occurrence record in the DB."""
        if not self.memory:
            return
        try:
            if hasattr(self.memory, "save_command_pattern"):
                self.memory.save_command_pattern(prev, next_)
        except Exception as e:
            log.debug(f"[Predictor] Persist failed: {e}")

    def _load_patterns(self):
        """Load co-occurrence matrix from DB."""
        if not self.memory:
            return
        try:
            if hasattr(self.memory, "get_command_patterns"):
                patterns = self.memory.get_command_patterns()
                with self._lock:
                    for row in patterns:
                        prev = row.get("prev_cmd", "")
                        next_ = row.get("next_cmd", "")
                        count = row.get("count", 1)
                        if prev and next_:
                            self._matrix[prev][next_] = count
                log.info(f"[Predictor] Loaded {len(self._matrix)} pattern(s) from DB.")
        except Exception as e:
            log.debug(f"[Predictor] Load failed: {e}")

    @staticmethod
    def _normalize(cmd: str) -> str:
        """Lowercase and strip for consistent keys."""
        return (cmd or "").lower().strip()[:80]
