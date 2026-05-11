"""
tools/vision/modules/screen_agent.py
GUI Automation via Vision AI — JarvisX Screen Agent.

Takes a screenshot, overlays a coordinate grid, sends to vision AI,
and executes the returned action (click, type, scroll, etc.).

Usage:
    agent = ScreenAgent(ai_client)
    result = agent.execute("click the Submit button")
"""
from __future__ import annotations
import re
import time
import logging
import threading
import tempfile
import os
from typing import Optional

log = logging.getLogger("screen_agent")

# Grid overlay density (cells across width)
_GRID_COLS = 20
_GRID_ROWS = 12


class ScreenAgent:
    """
    Automates GUI interactions by analyzing the screen with vision AI.
    Supports: click, double-click, right-click, type text, scroll, key press.
    """

    def __init__(self, ai_client):
        self.ai = ai_client
        self.available: bool = False
        self._init_backend()

    def _init_backend(self):
        try:
            import pyautogui  # noqa: F401
            import PIL.ImageGrab  # noqa: F401
            self.available = True
            log.info("ScreenAgent: pyautogui + PIL ready.")
        except ImportError:
            log.warning(
                "ScreenAgent: pyautogui or Pillow not installed. "
                "Run: pip install pyautogui Pillow"
            )

    def execute(self, instruction: str) -> str:
        """
        Main entry: interpret instruction, take screenshot, ask AI, execute action.
        Returns status message.
        """
        if not self.available:
            return "Screen automation not available (install pyautogui + Pillow)."
        try:
            # 1. Capture screen with grid
            screenshot_path = self._capture_with_grid()
            # 2. Ask AI what to do
            prompt = self._build_prompt(instruction)
            action_text = self.ai.chat_with_image(prompt, screenshot_path)
            log.info(f"[ScreenAgent] AI action: {action_text[:100]}")
            # 3. Parse and execute
            return self._parse_and_execute(action_text, instruction)
        except Exception as e:
            log.error(f"[ScreenAgent] Error: {e}")
            return f"Screen automation failed: {e}"

    def _capture_with_grid(self) -> str:
        """Take screenshot and draw coordinate grid on it."""
        import PIL.ImageGrab
        import PIL.ImageDraw
        import PIL.ImageFont

        screen = PIL.ImageGrab.grab()
        W, H = screen.size

        draw = PIL.ImageDraw.Draw(screen)
        cell_w = W / _GRID_COLS
        cell_h = H / _GRID_ROWS

        # Grid lines
        for c in range(_GRID_COLS + 1):
            x = int(c * cell_w)
            draw.line([(x, 0), (x, H)], fill=(80, 80, 80), width=1)
        for r in range(_GRID_ROWS + 1):
            y = int(r * cell_h)
            draw.line([(0, y), (W, y)], fill=(80, 80, 80), width=1)

        # Cell labels (col,row) at center of each cell
        try:
            font = PIL.ImageFont.truetype("arial.ttf", 10)
        except Exception:
            font = PIL.ImageFont.load_default()

        for r in range(_GRID_ROWS):
            for c in range(_GRID_COLS):
                cx = int((c + 0.5) * cell_w)
                cy = int((r + 0.5) * cell_h)
                draw.text((cx - 10, cy - 6), f"{c},{r}", fill=(0, 200, 255), font=font)

        # Save to temp file
        tmpfile = os.path.join(tempfile.gettempdir(), "jarvis_screen_agent.jpg")
        screen.save(tmpfile, "JPEG", quality=85)
        return tmpfile

    @staticmethod
    def _build_prompt(instruction: str) -> str:
        return (
            f"You are controlling a computer screen for a user.\n"
            f"The image shows the current screen with a coordinate grid overlay.\n"
            f"Grid format: column,row (0-indexed from top-left).\n"
            f"Cell size: screen_width/{_GRID_COLS} × screen_height/{_GRID_ROWS}.\n\n"
            f"Instruction: {instruction}\n\n"
            f"Respond with EXACTLY ONE of these action formats:\n"
            f"CLICK col,row\n"
            f"DOUBLE_CLICK col,row\n"
            f"RIGHT_CLICK col,row\n"
            f"TYPE text_to_type\n"
            f"SCROLL_DOWN amount\n"
            f"SCROLL_UP amount\n"
            f"KEY key_name\n"
            f"DONE message\n\n"
            f"Be precise. Use the grid coordinates to identify the exact element."
        )

    def _parse_and_execute(self, action_text: str, original_instruction: str) -> str:
        """Parse AI response and execute the action."""
        import pyautogui
        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.1

        import PIL.ImageGrab
        W, H = PIL.ImageGrab.grab().size
        cell_w = W / _GRID_COLS
        cell_h = H / _GRID_ROWS

        lines = action_text.strip().split("\n")
        executed = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # CLICK / DOUBLE_CLICK / RIGHT_CLICK col,row
            m = re.match(r"(CLICK|DOUBLE_CLICK|RIGHT_CLICK)\s+(\d+),(\d+)", line, re.IGNORECASE)
            if m:
                action_type, col_s, row_s = m.group(1).upper(), m.group(2), m.group(3)
                col, row = int(col_s), int(row_s)
                px = int((col + 0.5) * cell_w)
                py = int((row + 0.5) * cell_h)
                pyautogui.moveTo(px, py, duration=0.3)
                time.sleep(0.1)
                if action_type == "CLICK":
                    pyautogui.click(px, py)
                elif action_type == "DOUBLE_CLICK":
                    pyautogui.doubleClick(px, py)
                elif action_type == "RIGHT_CLICK":
                    pyautogui.rightClick(px, py)
                executed.append(f"{action_type} at ({px},{py})")
                time.sleep(0.3)
                continue

            # TYPE text
            m = re.match(r"TYPE\s+(.+)", line, re.IGNORECASE)
            if m:
                text = m.group(1).strip()
                pyautogui.typewrite(text, interval=0.04)
                executed.append(f"Typed: {text[:30]}")
                time.sleep(0.2)
                continue

            # SCROLL
            m = re.match(r"SCROLL_(DOWN|UP)\s+(\d+)", line, re.IGNORECASE)
            if m:
                direction = m.group(1).upper()
                amount = int(m.group(2))
                pyautogui.scroll(-amount if direction == "DOWN" else amount)
                executed.append(f"Scroll {direction} {amount}")
                continue

            # KEY
            m = re.match(r"KEY\s+(.+)", line, re.IGNORECASE)
            if m:
                key = m.group(1).strip()
                pyautogui.press(key)
                executed.append(f"Key: {key}")
                continue

            # DONE
            m = re.match(r"DONE\s*(.*)", line, re.IGNORECASE)
            if m:
                msg = m.group(1).strip()
                return msg or "Screen action complete."

        if executed:
            return "Executed: " + "; ".join(executed)
        return "Screen agent couldn't parse action. Please rephrase."
