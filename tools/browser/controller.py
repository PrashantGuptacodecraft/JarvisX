"""Browser automation with smarter YouTube workflows."""

from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
import webbrowser
from difflib import SequenceMatcher

from config.logger import get_logger
from config.settings import USER_NAME

log = get_logger("browser")

SITES = {
    "gmail": "https://mail.google.com",
    "github": "https://github.com",
    "chatgpt": "https://chat.openai.com",
    "linkedin": "https://linkedin.com",
    "youtube": "https://youtube.com",
    "google": "https://google.com",
    "netflix": "https://netflix.com",
    "twitter": "https://twitter.com",
    "instagram": "https://instagram.com",
    "reddit": "https://reddit.com",
    "wikipedia": "https://wikipedia.org",
    "whatsapp": "https://web.whatsapp.com",
    "stackoverflow": "https://stackoverflow.com",
    "claude": "https://claude.ai",
    "gemini": "https://gemini.google.com",
    "bard": "https://gemini.google.com",
    "maps": "https://maps.google.com",
    "drive": "https://drive.google.com",
    "meet": "https://meet.google.com",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}

YOUTUBE_CHANNEL_FILTER = "EgIQAg%253D%253D"
SEARCH_URLS = {
    "google": "https://www.google.com/search?q={query}",
    "youtube": "https://www.youtube.com/results?search_query={query}",
    "github": "https://github.com/search?q={query}",
    "reddit": "https://www.reddit.com/search/?q={query}",
    "wikipedia": "https://en.wikipedia.org/w/index.php?search={query}",
    "stackoverflow": "https://stackoverflow.com/search?q={query}",
    "maps": "https://www.google.com/maps/search/{query}",
    "amazon": "https://www.amazon.in/s?k={query}",
    "linkedin": "https://www.linkedin.com/search/results/all/?keywords={query}",
}
SEARCH_SITE_ALIASES = {
    "stack overflow": "stackoverflow",
    "wiki": "wikipedia",
    "google maps": "maps",
}


class BrowserController:
    def search_google(self, query: str) -> str:
        if not query:
            return f"What should I search, {USER_NAME}?"
        webbrowser.open(
            "https://www.google.com/search?q=" + urllib.parse.quote(query)
        )
        return f"Searching Google for '{query}'."

    def search_youtube(self, query: str) -> str:
        if not query:
            return f"What should I search on YouTube, {USER_NAME}?"
        webbrowser.open(
            "https://www.youtube.com/results?search_query="
            + urllib.parse.quote(query)
        )
        return f"Searching YouTube for '{query}', {USER_NAME}."

    def search_website(self, site: str, query: str) -> str:
        site_key = self._normalize_site(site)
        if not site_key:
            return f"Which website should I search, {USER_NAME}?"
        if not query:
            return f"What should I search on {site_key}, {USER_NAME}?"

        template = SEARCH_URLS.get(site_key)
        if template:
            webbrowser.open(template.format(query=urllib.parse.quote(query)))
            return f"Searching {site_key.capitalize()} for '{query}', {USER_NAME}."

        if site_key in SITES:
            domain = urllib.parse.urlparse(SITES[site_key]).netloc.replace("www.", "")
            return self.search_google(f"site:{domain} {query}")

        return self.search_google(f"{site} {query}")

    def play_youtube(self, query: str, channel: str = "") -> str:
        if not query and not channel:
            return f"What should I play, {USER_NAME}?"

        video = self._resolve_youtube_video(query=query, channel_name=channel)
        if video:
            webbrowser.open(video["url"])
            suffix = f" from {video['channel']}" if video.get("channel") else ""
            return (
                f"Playing '{video['title']}'{suffix} on YouTube, {USER_NAME}."
            )

        search_query = " ".join(part for part in [channel, query] if part).strip()
        return self.search_youtube(search_query)

    def open_youtube_channel(self, channel: str) -> str:
        if not channel:
            return f"Which YouTube channel should I open, {USER_NAME}?"

        match = self._resolve_youtube_channel(channel)
        if match:
            webbrowser.open(match["url"])
            return f"Opening the YouTube channel '{match['title']}', {USER_NAME}."

        url = (
            "https://www.youtube.com/results?search_query="
            + urllib.parse.quote(channel)
            + "&sp="
            + YOUTUBE_CHANNEL_FILTER
        )
        webbrowser.open(url)
        return (
            f"I opened YouTube channel search results for '{channel}', {USER_NAME}."
        )

    def play_from_youtube_channel(
        self,
        channel: str,
        video_query: str = "",
        prefer_latest: bool = True,
    ) -> str:
        if not channel:
            return f"Tell me which channel to use, {USER_NAME}."

        channel_match = self._resolve_youtube_channel(channel)
        if channel_match:
            webbrowser.open(channel_match["url"])
            time.sleep(1.0)
            video = self._resolve_youtube_video(
                query=video_query,
                channel_name=channel_match["title"],
                channel_url=channel_match["url"],
                prefer_latest=prefer_latest,
            )
            if video:
                webbrowser.open(video["url"])
                return (
                    f"Opening {channel_match['title']} and playing "
                    f"'{video['title']}', {USER_NAME}."
                )

            webbrowser.open(channel_match["url"].rstrip("/") + "/videos")
            if video_query:
                return (
                    f"I opened {channel_match['title']} and its videos tab, "
                    f"but I could not pin down '{video_query}' exactly, {USER_NAME}."
                )
            return (
                f"I opened {channel_match['title']} and its latest videos, {USER_NAME}."
            )

        search_query = " ".join(part for part in [channel, video_query] if part).strip()
        return self.search_youtube(search_query)

    def comment_on_youtube(self, text: str, wait_for_page: float = 4.0) -> str:
        if not text:
            return f"What should I comment, {USER_NAME}?"

        try:
            import pyautogui
            import pyperclip
        except ImportError:
            return (
                f"I opened the video, but automatic commenting needs "
                f"pyautogui and pyperclip installed, {USER_NAME}."
            )

        try:
            pyautogui.FAILSAFE = True
            pyautogui.PAUSE = 0.25
            time.sleep(max(wait_for_page, 0))
            self._focus_browser_window()
            pyautogui.press("pagedown", presses=4, interval=0.45)

            target = self._locate_screen_text(
                ["add a comment", "comment as", "write a comment", "comments"],
                timeout=6,
            )

            if target:
                click_y = target["y"]
                if target["phrase"] == "comments":
                    click_y += 45
                pyautogui.click(target["x"], click_y)
            else:
                width, height = pyautogui.size()
                pyautogui.click(width // 2, int(height * 0.78))

            time.sleep(0.8)
            pyperclip.copy(text)
            pyautogui.hotkey("ctrl", "v")
            time.sleep(0.6)

            button = self._locate_screen_text(
                ["comment", "submit"],
                timeout=4,
                prefer_bottom=True,
            )
            if button:
                pyautogui.click(button["x"], button["y"])
                return f"Comment posted on YouTube, {USER_NAME}."

            pyautogui.press("tab", presses=2, interval=0.25)
            pyautogui.press("enter")
            return f"Comment entered on YouTube, {USER_NAME}."

        except Exception as exc:
            log.warning(f"YouTube comment automation failed: {exc}")
            try:
                pyperclip.copy(text)
                return (
                    f"I opened the video and copied your comment to the clipboard "
                    f"because auto-commenting hit an issue: {exc}"
                )
            except Exception:
                return f"I could not post the YouTube comment automatically: {exc}"

    def youtube_workflow(
        self,
        channel: str = "",
        video_query: str = "",
        comment: str = "",
        play_strategy: str = "latest",
        raw_command: str = "",
    ) -> str:
        actions = []
        prefer_latest = play_strategy in {"latest", "newest", "recent", "first"}

        channel_match = None
        if channel:
            channel_match = self._resolve_youtube_channel(channel)
            if channel_match:
                webbrowser.open(channel_match["url"])
                actions.append(f"Opened channel '{channel_match['title']}'.")
            else:
                url = (
                    "https://www.youtube.com/results?search_query="
                    + urllib.parse.quote(channel)
                    + "&sp="
                    + YOUTUBE_CHANNEL_FILTER
                )
                webbrowser.open(url)
                actions.append(f"Opened channel results for '{channel}'.")

        video_query = video_query.strip()
        lookup_query = video_query or raw_command
        video = self._resolve_youtube_video(
            query=lookup_query,
            channel_name=(channel_match or {}).get("title", channel),
            channel_url=(channel_match or {}).get("url", ""),
            prefer_latest=prefer_latest,
        )
        if video:
            time.sleep(1.0)
            webbrowser.open(video["url"])
            actions.append(f"Playing '{video['title']}'.")
        elif not channel and lookup_query:
            self.search_youtube(lookup_query)
            actions.append(f"Opened YouTube search for '{lookup_query}'.")
        elif channel_match:
            webbrowser.open(channel_match["url"].rstrip("/") + "/videos")
            actions.append("Opened the channel videos tab.")

        if comment:
            actions.append(self.comment_on_youtube(comment))

        if not actions:
            return self.open_url("youtube")
        return " ".join(actions)

    def open_url(self, url_or_name: str) -> str:
        key = url_or_name.lower().strip()
        if key in SITES:
            webbrowser.open(SITES[key])
            return f"Opening {key.capitalize()}, {USER_NAME}."
        if not url_or_name.startswith("http"):
            url_or_name = "https://" + url_or_name
        webbrowser.open(url_or_name)
        return f"Opening {url_or_name}, {USER_NAME}."

    def compose_gmail(self, to: str = "", subject: str = "", body: str = "") -> str:
        params = {}
        if to:
            params["to"] = to
        if subject:
            params["su"] = subject
        if body:
            params["body"] = body
        params["view"] = "cm"
        params["fs"] = "1"

        url = "https://mail.google.com/mail/?" + urllib.parse.urlencode(params)
        webbrowser.open(url)

        parts = []
        if to:
            parts.append(f"to {to}")
        if subject:
            parts.append(f"subject '{subject}'")
        if body:
            parts.append("body prefilled")

        detail = ", ".join(parts) if parts else "blank compose"
        log.info(f"Gmail compose opened: {detail}")
        return f"Gmail compose opened - {detail}, {USER_NAME}."

    def send_gmail(
        self,
        to: str = "",
        subject: str = "",
        body: str = "",
        wait_for_page: float = 8.0,
    ) -> str:
        if not to:
            return f"Who should I email, {USER_NAME}?"
        if not body and not subject:
            return f"What should I send in the email, {USER_NAME}?"

        try:
            import pyautogui  # noqa: F401
        except ImportError:
            return self.compose_gmail(to=to, subject=subject, body=body)

        self.compose_gmail(to=to, subject=subject, body=body)
        time.sleep(max(wait_for_page, 0))
        self._focus_browser_window()

        try:
            button = self._locate_screen_text(
                ["send", "send message"],
                timeout=8,
                prefer_bottom=True,
            )
            if button:
                import pyautogui

                pyautogui.FAILSAFE = True
                pyautogui.PAUSE = 0.2
                pyautogui.click(button["x"], button["y"])
                log.info(f"Gmail message sent to {to}")
                return f"Email sent to {to}, {USER_NAME}."
        except Exception as exc:
            log.warning(f"Gmail send automation failed: {exc}")

        try:
            import pyautogui

            pyautogui.FAILSAFE = True
            pyautogui.PAUSE = 0.2
            # Gmail's official shortcut is Ctrl+Enter. First move focus to the latest compose box.
            pyautogui.press("esc")
            time.sleep(0.5)
            pyautogui.hotkey("ctrl", ".")
            time.sleep(0.5)
            pyautogui.hotkey("ctrl", "enter")
            time.sleep(0.6)
            pyautogui.press("enter")
            log.info(f"Gmail keyboard send fallback triggered for {to}")
            return f"Email send shortcut triggered for {to}, {USER_NAME}."
        except Exception as exc:
            log.warning(f"Gmail keyboard fallback failed: {exc}")

        return (
            f"Gmail draft opened and prefilled for {to}, {USER_NAME}. "
            f"I couldn't confirm the Send button automatically, so please check the compose window."
        )

    def open_gmail(self) -> str:
        webbrowser.open(SITES["gmail"])
        return f"Opening Gmail, {USER_NAME}."

    def _normalize_site(self, site: str) -> str:
        site_key = (site or "").lower().strip()
        return SEARCH_SITE_ALIASES.get(site_key, site_key)

    def _resolve_youtube_channel(self, channel_name: str) -> dict | None:
        channel_name = channel_name.strip()
        if not channel_name:
            return None

        if channel_name.startswith("@"):
            return {
                "title": channel_name,
                "url": f"https://www.youtube.com/{channel_name}",
            }

        search_url = (
            "https://www.youtube.com/results?search_query="
            + urllib.parse.quote(channel_name)
            + "&sp="
            + YOUTUBE_CHANNEL_FILTER
        )
        data = self._fetch_youtube_initial_data(search_url)
        if not data:
            return None

        candidates = self._extract_channel_candidates(data)
        if not candidates:
            return None

        best = max(
            candidates,
            key=lambda item: self._score_text_match(channel_name, item.get("title", "")),
        )
        if self._score_text_match(channel_name, best.get("title", "")) < 0.35:
            return None
        return best

    def _resolve_youtube_video(
        self,
        query: str = "",
        channel_name: str = "",
        channel_url: str = "",
        prefer_latest: bool = False,
    ) -> dict | None:
        query = query.strip()
        channel_name = channel_name.strip()

        if channel_url:
            videos_url = channel_url.rstrip("/") + "/videos"
            data = self._fetch_youtube_initial_data(videos_url)
            candidates = self._extract_video_candidates(data) if data else []
            if candidates:
                if not query or prefer_latest:
                    return candidates[0]
                best = max(
                    candidates,
                    key=lambda item: self._score_text_match(query, item.get("title", "")),
                )
                if self._score_text_match(query, best.get("title", "")) >= 0.35:
                    return best

        search_terms = " ".join(part for part in [channel_name, query] if part).strip()
        if not search_terms:
            return None

        search_url = (
            "https://www.youtube.com/results?search_query="
            + urllib.parse.quote(search_terms)
        )
        data = self._fetch_youtube_initial_data(search_url)
        candidates = self._extract_video_candidates(data) if data else []
        if not candidates:
            return None

        def score(item: dict) -> float:
            title_score = self._score_text_match(query or search_terms, item.get("title", ""))
            channel_score = (
                self._score_text_match(channel_name, item.get("channel", ""))
                if channel_name
                else 0.0
            )
            freshness = 0.05 if prefer_latest else 0.0
            return title_score + (channel_score * 0.8) + freshness

        best = max(candidates, key=score)
        if score(best) < 0.30:
            return None
        return best

    def _extract_channel_candidates(self, data: dict) -> list[dict]:
        matches = []
        seen = set()

        for node in self._walk(data):
            renderer = node.get("channelRenderer")
            if not renderer:
                continue

            title = self._extract_text(renderer.get("title"))
            endpoint = renderer.get("navigationEndpoint", {})
            browse = endpoint.get("browseEndpoint", {})
            canonical = browse.get("canonicalBaseUrl", "")
            channel_id = renderer.get("channelId") or browse.get("browseId", "")

            if canonical:
                url = self._coerce_youtube_url(canonical)
            elif channel_id:
                url = f"https://www.youtube.com/channel/{channel_id}"
            else:
                continue

            if url in seen:
                continue
            seen.add(url)
            matches.append({"title": title or channel_id, "url": url})

        return matches

    def _extract_video_candidates(self, data: dict | None) -> list[dict]:
        if not data:
            return []

        matches = []
        seen = set()

        for node in self._walk(data):
            renderer = node.get("videoRenderer") or node.get("gridVideoRenderer")
            if not renderer:
                continue

            video_id = renderer.get("videoId")
            if not video_id:
                continue
            url = f"https://www.youtube.com/watch?v={video_id}"
            if url in seen:
                continue

            seen.add(url)
            matches.append(
                {
                    "title": self._extract_text(renderer.get("title")) or video_id,
                    "channel": self._extract_text(
                        renderer.get("ownerText")
                        or renderer.get("shortBylineText")
                        or renderer.get("longBylineText")
                    ),
                    "published": self._extract_text(renderer.get("publishedTimeText")),
                    "url": url,
                }
            )

        return matches

    def _fetch_youtube_initial_data(self, url: str) -> dict | None:
        html = self._http_get_text(url)
        if not html:
            return None

        for marker in (
            "var ytInitialData = ",
            'window["ytInitialData"] = ',
            "ytInitialData = ",
        ):
            blob = self._extract_balanced_json(html, marker)
            if not blob:
                continue
            try:
                return json.loads(blob)
            except json.JSONDecodeError as exc:
                log.warning(f"Could not parse YouTube data from {url}: {exc}")
        return None

    def _http_get_text(self, url: str) -> str:
        try:
            import requests

            resp = requests.get(url, headers=HEADERS, timeout=10)
            resp.raise_for_status()
            return resp.text
        except ImportError:
            pass
        except Exception as exc:
            log.warning(f"Requests fetch failed for {url}: {exc}")

        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.read().decode("utf-8", errors="ignore")
        except Exception as exc:
            log.warning(f"Stdlib fetch failed for {url}: {exc}")
            return ""

    def _extract_balanced_json(self, text: str, marker: str) -> str:
        start = text.find(marker)
        if start == -1:
            return ""

        brace_start = text.find("{", start + len(marker))
        if brace_start == -1:
            return ""

        depth = 0
        in_string = False
        escape = False

        for idx in range(brace_start, len(text)):
            ch = text[idx]
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
                continue

            if ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[brace_start : idx + 1]

        return ""

    def _walk(self, node):
        if isinstance(node, dict):
            yield node
            for value in node.values():
                yield from self._walk(value)
        elif isinstance(node, list):
            for item in node:
                yield from self._walk(item)

    def _extract_text(self, value) -> str:
        if not value:
            return ""
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, dict):
            if value.get("simpleText"):
                return str(value["simpleText"]).strip()
            if value.get("runs"):
                parts = [
                    str(run.get("text", "")).strip()
                    for run in value["runs"]
                    if isinstance(run, dict) and run.get("text")
                ]
                return " ".join(part for part in parts if part).strip()
        if isinstance(value, list):
            parts = [self._extract_text(item) for item in value]
            return " ".join(part for part in parts if part).strip()
        return ""

    def _score_text_match(self, query: str, candidate: str) -> float:
        query = re.sub(r"\s+", " ", query.lower()).strip()
        candidate = re.sub(r"\s+", " ", candidate.lower()).strip()
        if not query or not candidate:
            return 0.0
        if query == candidate:
            return 1.0
        if query in candidate:
            return 0.92

        query_tokens = set(re.findall(r"[a-z0-9@._'-]+", query))
        candidate_tokens = set(re.findall(r"[a-z0-9@._'-]+", candidate))
        overlap = len(query_tokens & candidate_tokens) / max(len(query_tokens), 1)
        ratio = SequenceMatcher(None, query, candidate).ratio()
        return max(ratio, overlap * 0.95)

    def _coerce_youtube_url(self, path_or_url: str) -> str:
        if not path_or_url:
            return ""
        if path_or_url.startswith("http"):
            return path_or_url
        if not path_or_url.startswith("/"):
            path_or_url = "/" + path_or_url
        return "https://www.youtube.com" + path_or_url

    def _focus_browser_window(self) -> bool:
        try:
            import pygetwindow as gw
        except Exception:
            return False

        titles = [
            "Gmail",
            "Mail",
            "YouTube",
            "Chrome",
            "Edge",
            "Firefox",
            "Brave",
        ]
        for title in titles:
            windows = gw.getWindowsWithTitle(title)
            if not windows:
                continue
            try:
                windows[0].activate()
                time.sleep(0.6)
                return True
            except Exception:
                continue
        return False

    def _locate_screen_text(
        self,
        phrases: list[str],
        timeout: float = 4.0,
        prefer_bottom: bool = False,
    ) -> dict | None:
        try:
            import pyautogui
            import pytesseract
            from pytesseract import Output
        except Exception:
            return None

        wanted = [
            re.sub(r"\s+", " ", phrase.lower()).strip()
            for phrase in phrases
            if phrase and phrase.strip()
        ]
        if not wanted:
            return None

        deadline = time.time() + max(timeout, 0)
        best_match = None

        while time.time() <= deadline:
            image = pyautogui.screenshot()
            data = pytesseract.image_to_data(image, output_type=Output.DICT)
            words = []
            count = len(data.get("text", []))

            for idx in range(count):
                raw = (data["text"][idx] or "").strip()
                if not raw:
                    continue
                words.append(
                    {
                        "text": re.sub(r"\s+", " ", raw.lower()).strip(),
                        "x": int(data["left"][idx]),
                        "y": int(data["top"][idx]),
                        "w": int(data["width"][idx]),
                        "h": int(data["height"][idx]),
                    }
                )

            best_match = self._match_ocr_phrase(words, wanted, prefer_bottom)
            if best_match:
                return best_match
            time.sleep(0.5)

        return None

    def _match_ocr_phrase(
        self,
        words: list[dict],
        phrases: list[str],
        prefer_bottom: bool,
    ) -> dict | None:
        matches = []

        for phrase in phrases:
            tokens = phrase.split()
            if not tokens:
                continue

            for idx in range(len(words) - len(tokens) + 1):
                window = words[idx : idx + len(tokens)]
                if [item["text"] for item in window] != tokens:
                    continue

                x1 = min(item["x"] for item in window)
                y1 = min(item["y"] for item in window)
                x2 = max(item["x"] + item["w"] for item in window)
                y2 = max(item["y"] + item["h"] for item in window)
                matches.append(
                    {
                        "phrase": phrase,
                        "x": int((x1 + x2) / 2),
                        "y": int((y1 + y2) / 2),
                        "top": y1,
                        "bottom": y2,
                    }
                )

        if not matches:
            return None

        if prefer_bottom:
            return max(matches, key=lambda item: item["bottom"])
        return min(matches, key=lambda item: item["top"])
