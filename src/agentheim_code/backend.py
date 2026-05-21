from __future__ import annotations

from pathlib import Path

from interfaces.web_ui import create_app as create_agentheim_app


def create_app(workspace: str | Path = "."):
    """Create the local-only Agentheim Code backend app."""
    return create_agentheim_app(repo_root=Path(workspace).resolve())

