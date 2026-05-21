from __future__ import annotations

from pathlib import Path

from interfaces.web_ui import create_app as create_agentheim_app


def create_app(workspace: str | Path = ".") -> object:
    """Create the local-only Agentheim Code backend app."""
    workspace_path = Path(workspace).resolve()
    if not workspace_path.exists():
        raise FileNotFoundError(f"Workspace does not exist: {workspace_path}")
    if not workspace_path.is_dir():
        raise NotADirectoryError(f"Workspace must be a directory: {workspace_path}")
    return create_agentheim_app(repo_root=workspace_path)
