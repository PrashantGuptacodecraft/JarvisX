"""
brain/planner.py
Structured autonomous planner for chained commands.
"""

from __future__ import annotations

import json
import re
import time

from config.logger import get_logger
from config.settings import USER_NAME

log = get_logger("planner")

ACTION_WORDS = (
    "open",
    "launch",
    "start",
    "search",
    "play",
    "watch",
    "message",
    "send",
    "call",
    "comment",
    "read",
    "find",
    "run",
    "download",
    "install",
    "visit",
    "navigate",
    "compose",
    "write",
    "set",
    "add",
    "check",
    "summarize",
    "learn",
    "execute",
    "workflow",
    "mission",
)

CONNECTOR_PATTERN = re.compile(
    r"\b(?:and then|then|after that|afterwards|next|finally|also|followed by)\b",
    re.IGNORECASE,
)


class AutonomousPlanner:
    """
    Turn long requests into executable tool steps.
    """

    def __init__(self, ai_client, brain):
        self.ai = ai_client
        self.brain = brain

    def plan_and_execute(self, task: str, gui_log=None) -> str:
        log.info(f"Autonomous task: {task}")
        previous_state = self.brain._planner_active
        self.brain._planner_active = True

        try:
            steps = self._make_plan(task)
            if not steps:
                return self.brain.process(task)

            if gui_log:
                gui_log(f"[PLAN] {len(steps)} step(s) for: {task}")

            results = []
            for index, step in enumerate(steps, 1):
                description = step.get("description") or step.get("params", {}).get("raw") or task
                log.info(f"Step {index}/{len(steps)}: {description}")
                if gui_log:
                    gui_log(f"[STEP {index}] {description}")

                try:
                    result = self._execute_step(step)
                    ok = not self._looks_like_error(result)
                    results.append(
                        {
                            "step": description,
                            "result": result,
                            "ok": ok,
                        }
                    )
                    if gui_log:
                        status = "OK" if ok else "WARN"
                        gui_log(f"[{status}] {result}")
                    time.sleep(0.25)

                except Exception as exc:
                    log.warning(f"Step failed: {exc}")
                    alternative = self._suggest_alternative(description, str(exc))
                    alt_step = self._normalize_step(alternative) if alternative else None

                    if alt_step and alt_step.get("description") != description:
                        try:
                            result = self._execute_step(alt_step)
                            ok = not self._looks_like_error(result)
                            results.append(
                                {
                                    "step": alt_step.get("description", description),
                                    "result": result,
                                    "ok": ok,
                                }
                            )
                            if gui_log:
                                gui_log(f"[RETRY] {result}")
                            continue
                        except Exception as retry_exc:
                            exc = retry_exc

                    results.append(
                        {
                            "step": description,
                            "result": str(exc),
                            "ok": False,
                        }
                    )
                    if gui_log:
                        gui_log(f"[FAILED] {exc}")

            return self._summarize_results(task, results)
        finally:
            self.brain._planner_active = previous_state

    def _execute_step(self, step: dict) -> str:
        description = step.get("description", "")
        params = step.get("params") or {}
        original = params.get("raw") or description
        intent = step.get("intent")

        if intent:
            return self.brain.execute_intent(intent, params, original)
        return self.brain.process(original)

    def _make_plan(self, task: str) -> list[dict]:
        for builder in (
            self._make_specialized_plan,
            self._make_connector_plan,
            self._make_ai_plan,
        ):
            plan = builder(task)
            if plan:
                return plan

        intent, params = self.brain.detect_intent(task)
        if intent:
            return [
                {
                    "description": task,
                    "intent": intent,
                    "params": params,
                }
            ]

        return [{"description": task, "params": {"raw": task}}]

    def _make_specialized_plan(self, task: str) -> list[dict]:
        low = task.lower()

        youtube_multi_action = (
            "youtube" in low
            and any(word in low for word in ("channel", "comment", "their video", "latest video", "newest video"))
        )
        if youtube_multi_action:
            params = self._extract_youtube_workflow(task)
            if params.get("channel") or params.get("video_query") or params.get("comment"):
                return [
                    {
                        "description": task,
                        "intent": "youtube_workflow",
                        "params": params,
                    }
                ]

        return []

    def _make_connector_plan(self, task: str) -> list[dict]:
        pieces = self._split_task(task)
        if len(pieces) < 2:
            return []

        steps = []
        for piece in pieces:
            normalized = self._normalize_step(piece)
            if normalized:
                steps.append(normalized)

        return steps if len(steps) >= 2 else []

    def _make_ai_plan(self, task: str) -> list[dict]:
        supported = ", ".join(self.brain.supported_intents())
        prompt = f"""Break this request into executable assistant steps.

User request: "{task}"

Return only valid JSON in this exact shape:
{{
  "steps": [
    {{
      "description": "short action description",
      "intent": "one supported intent",
      "params": {{"raw": "plain action text"}}
    }}
  ]
}}

Rules:
- Supported intents: {supported}
- Use "youtube_workflow" for multi-part YouTube tasks involving channel, video choice, or commenting
- Keep each step small and directly executable
- Max 6 steps
- No markdown
- If the request is already a single action, return one step
"""

        raw = self.ai.chat(prompt)
        payload = self._extract_json_object(raw)
        if not payload:
            return []

        try:
            data = json.loads(payload)
        except json.JSONDecodeError as exc:
            log.warning(f"AI plan parse failed: {exc}")
            return []

        raw_steps = data.get("steps", []) if isinstance(data, dict) else []
        steps = []
        for raw_step in raw_steps:
            normalized = self._normalize_step(raw_step)
            if normalized:
                steps.append(normalized)
        return steps

    def _normalize_step(self, step) -> dict | None:
        if isinstance(step, str):
            description = step.strip(" .")
            intent = None
            params = {"raw": description}
        elif isinstance(step, dict):
            description = str(
                step.get("description")
                or step.get("step")
                or step.get("text")
                or step.get("raw")
                or ""
            ).strip(" .")
            intent = str(step.get("intent") or "").strip()
            params = step.get("params") if isinstance(step.get("params"), dict) else {}
            if description and "raw" not in params:
                params["raw"] = description
        else:
            return None

        if not description and params.get("raw"):
            description = str(params["raw"]).strip(" .")

        if intent and intent not in self.brain.supported_intents():
            detected_intent, detected_params = self.brain.detect_intent(description)
            intent = detected_intent
            params = detected_params or params

        if not intent and description:
            detected_intent, detected_params = self.brain.detect_intent(description)
            if detected_intent:
                intent = detected_intent
                params = detected_params

        if not description:
            description = params.get("raw", "")
        if not description:
            return None

        params = params or {}
        params.setdefault("raw", description)
        return {
            "description": description,
            "intent": intent,
            "params": params,
        }

    def _split_task(self, task: str) -> list[str]:
        normalized = re.sub(
            r"\s*,\s*(?=(?:"
            + "|".join(ACTION_WORDS)
            + r")\b)",
            " then ",
            task,
            flags=re.IGNORECASE,
        )
        normalized = re.sub(
            r"\s+\band\b\s+(?=(?:"
            + "|".join(ACTION_WORDS)
            + r")\b)",
            " then ",
            normalized,
            flags=re.IGNORECASE,
        )

        parts = [part.strip(" ,.") for part in CONNECTOR_PATTERN.split(normalized) if part.strip(" ,.")]
        return parts

    def _extract_youtube_workflow(self, task: str) -> dict:
        params = {
            "raw": task,
            "channel": "",
            "video_query": "",
            "comment": "",
            "play_strategy": "latest",
        }

        handle_match = re.search(r"(@[A-Za-z0-9._-]+)", task)
        if handle_match:
            params["channel"] = handle_match.group(1)

        if not params["channel"]:
            patterns = [
                r"(?:channel(?: named| called)?|open(?: the)? channel(?: of)?|go to(?: the)? channel(?: of)?|from(?: the)? channel)\s+(.+?)(?=\s+(?:and|then|play|watch|comment|open|$))",
                r"([A-Za-z0-9 ._'-]+?)'?s channel",
            ]
            for pattern in patterns:
                match = re.search(pattern, task, re.IGNORECASE)
                if match:
                    params["channel"] = match.group(1).strip(" ,.")
                    break

        comment_match = re.search(
            r"\bcomment(?:\s+(?:saying|that|with))?\s+(.+)$",
            task,
            re.IGNORECASE,
        )
        if comment_match:
            params["comment"] = comment_match.group(1).strip(" .")

        explicit_latest_request = any(
            phrase in task.lower()
            for phrase in ("latest video", "newest video", "recent video", "their video")
        )
        if explicit_latest_request:
            params["play_strategy"] = "latest"

        has_named_video = bool(re.search(r"\b(?:called|titled)\b", task, re.IGNORECASE))
        if not explicit_latest_request or has_named_video:
            video_patterns = [
                r"(?:play|watch)\s+(?:their\s+)?(?:latest|newest|recent)?\s*video\s+(?:called|titled)\s+(.+?)(?=\s+(?:and|then|comment|$))",
                r"(?:play|watch)\s+(.+?)(?:\s+on youtube|\s+from\s+the\s+channel|\s+and\s+comment|$)",
            ]
            for pattern in video_patterns:
                match = re.search(pattern, task, re.IGNORECASE)
                if match:
                    candidate = match.group(1).strip(" .")
                    if candidate and candidate.lower() not in {"their video", "video"}:
                        params["video_query"] = candidate
                        break

        if params["video_query"].lower() == "their":
            params["video_query"] = ""

        return params

    def _extract_json_object(self, text: str) -> str:
        fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if fence_match:
            return fence_match.group(1)

        start = text.find("{")
        if start == -1:
            return ""

        depth = 0
        in_string = False
        escape = False
        for index in range(start, len(text)):
            char = text[index]
            if in_string:
                if escape:
                    escape = False
                elif char == "\\":
                    escape = True
                elif char == '"':
                    in_string = False
                continue

            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return text[start : index + 1]
        return ""

    def _looks_like_error(self, result: str) -> bool:
        low = (result or "").lower()
        return any(
            phrase in low
            for phrase in (
                "error executing",
                "couldn't",
                "could not",
                "failed",
                "not available",
                "what should i",
                "which ",
            )
        )

    def _suggest_alternative(self, failed_step: str, error: str) -> str:
        prompt = f"""A step in my task plan failed.
Failed step: "{failed_step}"
Error: "{error}"

Suggest one simpler fallback action.
Return only the fallback action text."""
        return self.ai.chat(prompt).strip().strip("\"'")

    def _summarize_results(self, task: str, results: list[dict]) -> str:
        ok = [result for result in results if result["ok"]]
        failed = [result for result in results if not result["ok"]]

        if not results:
            return f"No steps executed, {USER_NAME}."
        if len(results) == 1:
            return results[0]["result"]
        if not failed:
            key_results = " ".join(result["result"] for result in results[-2:] if result["result"])
            return key_results or (
                f"Task complete, {USER_NAME}. "
                f"Executed {len(ok)} step{'s' if len(ok) != 1 else ''} for: {task}"
            )

        failed_steps = ", ".join(result["step"] for result in failed[:3])
        return (
            f"Task partially complete, {USER_NAME}. "
            f"{len(ok)}/{len(results)} steps succeeded. "
            f"Failed steps: {failed_steps}"
        )

    def is_complex_task(self, text: str) -> bool:
        text_lower = text.lower()
        if "youtube" in text_lower and any(
            word in text_lower
            for word in ("channel", "comment", "their video", "latest video", "newest video")
        ):
            return True

        has_connector = bool(CONNECTOR_PATTERN.search(text))
        action_hits = sum(
            1
            for word in ACTION_WORDS
            if re.search(rf"\b{re.escape(word)}\b", text_lower)
        )
        is_long = len(text.split()) > 10

        return has_connector or action_hits >= 2 or (is_long and " and " in text_lower)
