"""Logging setup for AICtx."""

from __future__ import annotations

import logging
from typing import Any

from rich.console import Console
from rich.logging import RichHandler

CONSOLE = Console(stderr=True)


def setup_logging(level: int = logging.INFO, **kwargs: Any) -> None:
    """Configure structured logging with Rich."""
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=CONSOLE, rich_tracebacks=True)],
        force=True,
        **kwargs,
    )
