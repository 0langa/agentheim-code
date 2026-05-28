from __future__ import annotations

import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


class DuckDuckGoSearchAdapter:
    """Real web search via duckduckgo-search (optional dependency)."""

    def __init__(self) -> None:
        self._client = None
        try:
            from duckduckgo_search import DDGS

            self._client = DDGS()
        except Exception:
            pass

    @property
    def available(self) -> bool:
        return self._client is not None

    def search(self, query: str, max_results: int = 5) -> dict[str, Any]:
        if not self.available:
            raise RuntimeError("duckduckgo-search is not installed.")
        client = self._client
        if client is None:
            raise RuntimeError("duckduckgo-search is not installed.")
        results = client.text(query, max_results=max_results)
        return {
            "query": query,
            "source": "duckduckgo",
            "results": [
                {
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "snippet": r.get("body", ""),
                }
                for r in results
            ],
        }


class UrllibSearchAdapter:
    """Fallback web search via DuckDuckGo HTML scraping."""

    def search(self, query: str, max_results: int = 5) -> dict[str, Any]:
        encoded = query.replace(" ", "+")
        url = f"https://html.duckduckgo.com/html/?q={encoded}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as response:
                html = response.read().decode("utf-8", errors="replace")
        except urllib.error.URLError as exc:
            return {"query": query, "source": "urllib", "error": str(exc), "results": []}

        results = []
        # Extract results from DuckDuckGo HTML
        for match in re.finditer(
            r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html
        ):
            href = match.group(1)
            title = re.sub(r"<[^>]+>", "", match.group(2))
            if href and title:
                results.append({"title": title.strip(), "url": href, "snippet": ""})
            if len(results) >= max_results:
                break

        return {"query": query, "source": "urllib", "results": results}


class WebResearchAdapter:
    """Dispatcher: tries DuckDuckGo, then urllib, then reports unavailable."""

    def __init__(self, repo_root: str | Path, enabled: bool = True) -> None:
        self.repo_root = Path(repo_root)
        self.enabled = enabled
        self._ddg = DuckDuckGoSearchAdapter()

    @property
    def available(self) -> bool:
        return True  # Always has at least the urllib fallback

    def search(self, query: str) -> dict[str, Any]:
        if not self.enabled:
            return {
                "query": query,
                "source": "unavailable",
                "error": "Web research is disabled.",
                "setup_guidance": "Enable web research by setting enabled=True when creating the adapter, or install duckduckgo-search: pip install duckduckgo-search",
                "results": [],
            }

        # Try duckduckgo-search first
        if self._ddg.available:
            try:
                return self._ddg.search(query)
            except Exception as exc:
                return {
                    "query": query,
                    "source": "unavailable",
                    "error": f"duckduckgo-search failed: {exc}",
                    "setup_guidance": "Install or upgrade duckduckgo-search: pip install -U duckduckgo-search",
                    "results": [],
                }

        # Fallback to urllib scraping
        try:
            return UrllibSearchAdapter().search(query)
        except Exception as exc:
            return {
                "query": query,
                "source": "unavailable",
                "error": str(exc),
                "setup_guidance": "Install duckduckgo-search for reliable web research: pip install duckduckgo-search",
                "results": [],
            }
