"""
tools/web/playwright_agent.py
Advanced Browser Automation module using Playwright.
"""

from __future__ import annotations

import time
import os
from config.logger import get_logger

log = get_logger("playwright")

class PlaywrightController:
    """Provides methods for browser automation using Playwright."""

    def __init__(self):
        self.available = False
        try:
            from playwright.sync_api import sync_playwright
            self.sync_playwright = sync_playwright
            self.available = True
            log.info("PlaywrightController initialized successfully.")
        except ImportError:
            log.warning("playwright not installed. Browser automation disabled.")
        self.playwright = None
        self.browser = None
        self.page = None

    def start_browser(self, headless: bool = False) -> str:
        """Starts the playwright browser instance."""
        if not self.available:
            return "Error: Playwright not installed."
        if self.browser:
            return "Browser already running."
        try:
            self.playwright = self.sync_playwright().start()
            self.browser = self.playwright.chromium.launch(headless=headless)
            self.page = self.browser.new_page()
            log.info(f"Started Playwright browser (headless={headless}).")
            return "Started browser."
        except Exception as e:
            log.error(f"Failed to start browser: {e}")
            return f"Failed to start browser: {e}"

    def close_browser(self) -> str:
        """Closes the active browser instance."""
        if self.browser:
            self.browser.close()
            self.browser = None
        if self.playwright:
            self.playwright.stop()
            self.playwright = None
        return "Browser closed."

    def go_to(self, url: str) -> str:
        """Navigates to a specific URL."""
        if not self.page:
            self.start_browser()
        if not url.startswith("http"):
            url = "https://" + url
        try:
            self.page.goto(url)
            self.page.wait_for_load_state("networkidle")
            return f"Navigated to {self.page.url}. Page Title: {self.page.title()}"
        except Exception as e:
            return f"Failed to navigate to {url}: {e}"

    def click(self, selector: str) -> str:
        """Clicks an element by CSS or XPath selector."""
        if not self.page:
            return "Error: Browser not started."
        try:
            self.page.click(selector)
            self.page.wait_for_load_state("networkidle")
            return f"Clicked element matching '{selector}'."
        except Exception as e:
            return f"Failed to click '{selector}': {e}"

    def type_text(self, selector: str, text: str, press_enter: bool = False) -> str:
        """Types text into an input field."""
        if not self.page:
            return "Error: Browser not started."
        try:
            self.page.fill(selector, text)
            if press_enter:
                self.page.press(selector, "Enter")
                self.page.wait_for_load_state("networkidle")
            return f"Typed text into '{selector}'."
        except Exception as e:
            return f"Failed to type in '{selector}': {e}"

    def extract_text(self, selector: str = "body") -> str:
        """Extracts inner text from an element."""
        if not self.page:
            return "Error: Browser not started."
        try:
            text = self.page.locator(selector).inner_text()
            return f"Extracted text: {text[:2000]}..." # Truncate for safety
        except Exception as e:
            return f"Failed to extract text from '{selector}': {e}"
