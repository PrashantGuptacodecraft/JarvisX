"""
brain/agents/orchestrator.py
AgentOrchestrator: Coordinates parallel researcher + writer + executor agents.

Usage:
    orch = AgentOrchestrator(ai_client, brain, tools)
    result = orch.run("Research AI trends, write a report, and email it to me")
"""
from __future__ import annotations
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from config.logger import get_logger
from config.settings import USER_NAME
from brain.agents.researcher import ResearcherAgent
from brain.agents.writer import WriterAgent
from brain.agents.executor import ExecutorAgent

log = get_logger("agent.orchestrator")


class AgentOrchestrator:
    """
    Multi-agent coordinator.
    Decomposes complex tasks into parallel research + sequential write/execute pipeline.
    """

    def __init__(self, ai_client, brain, tools: dict):
        self.ai = ai_client
        self.brain = brain
        self.tools = tools
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="jarvis-agent")

    def is_multi_agent_task(self, task: str) -> bool:
        """Returns True ONLY for genuinely complex multi-step parallel tasks.
        Must have compound markers (and then / after that) PLUS research+write signals.
        Simple commands like 'open chrome' or 'send message' must NOT trigger this."""
        low = task.lower()

        # Hard-blocklist: these are always single-intent commands
        single_intent_prefixes = [
            "open ", "close ", "play ", "search ", "send ", "message ",
            "call ", "show ", "what ", "how ", "tell me", "remind ",
            "turn ", "set ", "check ", "read ", "find ", "launch ",
            "enable ", "disable ", "start ", "stop ", "record ",
        ]
        for prefix in single_intent_prefixes:
            if low.strip().startswith(prefix):
                return False

        # Must contain an explicit compound task connector
        compound_markers = [
            " and then ", " after that ", " followed by ", " also ",
            " then ", ", then", " and also ", " afterwards ",
        ]
        has_compound = any(m in low for m in compound_markers)
        if not has_compound:
            return False

        # Must score 3+ across research + write + action signals
        research_signals = ["research", "find out", "gather", "collect info", "look into"]
        write_signals    = ["write", "draft", "create report", "generate", "compose", "summarize"]
        action_signals   = ["email", "whatsapp", "launch", "execute", "deploy"]
        signals = (
            sum(1 for s in research_signals if s in low) +
            sum(1 for s in write_signals    if s in low) +
            sum(1 for s in action_signals   if s in low)
        )
        return signals >= 2

    def run(self, task: str, gui_log=None) -> str:
        """
        Orchestrate a complex multi-step task using parallel agents.
        Pipeline: [Research] → [Write] → [Execute]
        """
        log.info(f"[Orchestrator] Starting: {task[:80]}")
        if gui_log:
            gui_log(f"[MULTI-AGENT] Orchestrating: {task}")

        # Step 1: Decompose task
        sub_tasks = self._decompose(task)
        if gui_log:
            gui_log(f"[DECOMPOSE] {len(sub_tasks)} sub-tasks identified")

        research_tasks = sub_tasks.get("research", [])
        write_tasks = sub_tasks.get("write", [])
        action_tasks = sub_tasks.get("execute", [])

        # Step 2: Parallel research phase
        research_results = {}
        if research_tasks:
            if gui_log:
                gui_log(f"[RESEARCH] Running {len(research_tasks)} parallel research agent(s)...")
            futures = {}
            for rt in research_tasks:
                agent = ResearcherAgent(
                    self.ai,
                    web_controller=self.tools.get("web"),
                    memory=self.tools.get("memory"),
                )
                future = self._executor.submit(agent.run, rt)
                futures[future] = rt
            for future in as_completed(futures, timeout=25):
                rt = futures[future]
                try:
                    research_results[rt] = future.result()
                    if gui_log:
                        gui_log(f"[RESEARCH OK] {rt[:40]}")
                except Exception as e:
                    research_results[rt] = f"Research error: {e}"
                    log.warning(f"[Orchestrator] Research failed: {e}")

        research_context = "\n\n".join(
            f"Research on '{k}':\n{v}" for k, v in research_results.items()
        )

        # Step 3: Writing phase (uses research context)
        write_results = []
        if write_tasks:
            if gui_log:
                gui_log(f"[WRITE] Generating {len(write_tasks)} document(s)...")
            for wt in write_tasks:
                agent = WriterAgent(self.ai, memory=self.tools.get("memory"))
                result = agent.run(wt, context=research_context)
                write_results.append(result)
                if gui_log:
                    gui_log(f"[WRITE OK] {wt[:40]}")

        # Step 4: Execution phase (app actions, messaging, etc.)
        exec_results = []
        if action_tasks:
            if gui_log:
                gui_log(f"[EXECUTE] Running {len(action_tasks)} system action(s)...")
            agent = ExecutorAgent(self.brain)
            exec_results = agent.run(action_tasks)
            for r in exec_results:
                status = "OK" if r["ok"] else "FAIL"
                if gui_log:
                    gui_log(f"[{status}] {r['action'][:40]}")

        # Step 5: Build final summary
        return self._build_summary(task, research_results, write_results, exec_results)

    def _decompose(self, task: str) -> dict:
        """Use AI to decompose task into research/write/execute buckets."""
        prompt = f"""Decompose this task into sub-tasks for parallel agents.

Task: "{task}"

Return JSON with this exact format:
{{
  "research": ["search topic 1", "find info about X"],
  "write": ["write report about ...", "draft email about ..."],
  "execute": ["open gmail", "send message to ..."]
}}

Rules:
- research: information gathering sub-tasks (web search, data collection)
- write: content generation sub-tasks (documents, emails, summaries)  
- execute: system actions (open apps, send messages, launch programs)
- Keep each item short and actionable
- Omit empty categories
- Max 3 items per category
- Return ONLY valid JSON, no markdown"""

        import json, re
        raw = self.ai.chat(prompt)
        # Extract JSON
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except Exception:
                pass
        # Fallback: treat entire task as single execute
        return {"execute": [task]}

    def _build_summary(
        self,
        task: str,
        research: dict,
        write_results: list,
        exec_results: list,
    ) -> str:
        parts = []
        if research:
            best = next(iter(research.values()), "")
            if best:
                parts.append(best[:300])
        if write_results:
            parts.append(write_results[0][:300])
        if exec_results:
            ok = sum(1 for r in exec_results if r["ok"])
            parts.append(f"Executed {ok}/{len(exec_results)} system action(s).")
        if parts:
            return " ".join(parts)
        return f"Task complete, {USER_NAME}."
