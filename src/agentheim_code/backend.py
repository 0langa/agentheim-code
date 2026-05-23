from __future__ import annotations

import asyncio
import json
import urllib.request
from collections.abc import AsyncIterator
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from pathlib import Path
from typing import Any, cast

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from agentheim_code import config as ui_config
from agentheim_code.provider_wizard import (
    create_profile,
    delete_profile,
    get_templates,
    verify_provider_connection,
)
from agentheim_code.usage_api import aggregate_session_usage
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
    context_files: list[str] = Field(default_factory=list)


class CoderQueueRequest(BaseModel):
    prompt: str = Field(min_length=1)


class CoderSessionModelRequest(BaseModel):
    profile: str | None = None
    provider: str | None = None
    model: str | None = None


class CoderSessionModeRequest(BaseModel):
    mode: str = "code"


class UiConfigPatch(BaseModel):
    onboarding_complete: bool | None = None
    onboarding_dismissed: bool | None = None
    default_workspace: str | None = None
    theme: str | None = None


class OnboardingCompleteRequest(BaseModel):
    default_workspace: str | None = None


def _version() -> str:
    try:
        return package_version("agentheim-code")
    except PackageNotFoundError:
        return "0.3.0"


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


def _sse(event: str, data: dict[str, Any]) -> str:
    payload = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


def _chunk_text(text: str, size: int = 24) -> list[str]:
    if not text:
        return []
    return [text[index : index + size] for index in range(0, len(text), size)]


def _prompt_with_context(prompt: str, context_files: list[str]) -> str:
    files = [path.strip() for path in context_files if path.strip()]
    if not files:
        return prompt
    listed = "\n".join(f"- {path}" for path in files)
    return f"Selected context files:\n{listed}\n\nUser prompt:\n{prompt}"


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


def _approval_display_fields(approval: dict[str, Any], session: dict[str, Any]) -> dict[str, Any]:
    pending = session.get("pending_approval") if isinstance(session, dict) else None
    params = pending.get("params", {}) if isinstance(pending, dict) else {}
    command = params.get("command") if isinstance(params, dict) else None
    path = params.get("path") if isinstance(params, dict) else None
    if isinstance(command, list):
        target = " ".join(str(part) for part in command)
        action_kind = "shell"
    elif path:
        target = str(path)
        action_kind = "file"
    else:
        target = (
            str(params.get("url", approval.get("tool_id", ""))) if isinstance(params, dict) else ""
        )
        action_kind = "tool"
    return {
        **approval,
        "params": params,
        "target": target,
        "action_kind": action_kind,
    }


def _session_view_response(view: Any) -> dict[str, Any]:
    payload = _json_model(view)
    session = cast(dict[str, Any], payload.get("session", {}))
    payload["approvals"] = [
        _approval_display_fields(cast(dict[str, Any], approval), session)
        for approval in payload.get("approvals", [])
    ]
    return payload


def _read_ui_config() -> dict[str, Any]:
    config = ui_config.load_config()
    core = config.get("core", {})
    ui = config.get("ui", {})
    onboarding = config.get("onboarding", {})
    return {
        "onboarding_complete": bool(onboarding.get("complete", False)),
        "onboarding_dismissed": bool(onboarding.get("dismissed", False)),
        "default_workspace": str(core.get("default_workspace", ".")),
        "theme": str(ui.get("theme", "dark")),
    }


def _write_ui_config(patch: UiConfigPatch) -> dict[str, Any]:
    current = ui_config.load_config()
    core = dict(current.get("core", {}))
    ui = dict(current.get("ui", {}))
    onboarding = dict(current.get("onboarding", {}))

    if patch.theme is not None:
        if patch.theme not in {"dark", "light", "high_contrast"}:
            raise HTTPException(
                status_code=400, detail="Theme must be dark, light, or high_contrast"
            )
        ui["theme"] = patch.theme
    if patch.default_workspace is not None:
        workspace = Path(patch.default_workspace).expanduser()
        if not workspace.exists() or not workspace.is_dir():
            raise HTTPException(status_code=400, detail=f"Workspace does not exist: {workspace}")
        core["default_workspace"] = str(workspace)
    if patch.onboarding_complete is not None:
        onboarding["complete"] = patch.onboarding_complete
    if patch.onboarding_dismissed is not None:
        onboarding["dismissed"] = patch.onboarding_dismissed

    updated = {**current, "core": core, "ui": ui, "onboarding": onboarding}
    ui_config.save_config(updated)
    return _read_ui_config()


def _detect_ollama() -> dict[str, Any]:
    result: dict[str, Any] = {
        "kind": "ollama",
        "display_name": "Ollama Local",
        "detected": False,
        "endpoint": "http://localhost:11434/v1",
        "models": [],
    }
    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=1.0) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return result

    models = payload.get("models", []) if isinstance(payload, dict) else []
    names = [
        str(item.get("name")) for item in models if isinstance(item, dict) and item.get("name")
    ]
    return {**result, "detected": True, "models": names}


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

    @app.get("/api/config")
    def api_get_config() -> dict[str, Any]:
        return _read_ui_config()

    @app.patch("/api/config")
    def api_patch_config(body: UiConfigPatch) -> dict[str, Any]:
        return _write_ui_config(body)

    @app.post("/api/onboarding/complete")
    def api_complete_onboarding(body: OnboardingCompleteRequest) -> dict[str, Any]:
        return _write_ui_config(
            UiConfigPatch(
                onboarding_complete=True,
                onboarding_dismissed=False,
                default_workspace=body.default_workspace,
            )
        )

    @app.get("/api/onboarding/local-providers")
    def api_local_providers() -> list[dict[str, Any]]:
        return [_detect_ollama()]

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
        return _session_view_response(
            get_session_view(_workspace(workspace_path, workspace_root), session_id)
        )

    @app.post("/api/coder/sessions/{session_id}/messages")
    def api_post_message(
        session_id: str, body: CoderSessionMessageRequest, workspace_root: str | None = None
    ) -> dict[str, Any]:
        return _json_model(
            post_message(
                _workspace(workspace_path, workspace_root),
                session_id,
                _prompt_with_context(body.prompt, body.context_files),
            )
        )

    @app.post("/api/coder/sessions/{session_id}/messages/stream")
    async def api_post_message_stream(
        session_id: str, body: CoderSessionMessageRequest, workspace_root: str | None = None
    ) -> StreamingResponse:
        workspace = _workspace(workspace_path, workspace_root)

        async def events() -> AsyncIterator[str]:
            yield _sse("start", {"session_id": session_id})
            task = asyncio.create_task(
                asyncio.to_thread(
                    post_message,
                    workspace,
                    session_id,
                    _prompt_with_context(body.prompt, body.context_files),
                )
            )
            sent_event_count = 0
            sent_text_length = 0
            try:
                while not task.done():
                    view = get_session_view(workspace, session_id)
                    event_payloads = [event.model_dump(mode="json") for event in view.events]
                    for payload in event_payloads[sent_event_count:]:
                        yield _sse("activity", {"session_id": session_id, "event": payload})
                    sent_event_count = len(event_payloads)
                    text = view.session.current_assistant_message or ""
                    if len(text) > sent_text_length:
                        yield _sse(
                            "token",
                            {
                                "session_id": session_id,
                                "token": text[sent_text_length:],
                            },
                        )
                        sent_text_length = len(text)
                    await asyncio.sleep(0.2)
                session = await task
            except Exception as exc:
                yield _sse(
                    "error",
                    {
                        "session_id": session_id,
                        "error": str(exc),
                        "error_type": type(exc).__name__,
                    },
                )
                return

            final_text = session.current_assistant_message or ""
            if len(final_text) > sent_text_length:
                remaining = final_text[sent_text_length:]
                for chunk in _chunk_text(remaining):
                    yield _sse("token", {"session_id": session_id, "token": chunk})
                    await asyncio.sleep(0)

            yield _sse(
                "done",
                {
                    "session_id": session_id,
                    "session": session.model_dump(mode="json"),
                },
            )

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
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

    @app.get("/api/coder/files/search")
    def api_file_search(
        q: str = "", limit: int = 50, workspace_root: str | None = None
    ) -> list[dict[str, Any]]:
        bounded_limit = max(1, min(limit, 200))
        return _search_file_tree(_workspace(workspace_path, workspace_root), q, bounded_limit)

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

    @app.get("/api/providers/wizard-templates")
    def api_wizard_templates() -> list[dict[str, Any]]:
        return cast(list[dict[str, Any]], get_templates(include_experimental=True))

    @app.post("/api/providers/profiles")
    def api_create_provider_profile(body: dict[str, Any]) -> dict[str, Any]:
        profile = create_profile(
            name=body["name"],
            provider_kind=body["provider_kind"],
            provider_id=body["provider_id"],
            model_id=body["model_id"],
            fields=body.get("fields", {}),
            set_as_default=body.get("set_as_default", False),
        )
        return {"ok": True, "profile": profile.model_dump()}

    @app.delete("/api/providers/profiles/{name}")
    def api_delete_provider_profile(name: str) -> dict[str, Any]:
        delete_profile(name)
        return {"ok": True}

    @app.post("/api/providers/test")
    def api_test_provider(body: dict[str, Any]) -> dict[str, Any]:
        return verify_provider_connection(
            provider_kind=body["provider_kind"],
            fields=body.get("fields", {}),
            model_id=body.get("model_id", ""),
        )

    @app.get("/api/coder/sessions/{session_id}/usage")
    def api_session_usage(session_id: str, workspace_root: str | None = None) -> dict[str, Any]:
        return aggregate_session_usage(_workspace(workspace_path, workspace_root), session_id)

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
