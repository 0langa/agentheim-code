"""Browser session manager for persistent Playwright contexts.

Allows multi-step browser workflows (navigate → click → fill → screenshot)
without launching a new browser per operation.
"""

from __future__ import annotations

import logging
import threading
import uuid
from typing import Any

logger = logging.getLogger(__name__)


class BrowserSession:
    """Holds a single Playwright browser context and page."""

    def __init__(self, playwright: Any, browser: Any, context: Any, page: Any) -> None:
        self.playwright = playwright
        self.browser = browser
        self.context = context
        self.page = page
        self.created_at = __import__("time").time()

    def close(self) -> None:
        try:
            self.context.close()
        except Exception as exc:
            logger.debug("Error closing browser context: %s", exc)
        try:
            self.browser.close()
        except Exception as exc:
            logger.debug("Error closing browser: %s", exc)
        try:
            self.playwright.stop()
        except Exception as exc:
            logger.debug("Error stopping playwright: %s", exc)


class BrowserSessionManager:
    """Singleton manager for persistent browser sessions.

    Maps session IDs to :class:`BrowserSession` objects so that agents can
    perform multi-step web interactions without launching a new browser each
    time.
    """

    _instance: BrowserSessionManager | None = None
    _lock = threading.Lock()
    _sessions: dict[str, BrowserSession]
    _session_lock: threading.Lock

    def __new__(cls) -> BrowserSessionManager:
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._sessions = {}
                cls._instance._session_lock = threading.Lock()
            return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Close all sessions and reset the singleton (mainly for tests)."""
        with cls._lock:
            if cls._instance is not None:
                cls._instance.close_all()
                cls._instance = None

    def create_session(self, headless: bool = True) -> str:
        """Launch a new browser and return its session ID."""
        from playwright.sync_api import sync_playwright

        p = sync_playwright().start()
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context()
        page = context.new_page()
        session_id = str(uuid.uuid4())
        with self._session_lock:
            self._sessions[session_id] = BrowserSession(p, browser, context, page)
        logger.debug("Created browser session %s", session_id)
        return session_id

    def get_page(self, session_id: str) -> Any:
        """Return the page for an existing session, or None if not found."""
        with self._session_lock:
            session = self._sessions.get(session_id)
        if session is None:
            return None
        return session.page

    def navigate(self, session_id: str, url: str, timeout: int) -> dict[str, Any]:
        """Navigate an existing session to *url*."""
        page = self.get_page(session_id)
        if page is None:
            raise RuntimeError(f"Browser session '{session_id}' not found")
        response = page.goto(url, timeout=timeout * 1000, wait_until="domcontentloaded")
        return {
            "title": page.title(),
            "status": response.status if response else None,
            "url": page.url,
        }

    def close_session(self, session_id: str) -> None:
        """Close a specific session."""
        with self._session_lock:
            session = self._sessions.pop(session_id, None)
        if session is not None:
            session.close()
            logger.debug("Closed browser session %s", session_id)

    def close_all(self) -> None:
        """Close all managed sessions."""
        with self._session_lock:
            sessions = list(self._sessions.items())
            self._sessions.clear()
        for sid, session in sessions:
            try:
                session.close()
            except Exception as exc:
                logger.warning("Error closing session %s: %s", sid, exc)
        logger.debug("Closed all browser sessions")
