"""Graceful startup/shutdown hooks for the FastAPI backend."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from fastapi import FastAPI

logger = logging.getLogger("agentheim_code.lifecycle")


def build_lifespan() -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    @asynccontextmanager
    async def _lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        logger.info("Agentheim Code backend starting (%s)", app.title)
        yield
        logger.info("Agentheim Code backend shutting down")

    return _lifespan
