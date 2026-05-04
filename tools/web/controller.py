"""
tools/web/controller.py
Web intelligence plus practical download workflows.
"""

from __future__ import annotations

import mimetypes
import os
import re
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

from config.logger import get_logger
from config.settings import USER_NAME

log = get_logger("web")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

DIRECT_DOWNLOAD_EXTENSIONS = (
    ".zip", ".rar", ".7z", ".tar", ".gz",
    ".exe", ".msi", ".apk", ".dmg", ".pkg",
    ".pdf", ".csv", ".json", ".xml", ".txt",
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg",
    ".mp3", ".wav", ".mp4", ".mkv",
    ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx",
)

DOWNLOAD_FOLDERS = {
    "downloads": Path.home() / "Downloads",
    "desktop": Path.home() / "Desktop",
    "documents": Path.home() / "Documents",
    "pictures": Path.home() / "Pictures",
    "music": Path.home() / "Music",
    "videos": Path.home() / "Videos",
}


class WebController:
    def fetch_page(self, url: str) -> str:
        url = url.strip()
        if not url:
            return ""
        if not url.startswith("http"):
            url = "https://" + url

        log.info(f"Fetching: {url}")
        try:
            html = self._http_get_text(url)
            return self._html_to_text(html)
        except Exception as exc:
            log.error(f"Fetch error: {exc}")
            return f"Couldn't fetch page: {exc}"

    def search(self, query: str) -> str:
        if not query:
            return f"What should I search for, {USER_NAME}?"

        log.info(f"Web search: {query}")

        try:
            import requests

            encoded = urllib.parse.quote(query)
            url = f"https://api.duckduckgo.com/?q={encoded}&format=json&no_redirect=1&no_html=1"
            resp = requests.get(url, headers=HEADERS, timeout=8)
            data = resp.json()

            results = []
            if data.get("AbstractText"):
                results.append(data["AbstractText"])
            if data.get("Answer"):
                results.append(f"Answer: {data['Answer']}")
            for item in data.get("RelatedTopics", [])[:3]:
                if isinstance(item, dict) and item.get("Text"):
                    results.append(item["Text"])

            if results:
                return f"Web search results for '{query}':\n" + "\n\n".join(results[:3])

        except Exception as exc:
            log.warning(f"DDG API failed: {exc}")

        results = self.search_results(query, limit=3)
        if results:
            lines = [f"- {item['title']} -> {item['url']}" for item in results]
            return f"Top web matches for '{query}':\n" + "\n".join(lines)

        webbrowser.open("https://duckduckgo.com/?q=" + urllib.parse.quote(query))
        return f"Opened DuckDuckGo search for '{query}', {USER_NAME}."

    def search_results(self, query: str, limit: int = 5) -> list[dict]:
        if not query:
            return []

        encoded = urllib.parse.quote(query)
        url = f"https://duckduckgo.com/html/?q={encoded}"

        try:
            html = self._http_get_text(url)
        except Exception as exc:
            log.warning(f"Search results fetch failed: {exc}")
            return []

        try:
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(html, "html.parser")
            results = []
            for link in soup.select("a.result__a, a[data-testid='result-title-a']"):
                href = link.get("href", "").strip()
                title = link.get_text(" ", strip=True)
                resolved = self._resolve_duckduckgo_link(href)
                if title and resolved:
                    results.append({"title": title, "url": resolved})
                if len(results) >= limit:
                    break
            return results
        except Exception:
            results = []
            for match in re.finditer(
                r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
                html,
                re.IGNORECASE | re.DOTALL,
            ):
                href = self._resolve_duckduckgo_link(match.group(1))
                title = re.sub(r"<[^>]+>", "", match.group(2)).strip()
                if href and title:
                    results.append({"title": title, "url": href})
                if len(results) >= limit:
                    break
            return results

    def download_file(self, url: str, filename: str = "", folder: str = "downloads") -> str:
        if not url:
            return f"Which file URL should I download, {USER_NAME}?"
        if not url.startswith("http"):
            url = "https://" + url

        destination_dir = self._resolve_folder(folder)
        destination_dir.mkdir(parents=True, exist_ok=True)

        try:
            response = self._http_get_response(url)
            final_url = response["url"]
            content_type = response["headers"].get("content-type", "")
            content_disposition = response["headers"].get("content-disposition", "")

            chosen_name = (
                self._filename_from_content_disposition(content_disposition)
                or filename.strip()
                or Path(urllib.parse.urlparse(final_url).path).name
                or "downloaded_file"
            )
            chosen_name = self._sanitize_filename(chosen_name)
            if "." not in Path(chosen_name).name:
                guessed_ext = mimetypes.guess_extension(content_type.split(";")[0].strip()) or ""
                if guessed_ext:
                    chosen_name += guessed_ext

            target = self._ensure_unique_path(destination_dir / chosen_name)

            with open(target, "wb") as handle:
                handle.write(response["content"])

            return f"Downloaded file to {target}, {USER_NAME}."
        except Exception as exc:
            log.error(f"Download failed for {url}: {exc}")
            return f"Couldn't download that file, {USER_NAME}: {exc}"

    def download_from_query(self, query: str, filename: str = "", folder: str = "downloads") -> str:
        query = (query or "").strip()
        if not query:
            return f"What should I download, {USER_NAME}?"

        url_match = re.search(r'https?://[^\s)>\]"]+', query)
        if url_match:
            return self.download_file(url_match.group(0), filename=filename, folder=folder)

        search_query = query if "download" in query.lower() else f"{query} download"
        results = self.search_results(search_query, limit=8)
        candidate = self._pick_download_candidate(results, query)

        if candidate and self._is_direct_download_url(candidate["url"]):
            return self.download_file(candidate["url"], filename=filename or candidate["title"], folder=folder)

        if candidate:
            webbrowser.open(candidate["url"])
            return (
                f"I found a likely download page for '{query}' and opened it: "
                f"{candidate['title']}, {USER_NAME}."
            )

        webbrowser.open("https://duckduckgo.com/?q=" + urllib.parse.quote(search_query))
        return (
            f"I couldn't find a direct file link for '{query}', so I opened search results "
            f"to help you finish it quickly, {USER_NAME}."
        )

    def summarize_with_ai(self, content: str, ai_client) -> str:
        url_match = re.search(r'https?://[^\s]+', content)
        if url_match:
            url = url_match.group()
            page_text = self.fetch_page(url)
            if page_text:
                summary = ai_client.summarize(page_text)
                return f"Summary of {url}:\n{summary}"
            return f"Couldn't fetch that page, {USER_NAME}."
        return ai_client.chat(content)

    def get_weather(self, city: str = "") -> str:
        try:
            import requests

            location = urllib.parse.quote(city) if city else ""
            url = f"https://wttr.in/{location}?format=3"
            resp = requests.get(url, headers=HEADERS, timeout=8)
            return resp.text.strip()
        except Exception as exc:
            return f"Couldn't get weather: {exc}"

    def get_news_headlines(self, topic: str = "technology") -> str:
        try:
            import requests

            feeds = {
                "technology": "https://feeds.feedburner.com/TechCrunch",
                "world": "https://feeds.bbci.co.uk/news/world/rss.xml",
                "india": "https://feeds.bbci.co.uk/news/world/south_asia/rss.xml",
            }
            url = feeds.get(topic.lower(), feeds["technology"])
            resp = requests.get(url, headers=HEADERS, timeout=8)
            titles = re.findall(r"<title><!\[CDATA\[(.*?)\]\]></title>", resp.text)
            if not titles:
                titles = re.findall(r"<title>(.*?)</title>", resp.text)
            titles = [title for title in titles if len(title) > 10][:5]
            if titles:
                return f"Top {topic} headlines:\n" + "\n".join(f"- {title}" for title in titles)
            return "Couldn't fetch headlines."
        except Exception as exc:
            return f"News fetch failed: {exc}"

    def _fetch_stdlib(self, url: str) -> str:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
        return self._html_to_text(html)

    def _html_to_text(self, html: str) -> str:
        try:
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(html, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form", "noscript"]):
                tag.decompose()
            text = soup.get_text(separator="\n", strip=True)
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            return "\n".join(lines)[:5000]
        except ImportError:
            text = re.sub(r"<script.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<style.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<[^>]+>", "", text)
            text = re.sub(r"\s{3,}", "\n\n", text)
            return text.strip()[:5000]

    def _http_get_text(self, url: str) -> str:
        try:
            import requests

            resp = requests.get(url, headers=HEADERS, timeout=10)
            resp.raise_for_status()
            return resp.text
        except ImportError:
            return self._fetch_stdlib(url)
        except Exception:
            return self._fetch_stdlib(url)

    def _http_get_response(self, url: str) -> dict:
        try:
            import requests

            resp = requests.get(url, headers=HEADERS, timeout=30, allow_redirects=True)
            resp.raise_for_status()
            return {
                "url": resp.url,
                "headers": {k.lower(): v for k, v in resp.headers.items()},
                "content": resp.content,
            }
        except ImportError:
            pass

        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=30) as resp:
            content = resp.read()
            headers = {k.lower(): v for k, v in dict(resp.info()).items()}
            return {
                "url": resp.geturl(),
                "headers": headers,
                "content": content,
            }

    def _resolve_duckduckgo_link(self, href: str) -> str:
        href = (href or "").strip()
        if not href:
            return ""
        if href.startswith("//"):
            href = "https:" + href
        if "duckduckgo.com/l/?" in href:
            parsed = urllib.parse.urlparse(href)
            target = urllib.parse.parse_qs(parsed.query).get("uddg", [""])[0]
            return urllib.parse.unquote(target) if target else href
        return href

    def _pick_download_candidate(self, results: list[dict], query: str) -> dict | None:
        if not results:
            return None

        query_tokens = set(re.findall(r"[a-z0-9]+", query.lower()))
        blacklist = ("youtube.com", "facebook.com", "instagram.com")

        def score(result: dict) -> float:
            title = result["title"].lower()
            url = result["url"].lower()
            title_tokens = set(re.findall(r"[a-z0-9]+", title))
            overlap = len(query_tokens & title_tokens)
            value = float(overlap)
            if self._is_direct_download_url(url):
                value += 6.0
            if any(token in url for token in ("download", "releases", "release", "latest")):
                value += 2.0
            if any(domain in url for domain in blacklist):
                value -= 4.0
            return value

        ranked = sorted(results, key=score, reverse=True)
        best = ranked[0]
        return best if score(best) > 0 else None

    def _is_direct_download_url(self, url: str) -> bool:
        path = urllib.parse.urlparse(url).path.lower()
        return path.endswith(DIRECT_DOWNLOAD_EXTENSIONS)

    def _resolve_folder(self, folder: str) -> Path:
        return DOWNLOAD_FOLDERS.get((folder or "downloads").lower(), DOWNLOAD_FOLDERS["downloads"])

    def _sanitize_filename(self, filename: str) -> str:
        name = re.sub(r'[<>:"/\\|?*]+', "_", filename).strip()
        return name[:180] or "downloaded_file"

    def _ensure_unique_path(self, path: Path) -> Path:
        if not path.exists():
            return path
        stem = path.stem
        suffix = path.suffix
        counter = 1
        while True:
            candidate = path.with_name(f"{stem}_{counter}{suffix}")
            if not candidate.exists():
                return candidate
            counter += 1

    def _filename_from_content_disposition(self, header: str) -> str:
        match = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?', header or "", re.IGNORECASE)
        if not match:
            return ""
        return os.path.basename(urllib.parse.unquote(match.group(1).strip()))
