from __future__ import annotations

# ruff: noqa: SIM905
import asyncio
import importlib
import json
import secrets
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.responses import Response as StarletteResponse

from agentheim_code import __version__
from agentheim_code import config as ui_config
from agentheim_code.http_context import MAX_JSON_BODY_BYTES, REQUEST_ID_HEADER, new_request_id
from agentheim_code.lifecycle import build_lifespan
from agentheim_code.routes import coder, files, providers
from agentheim_code.structured_errors import E_REQUEST_TOO_LARGE, E_UNAUTHORIZED
from workflows.coder import runtime as coder_runtime

_ROUTE_CODER_EXPORTS = set(  # noqa: SIM905 - compact compat export table keeps backend slim.
    "ApprovalDisplayResponse CoderQueueRequest CoderSessionCreateRequest "
    "CoderSessionMessageRequest CoderSessionModeRequest CoderSessionModelRequest "
    "CoderSessionTrustModeRequest CommandRegistryEntry CommandResultResponse "
    "ContextPreviewResponse ContextValidateRequest ContextValidationResponse "
    "ModeCatalogResponse ModeDescriptorResponse SessionDiffResponse SessionEventResponse "
    "SessionModelSelectionResponse SessionResponse SessionViewResponse TranscriptEntryResponse "
    "TrustModeDescriptorResponse UsageBreakdownResponse UsageResponse _approval_display_fields "
    "_chunk_text _command_result_response _mode_catalog_response _model_selection_response "
    "_prompt_with_context _session_diff_response _session_event_response _session_response "
    "_session_view_response _sse _transcript_entry_response _usage_response".split()  # noqa: SIM905
)
_ROUTE_FILE_EXPORTS = {
    "FileBrowseResponse",
    "FileEntryResponse",
    "_safe_preview_path",
    "_search_file_tree",
}
_ROUTE_PROVIDER_EXPORTS = {"_redact_account", "_redact_binding"}
_RUNTIME_EXPORTS = set(  # noqa: SIM905 - compact compat export table keeps backend slim.
    "_save_session approve_request available_commands browse_file_tree cancel_session "
    "create_session get_session get_session_view list_file_tree list_model_options "
    "list_sessions post_message queue_message resume_session set_session_mode "
    "update_session_model update_session_trust_mode".split()  # noqa: SIM905
)
_OTHER_EXPORTS = {
    "build_context_bundle": ("agentheim_code.context_bundle", "build_context_bundle"),
    "list_provider_templates": ("config.config", "list_provider_templates"),
    "load_health": ("agentheim_code.provider_health", "load_health"),
    "load_profiles_document": ("config.config", "load_profiles_document"),
    "validate_account_draft": ("agentheim_code.provider_management", "validate_account_draft"),
}


def __getattr__(name: str) -> Any:
    if name in _ROUTE_CODER_EXPORTS:
        return getattr(coder, name)
    if name in _ROUTE_FILE_EXPORTS:
        return getattr(files, name)
    if name in _ROUTE_PROVIDER_EXPORTS:
        return getattr(providers, name)
    if name in _RUNTIME_EXPORTS:
        return getattr(coder_runtime, name)
    if name in _OTHER_EXPORTS:
        module_name, attr = _OTHER_EXPORTS[name]
        return getattr(importlib.import_module(module_name), attr)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


class UiConfigPatch(BaseModel):
    onboarding_complete: bool | None = None
    onboarding_dismissed: bool | None = None
    default_workspace: str | None = None
    theme: str | None = None


class OnboardingCompleteRequest(BaseModel):
    default_workspace: str | None = None


class HealthResponse(BaseModel):
    status: str
    version: str
    workspace: str


class UiConfigResponse(BaseModel):
    onboarding_complete: bool
    onboarding_dismissed: bool
    default_workspace: str
    theme: Literal["dark", "light", "high_contrast"]


class LocalProviderResponse(BaseModel):
    kind: str
    display_name: str
    detected: bool
    endpoint: str
    models: list[str] = Field(default_factory=list)


class ExchangeRequest(BaseModel):
    nonce: str


def _version() -> str:
    return str(__version__)


def _json_model(model: Any) -> dict[str, Any]:
    return cast(dict[str, Any], model.model_dump(mode="json"))


def _ui_config_response(payload: dict[str, Any]) -> UiConfigResponse:
    return UiConfigResponse(
        onboarding_complete=bool(payload.get("onboarding_complete", False)),
        onboarding_dismissed=bool(payload.get("onboarding_dismissed", False)),
        default_workspace=str(payload.get("default_workspace", ".")),
        theme=cast(
            Literal["dark", "light", "high_contrast"],
            payload.get("theme", "dark"),
        ),
    )


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

    app = FastAPI(title="Agentheim Code", version=_version(), lifespan=build_lifespan())
    app.state.workspace_path = workspace_path
    app.state.session_secret = secrets.token_urlsafe(32)
    app.state.csrf_token = secrets.token_urlsafe(32)
    app.state.launch_nonce = None
    app.state.launch_nonce_expires = None

    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=(
            r"^(http://(127\.0\.0\.1|localhost)(:\d+)?|"
            r"https?://tauri\.localhost|tauri://localhost)$"
        ),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def _set_auth_cookie(response: Any) -> None:
        response.set_cookie(
            key="agentheim_session",
            value=app.state.session_secret,
            httponly=True,
            samesite="strict",
            path="/api",
            max_age=86400,
        )

    def _auth_ok(request: Request) -> bool:
        if not request.url.path.startswith("/api/"):
            return True
        cookie = request.cookies.get("agentheim_session")
        csrf = request.headers.get("x-csrf-token")
        return bool(cookie == app.state.session_secret and csrf == app.state.csrf_token)

    @app.middleware("http")
    async def attach_request_context(request: Request, call_next: Any) -> Any:
        request_id = request.headers.get(REQUEST_ID_HEADER, new_request_id())
        request.state.request_id = request_id
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                if int(content_length) > MAX_JSON_BODY_BYTES:
                    error_detail = {**E_REQUEST_TOO_LARGE.to_dict(), "request_id": request_id}
                    return JSONResponse(
                        status_code=413,
                        content={"detail": error_detail},
                        headers={REQUEST_ID_HEADER: request_id},
                    )
            except ValueError:
                pass
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response

    @app.middleware("http")
    async def auth_middleware(request: Request, call_next: Any) -> Any:
        if request.url.path == "/api/auth/exchange":
            return await call_next(request)
        if not _auth_ok(request):
            request_id = getattr(request.state, "request_id", new_request_id())
            return JSONResponse(
                status_code=401,
                content={"detail": {**E_UNAUTHORIZED.to_dict(), "request_id": request_id}},
                headers={REQUEST_ID_HEADER: request_id},
            )
        return await call_next(request)

    @app.get("/api/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status="ok", version=_version(), workspace=str(workspace_path))

    @app.get("/api/config", response_model=UiConfigResponse)
    def api_get_config() -> UiConfigResponse:
        return _ui_config_response(_read_ui_config())

    @app.patch("/api/config", response_model=UiConfigResponse)
    def api_patch_config(body: UiConfigPatch) -> UiConfigResponse:
        return _ui_config_response(_write_ui_config(body))

    @app.post("/api/onboarding/complete", response_model=UiConfigResponse)
    def api_complete_onboarding(body: OnboardingCompleteRequest) -> UiConfigResponse:
        return _ui_config_response(
            _write_ui_config(
                UiConfigPatch(
                    onboarding_complete=True,
                    onboarding_dismissed=False,
                    default_workspace=body.default_workspace,
                )
            )
        )

    @app.get("/api/onboarding/local-providers", response_model=list[LocalProviderResponse])
    def api_local_providers() -> list[LocalProviderResponse]:
        return [LocalProviderResponse.model_validate(_detect_ollama())]

    app.include_router(coder.router)
    app.include_router(files.router)
    app.include_router(providers.router)

    @app.websocket("/api/coder/sessions/{session_id}/events")
    async def api_events(websocket: WebSocket, session_id: str) -> None:
        if not _origin_allowed(websocket.headers.get("origin")):
            await websocket.close(code=1008)
            return
        await websocket.accept()
        previous_count = -1
        try:
            while True:
                view = coder_runtime.get_session_view(workspace_path, session_id)
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
    def coder_index() -> Any:
        if index.exists():
            html = index.read_text(encoding="utf-8")
            if "Agentheim Coder" not in html:
                html = html.replace(
                    '<div id="root"></div>', '<div id="root"></div><!-- Agentheim Coder -->'
                )
            csrf = app.state.csrf_token
            injection = f'<script>window.__AGENTHEIM_CSRF__="{csrf}"</script>'
            if "<head>" in html:
                html = html.replace("<head>", f"<head>{injection}", 1)
            else:
                html = injection + html
            response = HTMLResponse(html)
            _set_auth_cookie(response)
            return response
        return "<!doctype html><title>Agentheim Code</title><h1>Agentheim Code</h1><p>Run npm --prefix apps/web run build to create the UI bundle.</p>"

    @app.post("/api/auth/exchange")
    def api_auth_exchange(payload: ExchangeRequest) -> StarletteResponse:
        expected = app.state.launch_nonce
        expires = app.state.launch_nonce_expires
        if (
            expected is None
            or expires is None
            or datetime.now(UTC) > expires
            or payload.nonce != expected
        ):
            raise HTTPException(status_code=401, detail="Invalid or expired launch nonce.")
        app.state.launch_nonce = None
        app.state.launch_nonce_expires = None
        resp = JSONResponse({"csrf_token": app.state.csrf_token})
        _set_auth_cookie(resp)
        return resp

    if dist.exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    return app
