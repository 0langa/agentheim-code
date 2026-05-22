from __future__ import annotations

import asyncio
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from pathlib import Path
from typing import Any, cast

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from config.config import list_provider_templates, load_profiles_document
from core.run_view import list_run_views
from workflows.coder.runtime import (
    approve_request,
    available_commands,
    cancel_session,
    create_session,
    get_session,
    get_session_view,
    list_file_tree,
    list_model_options,
    list_sessions,
    post_message,
    queue_message,
    set_session_mode,
    update_session_model,
)


class CoderSessionCreateRequest(BaseModel):
    workspace_root: str | None = None
    trust_mode: str = "ask"
    mode: str = "code"
    profile: str | None = None
    provider: str | None = None
    model: str | None = None


class CoderSessionMessageRequest(BaseModel):
    prompt: str = Field(min_length=1)


class CoderQueueRequest(BaseModel):
    prompt: str = Field(min_length=1)


class CoderSessionModelRequest(BaseModel):
    profile: str | None = None
    provider: str | None = None
    model: str | None = None


class CoderSessionModeRequest(BaseModel):
    mode: str = "code"


def _version() -> str:
    try:
        return package_version("agentheim-code")
    except PackageNotFoundError:
        return "0.1.0"


def _json_model(model: Any) -> dict[str, Any]:
    return cast(dict[str, Any], model.model_dump(mode="json"))


def _web_dist_dir() -> Path:
    packaged = Path(__file__).resolve().parent / "web"
    if (packaged / "index.html").exists():
        return packaged
    return Path(__file__).resolve().parents[2] / "apps" / "web" / "dist"


def _origin_allowed(origin: str | None) -> bool:
    if not origin:
        return True
    allowed_exact = {
        "tauri://localhost",
        "http://tauri.localhost",
        "https://tauri.localhost",
    }
    if origin in allowed_exact:
        return True
    return origin.startswith("http://127.0.0.1:") or origin.startswith("http://localhost:")


def _workspace(base: Path, workspace_root: str | None = None) -> Path:
    if not workspace_root or workspace_root == ".":
        return base
    candidate = Path(workspace_root)
    if not candidate.is_absolute():
        candidate = base / candidate
    resolved = candidate.resolve()
    if not resolved.exists() or not resolved.is_dir():
        raise HTTPException(status_code=400, detail=f"Workspace does not exist: {resolved}")
    return resolved


def create_app(workspace: str | Path = ".") -> FastAPI:
    """Create the local-only standalone Agentheim Code backend app."""
    workspace_path = Path(workspace).resolve()
    if not workspace_path.exists():
        raise FileNotFoundError(f"Workspace does not exist: {workspace_path}")
    if not workspace_path.is_dir():
        raise NotADirectoryError(f"Workspace must be a directory: {workspace_path}")

    app = FastAPI(title="Agentheim Code", version=_version())
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=(
            r"^(http://(127\.0\.0\.1|localhost)(:\d+)?|"
            r"https?://tauri\.localhost|tauri://localhost)$"
        ),
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": _version(), "workspace": str(workspace_path)}

    @app.get("/api/coder/sessions")
    def api_list_sessions(workspace_root: str | None = None) -> list[dict[str, Any]]:
        return [
            session.model_dump(mode="json")
            for session in list_sessions(_workspace(workspace_path, workspace_root))
        ]

    @app.post("/api/coder/sessions")
    def api_create_session(body: CoderSessionCreateRequest) -> dict[str, Any]:
        session = create_session(
            _workspace(workspace_path, body.workspace_root),
            trust_mode=body.trust_mode,
            mode=body.mode,
            profile=body.profile,
            provider=body.provider,
            model=body.model,
        )
        return _json_model(session)

    @app.get("/api/coder/sessions/{session_id}")
    def api_get_session(session_id: str, workspace_root: str | None = None) -> dict[str, Any]:
        return _json_model(get_session(_workspace(workspace_path, workspace_root), session_id))

    @app.get("/api/coder/sessions/{session_id}/view")
    def api_get_session_view(session_id: str, workspace_root: str | None = None) -> dict[str, Any]:
        return _json_model(get_session_view(_workspace(workspace_path, workspace_root), session_id))

    @app.post("/api/coder/sessions/{session_id}/messages")
    def api_post_message(
        session_id: str, body: CoderSessionMessageRequest, workspace_root: str | None = None
    ) -> dict[str, Any]:
        return _json_model(
            post_message(_workspace(workspace_path, workspace_root), session_id, body.prompt)
        )

    @app.post("/api/coder/sessions/{session_id}/queue")
    def api_queue_message(
        session_id: str, body: CoderQueueRequest, workspace_root: str | None = None
    ) -> dict[str, Any]:
        return _json_model(
            queue_message(_workspace(workspace_path, workspace_root), session_id, body.prompt)
        )

    @app.patch("/api/coder/sessions/{session_id}/model")
    def api_update_model(
        session_id: str, body: CoderSessionModelRequest, workspace_root: str | None = None
    ) -> dict[str, Any]:
        return _json_model(
            update_session_model(
                _workspace(workspace_path, workspace_root),
                session_id,
                profile=body.profile,
                provider=body.provider,
                model=body.model,
            )
        )

    @app.patch("/api/coder/sessions/{session_id}/mode")
    def api_update_mode(
        session_id: str, body: CoderSessionModeRequest, workspace_root: str | None = None
    ) -> dict[str, Any]:
        return _json_model(
            set_session_mode(_workspace(workspace_path, workspace_root), session_id, body.mode)
        )

    @app.post("/api/coder/sessions/{session_id}/cancel")
    def api_cancel_session(session_id: str, workspace_root: str | None = None) -> dict[str, Any]:
        return _json_model(cancel_session(_workspace(workspace_path, workspace_root), session_id))

    @app.post("/api/coder/sessions/{session_id}/approvals/{request_id}/grant")
    def api_grant_approval(
        session_id: str, request_id: str, workspace_root: str | None = None
    ) -> dict[str, Any]:
        return _json_model(
            approve_request(
                _workspace(workspace_path, workspace_root), session_id, request_id, grant=True
            )
        )

    @app.post("/api/coder/sessions/{session_id}/approvals/{request_id}/deny")
    def api_deny_approval(
        session_id: str, request_id: str, workspace_root: str | None = None
    ) -> dict[str, Any]:
        return _json_model(
            approve_request(
                _workspace(workspace_path, workspace_root), session_id, request_id, grant=False
            )
        )

    @app.get("/api/coder/sessions/{session_id}/diff")
    def api_diff(session_id: str, workspace_root: str | None = None) -> list[dict[str, Any]]:
        return [
            _json_model(diff)
            for diff in get_session_view(
                _workspace(workspace_path, workspace_root), session_id
            ).diffs
        ]

    @app.get("/api/coder/files")
    def api_files(workspace_root: str | None = None) -> list[dict[str, Any]]:
        return cast(
            list[dict[str, Any]], list_file_tree(_workspace(workspace_path, workspace_root))
        )

    @app.get("/api/coder/runs")
    def api_runs(workspace_root: str | None = None) -> list[dict[str, Any]]:
        return [
            _json_model(view) for view in list_run_views(_workspace(workspace_path, workspace_root))
        ]

    @app.get("/api/coder/models")
    def api_models() -> dict[str, Any]:
        return cast(dict[str, Any], list_model_options())

    @app.get("/api/coder/commands")
    def api_commands() -> list[dict[str, str]]:
        return cast(list[dict[str, str]], available_commands())

    @app.get("/api/providers/templates")
    def api_provider_templates() -> list[dict[str, Any]]:
        return cast(list[dict[str, Any]], list_provider_templates(include_experimental=True))

    @app.get("/api/providers/profiles")
    def api_provider_profiles() -> dict[str, Any]:
        try:
            document = load_profiles_document()
        except Exception as exc:
            return {"configured": False, "error": str(exc), "profiles": []}
        return {
            "configured": True,
            "default_profile": document.default_profile,
            "profiles": [
                {
                    "name": profile.name,
                    "providers": [
                        {
                            "id": provider.id,
                            "kind": provider.kind,
                            "auth_mode": provider.auth_mode,
                            "endpoint": provider.endpoint,
                            "has_secret": bool(provider.secret_ref),
                        }
                        for provider in profile.providers.values()
                    ],
                    "models": [binding.model_dump() for binding in profile.models.values()],
                }
                for profile in document.profiles.values()
            ],
        }

    @app.websocket("/api/coder/sessions/{session_id}/events")
    async def api_events(websocket: WebSocket, session_id: str) -> None:
        if not _origin_allowed(websocket.headers.get("origin")):
            await websocket.close(code=1008)
            return
        await websocket.accept()
        previous_count = -1
        try:
            while True:
                view = get_session_view(workspace_path, session_id)
                events = [event.model_dump(mode="json") for event in view.events]
                if len(events) != previous_count:
                    await websocket.send_json({"session_id": session_id, "events": events})
                    previous_count = len(events)
                await asyncio.sleep(1)
        except WebSocketDisconnect:
            return

    dist = _web_dist_dir()
    index = dist / "index.html"

    @app.get("/", response_class=HTMLResponse)
    @app.get("/coder", response_class=HTMLResponse)
    def coder_index() -> str:
        if index.exists():
            html = index.read_text(encoding="utf-8")
            if "Agentheim Coder" not in html:
                html = html.replace(
                    '<div id="root"></div>', '<div id="root"></div><!-- Agentheim Coder -->'
                )
            return html
        return "<!doctype html><title>Agentheim Code</title><h1>Agentheim Code</h1><p>Run npm --prefix apps/web run build to create the UI bundle.</p>"

    if dist.exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    return app
