"""
tools/system/computer_use.py
Advanced Computer Use module: Allows Jarvis to natively control the mouse, keyboard, and screen.
"""

from __future__ import annotations

import time
import os
from config.logger import get_logger

log = get_logger("computer_use")

class ComputerController:
    """Provides methods for keyboard and mouse control via PyAutoGUI."""

    def __init__(self):
        self.available = False
        try:
            import pyautogui
            pyautogui.FAILSAFE = True
            self.pyautogui = pyautogui
            self.available = True
            log.info("ComputerController initialized successfully.")
        except ImportError:
            log.warning("pyautogui not installed. Computer control disabled.")

    def type_text(self, text: str, interval: float = 0.02) -> str:
        """Types out the given string."""
        if not self.available:
            return "Error: pyautogui not installed."
        log.info(f"Typing text: {text}")
        self.pyautogui.write(text, interval=interval)
        return "Typed text successfully."

    def press_key(self, key: str) -> str:
        """Presses a specific key (e.g., 'enter', 'tab', 'ctrl', 'c')."""
        if not self.available:
            return "Error: pyautogui not installed."
        log.info(f"Pressing key: {key}")
        self.pyautogui.press(key)
        return f"Pressed {key}."

    def hotkey(self, *keys) -> str:
        """Presses a hotkey combination (e.g., 'ctrl', 'c')."""
        if not self.available:
            return "Error: pyautogui not installed."
        log.info(f"Pressing hotkey: {keys}")
        self.pyautogui.hotkey(*keys)
        return f"Pressed hotkey {keys}."

    def click(self, x: int = None, y: int = None, button: str = 'left') -> str:
        """Clicks the mouse at current location or specified coordinates."""
        if not self.available:
            return "Error: pyautogui not installed."
        log.info(f"Clicking at {x},{y} with {button} button.")
        if x is not None and y is not None:
            self.pyautogui.click(x=x, y=y, button=button)
            return f"Clicked {button} at ({x}, {y})."
        else:
            self.pyautogui.click(button=button)
            return f"Clicked {button} at current location."

    def move_to(self, x: int, y: int, duration: float = 0.5) -> str:
        """Moves mouse to absolute coordinates."""
        if not self.available:
            return "Error: pyautogui not installed."
        self.pyautogui.moveTo(x, y, duration=duration)
        return f"Moved mouse to ({x}, {y})."

    def screenshot(self, filepath: str = "screenshot.png") -> str:
        """Takes a screenshot of the entire screen."""
        if not self.available:
            return "Error: pyautogui not installed."
        log.info(f"Taking screenshot to {filepath}")
        self.pyautogui.screenshot(filepath)
        return f"Screenshot saved to {filepath}."

    def get_screen_size(self) -> str:
        """Returns the screen width and height."""
        if not self.available:
            return "Error: pyautogui not installed."
        w, h = self.pyautogui.size()
        return f"Screen resolution is {w}x{h}."
