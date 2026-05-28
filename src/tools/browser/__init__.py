"""Browser automation tool implementing ToolProtocol.

Web page interaction with Playwright primary backend and HTTP fallback chain.
Supports persistent sessions for multi-step workflows.
"""

from __future__ import annotations

import asyncio
import base64
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from core.errors import ToolSafetyError
from core.tool_protocol import (
    AsyncBaseTool,
    BaseTool,
    ParamSchema,
    ReturnSchema,
    RiskLevel,
    ToolContext,
    ToolResult,
    ToolSchema,
)
from tools.browser.session import BrowserSessionManager
from tools.network import NetworkEnforcer, NetworkPolicy, NetworkViolation

# Default browser network policy: http/https only, private/link-local blocked.
_BROWSER_POLICY = NetworkPolicy(
    allowed=True,
    allowed_schemes=("http", "https"),
    deny_private_ranges=True,
    deny_link_local=True,
)


class BrowserTool(BaseTool):
    """Browser automation with Playwright primary and HTTP fallback.

    Supports two modes:
    1. **Session mode**: Create a session with ``operation=create_session``,
       then reuse it across ``navigate``, ``click``, ``fill``, etc.
    2. **Transient mode**: Each operation launches its own browser
       (backward-compatible, but slower).
    """

    PLAYWRIGHT_OPS = {"screenshot", "click", "fill", "evaluate", "create_session", "close_session"}

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        schema = ToolSchema(
            description="Browser automation for web page interaction. Supports persistent sessions for multi-step workflows.",
            parameters={
                "operation": ParamSchema(
                    type="string",
                    description="Operation to perform",
                    enum=[
                        "navigate",
                        "get_text",
                        "get_links",
                        "screenshot",
                        "click",
                        "fill",
                        "evaluate",
                        "create_session",
                        "close_session",
                    ],
                    required=True,
                ),
                "url": ParamSchema(type="string", description="URL to navigate to", required=False),
                "selector": ParamSchema(
                    type="string",
                    description="CSS selector for click/fill/get_text",
                    required=False,
                ),
                "value": ParamSchema(
                    type="string", description="Value to fill into input", required=False
                ),
                "script": ParamSchema(
                    type="string", description="JavaScript to evaluate", required=False
                ),
                "save_path": ParamSchema(
                    type="string",
                    description="Relative path to save screenshot (omit for base64)",
                    required=False,
                ),
                "timeout": ParamSchema(
                    type="integer", description="Timeout in seconds", default=30, required=False
                ),
                "session_id": ParamSchema(
                    type="string",
                    description="Session ID for persistent browser context",
                    required=False,
                ),
            },
            returns=ReturnSchema(type="object", description="Operation result"),
        )
        super().__init__("browser", schema, RiskLevel.HIGH)

    @staticmethod
    def _validate_url(url: str) -> None:
        """Validate URL scheme and host against browser network policy.

        Raises ToolSafetyError on violation.
        """
        if not url:
            return
        enforcer = NetworkEnforcer(_BROWSER_POLICY)
        try:
            enforcer.validate(url)
        except NetworkViolation as exc:
            raise ToolSafetyError(str(exc)) from exc

    def invoke(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
        valid, err = self.validate_params(params)
        if not valid:
            return ToolResult(success=False, error=err)

        operation = params.get("operation")
        url = params.get("url", "")
        session_id = params.get("session_id")

        # Network policy check
        if not context.network_allowed:
            return ToolResult(success=False, error="Network access is not allowed by policy.")

        # URL scheme/host enforcement
        try:
            self._validate_url(url)
        except ToolSafetyError as exc:
            return ToolResult(success=False, error=str(exc))

        try:
            if operation == "create_session":
                return self._create_session()
            if operation == "close_session":
                return self._close_session(session_id)

            # URL required for all ops except evaluate (which may run on current page context)
            if operation != "evaluate" and not url and not session_id:
                return ToolResult(
                    success=False, error="Parameter 'url' is required for this operation."
                )

            if operation == "navigate":
                return self._navigate(url, params.get("timeout", 30), session_id)
            if operation == "get_text":
                return self._get_text(
                    url, params.get("selector"), params.get("timeout", 30), session_id
                )
            if operation == "get_links":
                return self._get_links(url, params.get("timeout", 30), session_id)
            if operation == "screenshot":
                return self._screenshot(
                    url, params.get("save_path"), params.get("timeout", 30), session_id
                )
            if operation == "click":
                return self._click(
                    url, params.get("selector", ""), params.get("timeout", 30), session_id
                )
            if operation == "fill":
                return self._fill(
                    url,
                    params.get("selector", ""),
                    params.get("value", ""),
                    params.get("timeout", 30),
                    session_id,
                )
            if operation == "evaluate":
                return self._evaluate(
                    url, params.get("script", ""), params.get("timeout", 30), session_id
                )
        except ToolSafetyError as exc:
            return ToolResult(success=False, error=str(exc))

        return ToolResult(success=False, error=f"Unknown operation: {operation}")

    # ------------------------------------------------------------------
    # Session helpers
    # ------------------------------------------------------------------

    def _create_session(self) -> ToolResult:
        manager = BrowserSessionManager()
        sid = manager.create_session()
        return ToolResult(
            success=True,
            data={"session_id": sid},
            metadata={"backend": "playwright", "action": "session_created"},
        )

    def _close_session(self, session_id: str | None) -> ToolResult:
        if not session_id:
            return ToolResult(
                success=False, error="Parameter 'session_id' is required for close_session."
            )
        manager = BrowserSessionManager()
        manager.close_session(session_id)
        return ToolResult(
            success=True,
            data={"session_id": session_id},
            metadata={"backend": "playwright", "action": "session_closed"},
        )

    def _get_page(self, url: str, timeout: int, session_id: str | None) -> Any:
        """Return a page object, creating a transient session if needed."""
        self._validate_url(url)
        manager = BrowserSessionManager()
        if session_id:
            page = manager.get_page(session_id)
            if page is None:
                raise ToolSafetyError(
                    f"Session '{session_id}' not found. Create it first with operation=create_session."
                )
            if url:
                page.goto(url, timeout=timeout * 1000, wait_until="domcontentloaded")
            return page
        # Transient: launch new browser
        from playwright.sync_api import sync_playwright

        p = sync_playwright().start()
        browser = p.chromium.launch()
        page = browser.new_page()
        if url:
            page.goto(url, timeout=timeout * 1000, wait_until="domcontentloaded")
        return page

    # ------------------------------------------------------------------
    # Backend helpers
    # ------------------------------------------------------------------

    def _resolve_save_path(self, raw_path: str | None) -> Path | None:
        """Resolve and validate a screenshot save path."""
        if not raw_path:
            return None
        target = (self.repo_root / raw_path).resolve()
        try:
            target.relative_to(self.repo_root)
        except ValueError as exc:
            raise ToolSafetyError(f"Save path escapes workspace: {raw_path}") from exc
        target.parent.mkdir(parents=True, exist_ok=True)
        return target

    @staticmethod
    def _playwright_available() -> bool:
        try:
            from playwright.sync_api import sync_playwright  # noqa: F401

            return True
        except Exception:
            return False

    @staticmethod
    def _playwright_install_guidance() -> str:
        return "Install Playwright: pip install playwright && playwright install chromium"

    # ------------------------------------------------------------------
    # Operations
    # ------------------------------------------------------------------

    def _navigate(self, url: str, timeout: int, session_id: str | None) -> ToolResult:
        """Navigate to URL and return page metadata."""
        if session_id:
            manager = BrowserSessionManager()
            if not url:
                page = manager.get_page(session_id)
                if page is None:
                    return ToolResult(success=False, error=f"Session '{session_id}' not found.")
                return ToolResult(
                    success=True,
                    data={"title": page.title(), "status": None, "url": page.url},
                    metadata={"backend": "playwright", "session_id": session_id},
                )
            meta = manager.navigate(session_id, url, timeout)
            return ToolResult(
                success=True,
                data=meta,
                metadata={"backend": "playwright", "session_id": session_id},
            )
        if self._playwright_available():
            return self._navigate_playwright(url, timeout)
        return self._navigate_http_fallback(url, timeout)

    def _get_text(
        self, url: str, selector: str | None, timeout: int, session_id: str | None
    ) -> ToolResult:
        if session_id or self._playwright_available():
            try:
                page = self._get_page(url, timeout, session_id)
                if selector:
                    text = page.locator(selector).first.inner_text(timeout=timeout * 1000)
                else:
                    text = page.locator("body").inner_text(timeout=timeout * 1000)
                return ToolResult(
                    success=True,
                    data=text,
                    metadata={"backend": "playwright", "session_id": session_id},
                )
            except Exception as exc:
                return ToolResult(success=False, error=str(exc))
        return self._get_text_http_fallback(url, selector, timeout)

    def _get_links(self, url: str, timeout: int, session_id: str | None) -> ToolResult:
        if session_id or self._playwright_available():
            try:
                page = self._get_page(url, timeout, session_id)
                links = page.locator("a").all()
                results = []
                for link in links:
                    href = link.get_attribute("href") or ""
                    text = link.inner_text().strip()
                    if href:
                        results.append({"text": text, "href": href})
                return ToolResult(
                    success=True,
                    data=results,
                    metadata={
                        "backend": "playwright",
                        "count": len(results),
                        "session_id": session_id,
                    },
                )
            except Exception as exc:
                return ToolResult(success=False, error=str(exc))
        return self._get_links_http_fallback(url, timeout)

    def _screenshot(
        self, url: str, save_path: str | None, timeout: int, session_id: str | None
    ) -> ToolResult:
        if not self._playwright_available():
            return ToolResult(
                success=False,
                error=f"Screenshot requires Playwright which is not available. {self._playwright_install_guidance()}",
            )
        target = self._resolve_save_path(save_path)
        try:
            page = self._get_page(url, timeout, session_id)
            if target:
                page.screenshot(path=str(target), full_page=True)
                return ToolResult(
                    success=True,
                    data=str(target.relative_to(self.repo_root)),
                    metadata={
                        "backend": "playwright",
                        "format": "png",
                        "saved": True,
                        "session_id": session_id,
                    },
                )
            else:
                png_bytes = page.screenshot(full_page=True)
                b64 = base64.b64encode(png_bytes).decode("ascii")
                return ToolResult(
                    success=True,
                    data=b64,
                    metadata={
                        "backend": "playwright",
                        "format": "png",
                        "saved": False,
                        "encoding": "base64",
                        "session_id": session_id,
                    },
                )
        except Exception as exc:
            return ToolResult(success=False, error=str(exc))

    def _click(self, url: str, selector: str, timeout: int, session_id: str | None) -> ToolResult:
        if not selector:
            return ToolResult(success=False, error="Parameter 'selector' is required for click.")
        if not self._playwright_available():
            return ToolResult(
                success=False,
                error=f"Click requires Playwright which is not available. {self._playwright_install_guidance()}",
            )
        try:
            page = self._get_page(url, timeout, session_id)
            page.locator(selector).first.click(timeout=timeout * 1000)
            return ToolResult(
                success=True,
                data={"clicked": selector},
                metadata={"backend": "playwright", "session_id": session_id},
            )
        except Exception as exc:
            return ToolResult(success=False, error=str(exc))

    def _fill(
        self, url: str, selector: str, value: str, timeout: int, session_id: str | None
    ) -> ToolResult:
        if not selector:
            return ToolResult(success=False, error="Parameter 'selector' is required for fill.")
        if not self._playwright_available():
            return ToolResult(
                success=False,
                error=f"Fill requires Playwright which is not available. {self._playwright_install_guidance()}",
            )
        try:
            page = self._get_page(url, timeout, session_id)
            page.locator(selector).first.fill(value, timeout=timeout * 1000)
            return ToolResult(
                success=True,
                data={"filled": selector},
                metadata={"backend": "playwright", "session_id": session_id},
            )
        except Exception as exc:
            return ToolResult(success=False, error=str(exc))

    def _evaluate(self, url: str, script: str, timeout: int, session_id: str | None) -> ToolResult:
        if not script:
            return ToolResult(success=False, error="Parameter 'script' is required for evaluate.")
        if not self._playwright_available():
            return ToolResult(
                success=False,
                error=f"Evaluate requires Playwright which is not available. {self._playwright_install_guidance()}",
            )
        try:
            page = self._get_page(url, timeout, session_id)
            result = page.evaluate(script)
            return ToolResult(
                success=True,
                data=result,
                metadata={"backend": "playwright", "session_id": session_id},
            )
        except Exception as exc:
            return ToolResult(success=False, error=str(exc))

    # ------------------------------------------------------------------
    # Playwright backends (transient mode)
    # ------------------------------------------------------------------

    def _navigate_playwright(self, url: str, timeout: int) -> ToolResult:
        from playwright.sync_api import sync_playwright

        p = sync_playwright().start()
        browser = p.chromium.launch()
        try:
            page = browser.new_page()
            response = page.goto(url, timeout=timeout * 1000, wait_until="domcontentloaded")
            status = response.status if response else None
            title = page.title()
            return ToolResult(
                success=True,
                data={"title": title, "status": status, "url": page.url},
                metadata={"backend": "playwright"},
            )
        finally:
            browser.close()
            p.stop()

    # ------------------------------------------------------------------
    # HTTP fallback backends (requests → urllib)
    # ------------------------------------------------------------------

    def _fetch_with_requests(self, url: str, timeout: int) -> tuple[int, str]:
        import requests

        resp = requests.get(
            url,
            timeout=timeout,
            headers={"User-Agent": "AI-Team-BrowserTool/1.0"},
            allow_redirects=False,
        )
        return resp.status_code, resp.text

    def _fetch_with_urllib(self, url: str, timeout: int) -> tuple[int | None, str]:
        req = urllib.request.Request(url, headers={"User-Agent": "AI-Team-BrowserTool/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.status, response.read().decode("utf-8", errors="ignore")

    def _fetch(self, url: str, timeout: int) -> tuple[int | None, str]:
        try:
            return self._fetch_with_requests(url, timeout)
        except Exception:
            try:
                return self._fetch_with_urllib(url, timeout)
            except urllib.error.HTTPError as exc:
                return exc.code, exc.read().decode("utf-8", errors="ignore")
            except Exception as exc:
                return None, str(exc)

    def _navigate_http_fallback(self, url: str, timeout: int) -> ToolResult:
        status, html = self._fetch(url, timeout)
        if status is None:
            return ToolResult(success=False, error=f"Failed to fetch URL: {html}")
        # Extract title from HTML
        title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        title = title_match.group(1).strip() if title_match else ""
        return ToolResult(
            success=True,
            data={"title": title, "status": status, "url": url},
            metadata={"backend": "http_fallback"},
        )

    def _get_text_http_fallback(self, url: str, selector: str | None, timeout: int) -> ToolResult:
        status, html = self._fetch(url, timeout)
        if status is None:
            return ToolResult(success=False, error=f"Failed to fetch URL: {html}")
        try:
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(html, "html.parser")
            if selector:
                element = soup.select_one(selector)
                if element is None:
                    return ToolResult(success=False, error=f"Selector not found: {selector}")
                text = element.get_text(separator="\n", strip=True)
            else:
                # Remove script/style tags
                for tag in soup(["script", "style"]):
                    tag.decompose()
                text = soup.get_text(separator="\n", strip=True)
            return ToolResult(success=True, data=text, metadata={"backend": "http_fallback"})
        except ImportError:
            # Pure regex fallback
            text = re.sub(r"<[^>]+>", " ", html)
            text = re.sub(r"\s+", " ", text).strip()
            return ToolResult(success=True, data=text, metadata={"backend": "urllib_fallback"})

    def _get_links_http_fallback(self, url: str, timeout: int) -> ToolResult:
        status, html = self._fetch(url, timeout)
        if status is None:
            return ToolResult(success=False, error=f"Failed to fetch URL: {html}")
        try:
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(html, "html.parser")
            links = []
            for a in soup.find_all("a", href=True):
                links.append({"text": a.get_text(strip=True), "href": a["href"]})
            return ToolResult(
                success=True, data=links, metadata={"backend": "http_fallback", "count": len(links)}
            )
        except ImportError:
            # Regex fallback
            links = []
            for match in re.finditer(
                r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', html, re.IGNORECASE | re.DOTALL
            ):
                href = match.group(1)
                text = re.sub(r"<[^>]+>", "", match.group(2)).strip()
                links.append({"text": text, "href": href})
            return ToolResult(
                success=True,
                data=links,
                metadata={"backend": "urllib_fallback", "count": len(links)},
            )


class AsyncBrowserTool(AsyncBaseTool):
    """Async browser automation tool.

    Uses :mod:`playwright.async_api` for transient mode and wraps the
    synchronous :class:`BrowserSessionManager` in ``asyncio.to_thread()``
    for session mode.
    """

    PLAYWRIGHT_OPS = {"screenshot", "click", "fill", "evaluate", "create_session", "close_session"}

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        schema = ToolSchema(
            description="Async browser automation for web page interaction. Supports persistent sessions for multi-step workflows.",
            parameters={
                "operation": ParamSchema(
                    type="string",
                    description="Operation to perform",
                    enum=[
                        "navigate",
                        "get_text",
                        "get_links",
                        "screenshot",
                        "click",
                        "fill",
                        "evaluate",
                        "create_session",
                        "close_session",
                    ],
                    required=True,
                ),
                "url": ParamSchema(type="string", description="URL to navigate to", required=False),
                "selector": ParamSchema(
                    type="string",
                    description="CSS selector for click/fill/get_text",
                    required=False,
                ),
                "value": ParamSchema(
                    type="string", description="Value to fill into input", required=False
                ),
                "script": ParamSchema(
                    type="string", description="JavaScript to evaluate", required=False
                ),
                "save_path": ParamSchema(
                    type="string",
                    description="Relative path to save screenshot (omit for base64)",
                    required=False,
                ),
                "timeout": ParamSchema(
                    type="integer", description="Timeout in seconds", default=30, required=False
                ),
                "session_id": ParamSchema(
                    type="string",
                    description="Session ID for persistent browser context",
                    required=False,
                ),
            },
            returns=ReturnSchema(type="object", description="Operation result"),
        )
        super().__init__("browser.async", schema, RiskLevel.HIGH)

    async def ainvoke(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
        valid, err = self.validate_params(params)
        if not valid:
            return ToolResult(success=False, error=err)

        operation = params.get("operation")
        url = params.get("url", "")

        if not context.network_allowed:
            return ToolResult(success=False, error="Network access is not allowed by policy.")

        try:
            BrowserTool._validate_url(url)
        except ToolSafetyError as exc:
            return ToolResult(success=False, error=str(exc))

        try:
            if operation == "create_session":
                return await asyncio.to_thread(self._create_session_sync)
            if operation == "close_session":
                session_id = params.get("session_id")
                return await asyncio.to_thread(self._close_session_sync, session_id)

            if operation in (
                "navigate",
                "get_text",
                "get_links",
                "screenshot",
                "click",
                "fill",
                "evaluate",
            ):
                session_id = params.get("session_id")
                if session_id:
                    # Session mode — wrap sync calls in thread
                    return await asyncio.to_thread(self._sync_invoke, operation, params, context)
                # Transient mode — use async playwright
                return await self._async_transient_invoke(operation, params, context)
        except ToolSafetyError as exc:
            return ToolResult(success=False, error=str(exc))

        return ToolResult(success=False, error=f"Unknown operation: {operation}")

    def _create_session_sync(self) -> ToolResult:
        manager = BrowserSessionManager()
        sid = manager.create_session()
        return ToolResult(
            success=True,
            data={"session_id": sid},
            metadata={"backend": "playwright", "action": "session_created"},
        )

    def _close_session_sync(self, session_id: str | None) -> ToolResult:
        if not session_id:
            return ToolResult(
                success=False, error="Parameter 'session_id' is required for close_session."
            )
        manager = BrowserSessionManager()
        manager.close_session(session_id)
        return ToolResult(
            success=True,
            data={"session_id": session_id},
            metadata={"backend": "playwright", "action": "session_closed"},
        )

    def _sync_invoke(
        self, operation: str, params: dict[str, Any], context: ToolContext
    ) -> ToolResult:
        """Delegate to sync BrowserTool for session-mode operations."""
        sync_tool = BrowserTool(self.repo_root)
        return sync_tool.invoke(params, context)

    async def _async_transient_invoke(
        self, operation: str, params: dict[str, Any], context: ToolContext
    ) -> ToolResult:
        """Use playwright.async_api for transient (non-session) operations."""
        from playwright.async_api import async_playwright

        url = params.get("url", "")
        timeout = params.get("timeout", 30)
        selector = params.get("selector")
        save_path = params.get("save_path")

        async with async_playwright() as p:
            browser = await p.chromium.launch()
            try:
                page = await browser.new_page()
                BrowserTool._validate_url(url)
                if url:
                    await page.goto(url, timeout=timeout * 1000, wait_until="domcontentloaded")

                if operation == "navigate":
                    return ToolResult(
                        success=True,
                        data={"title": await page.title(), "status": None, "url": page.url},
                        metadata={"backend": "playwright.async"},
                    )
                if operation == "get_text":
                    if selector:
                        text = await page.locator(selector).first.inner_text(timeout=timeout * 1000)
                    else:
                        text = await page.locator("body").inner_text(timeout=timeout * 1000)
                    return ToolResult(
                        success=True, data=text, metadata={"backend": "playwright.async"}
                    )
                if operation == "get_links":
                    links = await page.locator("a").all()
                    results = []
                    for link in links:
                        href = await link.get_attribute("href") or ""
                        text = (await link.inner_text()).strip()
                        if href:
                            results.append({"text": text, "href": href})
                    return ToolResult(
                        success=True,
                        data=results,
                        metadata={"backend": "playwright.async", "count": len(results)},
                    )
                if operation == "screenshot":
                    target = BrowserTool(self.repo_root)._resolve_save_path(save_path)
                    if target:
                        await page.screenshot(path=str(target), full_page=True)
                        return ToolResult(
                            success=True,
                            data=str(target.relative_to(self.repo_root)),
                            metadata={
                                "backend": "playwright.async",
                                "format": "png",
                                "saved": True,
                            },
                        )
                    else:
                        png_bytes = await page.screenshot(full_page=True)
                        b64 = base64.b64encode(png_bytes).decode("ascii")
                        return ToolResult(
                            success=True,
                            data=b64,
                            metadata={
                                "backend": "playwright.async",
                                "format": "png",
                                "saved": False,
                                "encoding": "base64",
                            },
                        )
                if operation == "click":
                    if not selector:
                        return ToolResult(
                            success=False, error="Parameter 'selector' is required for click."
                        )
                    await page.locator(selector).first.click(timeout=timeout * 1000)
                    return ToolResult(
                        success=True,
                        data={"clicked": selector},
                        metadata={"backend": "playwright.async"},
                    )
                if operation == "fill":
                    if not selector:
                        return ToolResult(
                            success=False, error="Parameter 'selector' is required for fill."
                        )
                    value = params.get("value", "")
                    await page.locator(selector).first.fill(value, timeout=timeout * 1000)
                    return ToolResult(
                        success=True,
                        data={"filled": selector},
                        metadata={"backend": "playwright.async"},
                    )
                if operation == "evaluate":
                    script = params.get("script", "")
                    if not script:
                        return ToolResult(
                            success=False, error="Parameter 'script' is required for evaluate."
                        )
                    result = await page.evaluate(script)
                    return ToolResult(
                        success=True, data=result, metadata={"backend": "playwright.async"}
                    )
            finally:
                await browser.close()

        return ToolResult(success=False, error=f"Unknown operation: {operation}")
