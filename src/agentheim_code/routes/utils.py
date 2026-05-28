from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException, Request


def workspace_from_request(request: Request, workspace_root: str | None = None) -> Path:
    base = Path(request.app.state.workspace_path)
    if not workspace_root or workspace_root == ".":
        return base
    candidate = Path(workspace_root)
    if not candidate.is_absolute():
        candidate = base / candidate
    resolved = candidate.resolve()
    if not resolved.exists() or not resolved.is_dir():
        raise HTTPException(status_code=400, detail=f"Workspace does not exist: {resolved}")
    return resolved


def workspace_base(request: Request) -> Path:
    return Path(request.app.state.workspace_path)


def request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", ""))
