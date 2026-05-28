from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from agentheim_code.routes.utils import workspace_from_request
from core.path_security import safe_workspace_file_path
from workflows.coder.runtime import browse_file_tree, list_file_tree

router = APIRouter(prefix="/api/coder")


class FileEntryResponse(BaseModel):
    path: str
    type: str


class FileBrowseResponse(BaseModel):
    items: list[FileEntryResponse]
    next_offset: int | None = None
    has_more: bool
    query: str = ""


def _search_file_tree(workspace: Path, query: str, limit: int) -> list[dict[str, Any]]:
    lowered = query.lower().strip()
    results = []
    for item in list_file_tree(workspace, limit=1000):
        path = str(item.get("path", ""))
        if lowered and lowered not in path.lower():
            continue
        if item.get("type") != "file":
            continue
        results.append(item)
        if len(results) >= limit:
            break
    return cast(list[dict[str, Any]], results)


def _safe_preview_path(workspace: Path, path: str) -> Path:
    if not path:
        raise HTTPException(status_code=400, detail="Path is required.")
    try:
        target = safe_workspace_file_path(workspace, path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found.")
    return target


@router.get("/files", response_model=list[FileEntryResponse])
def api_files(request: Request, workspace_root: str | None = None) -> list[FileEntryResponse]:
    return cast(
        list[FileEntryResponse],
        [
            FileEntryResponse.model_validate(item)
            for item in list_file_tree(workspace_from_request(request, workspace_root))
        ],
    )


@router.get("/files/browser", response_model=FileBrowseResponse)
def api_file_browser(
    request: Request,
    q: str = "",
    limit: int = 100,
    offset: int = 0,
    workspace_root: str | None = None,
) -> FileBrowseResponse:
    bounded_limit = max(1, min(limit, 200))
    bounded_offset = max(offset, 0)
    items, next_offset = browse_file_tree(
        workspace_from_request(request, workspace_root),
        query=q,
        limit=bounded_limit,
        offset=bounded_offset,
    )
    return FileBrowseResponse(
        items=[FileEntryResponse.model_validate(item) for item in items],
        next_offset=next_offset,
        has_more=next_offset is not None,
        query=q,
    )


@router.get("/files/search", response_model=list[FileEntryResponse])
def api_file_search(
    request: Request, q: str = "", limit: int = 50, workspace_root: str | None = None
) -> list[FileEntryResponse]:
    bounded_limit = max(1, min(limit, 200))
    return [
        FileEntryResponse.model_validate(item)
        for item in _search_file_tree(
            workspace_from_request(request, workspace_root), q, bounded_limit
        )
    ]


@router.get("/files/preview")
def api_file_preview(request: Request, path: str = "", workspace_root: str | None = None) -> str:
    target = _safe_preview_path(workspace_from_request(request, workspace_root), path)
    try:
        return target.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not read file: {exc}") from exc
