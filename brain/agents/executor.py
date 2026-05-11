"""
brain/agents/executor.py
ExecutorAgent: Runs system actions, app launches, terminal commands.
"""
from __future__ import annotations
import threading
import time
from config.logger import get_logger

log = get_logger("agent.executor")


class ExecutorAgent:
    """Executes system-level actions as part of a multi-agent pipeline."""

    def __init__(self, brain):
        self.brain = brain
        self.results: list[dict] = []
        self.done: bool = False
        self.error: str = ""

    def run(self, actions: list[str]) -> list[dict]:
        """
        Execute a list of action strings sequentially.
        Each action is processed by brain.process().
        Returns list of {action, result, ok} dicts.
        """
        self.done = False
        self.results = []
        self.error = ""
        log.info(f"[Executor] Running {len(actions)} action(s)")
        for action in actions:
            try:
                result = self.brain.process(action)
                ok = True
                log.info(f"[Executor] OK: {action[:60]}")
            except Exception as e:
                result = str(e)
                ok = False
                log.error(f"[Executor] Failed: {action[:60]} → {e}")
            self.results.append({"action": action, "result": result, "ok": ok})
            time.sleep(0.2)  # brief pause between actions
        self.done = True
        return self.results

    def run_async(self, actions: list[str]) -> threading.Thread:
        """Run actions in a background thread."""
        t = threading.Thread(target=self.run, args=(actions,), daemon=True)
        t.start()
        return t

    def wait(self, timeout: float = 30.0) -> list[dict]:
        """Wait for async results."""
        deadline = time.time() + timeout
        while not self.done and time.time() < deadline:
            time.sleep(0.1)
        return self.results

    def summary(self) -> str:
        """Return human-readable execution summary."""
        ok = [r for r in self.results if r["ok"]]
        failed = [r for r in self.results if not r["ok"]]
        if not self.results:
            return "No actions were executed."
        if not failed:
            return f"All {len(ok)} action(s) completed successfully."
        return (
            f"{len(ok)}/{len(self.results)} actions succeeded. "
            f"Failed: {', '.join(r['action'][:30] for r in failed[:3])}"
        )
