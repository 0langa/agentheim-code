from __future__ import annotations

import asyncio
import json
import urllib.request
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, Literal, Never, cast

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from agentheim_code import __version__
from agentheim_code import config as ui_config
from agentheim_code.context_bundle import build_context_bundle
from agentheim_code.http_context import MAX_JSON_BODY_BYTES, REQUEST_ID_HEADER, new_request_id
from agentheim_code.lifecycle import build_lifespan
from agentheim_code.provider_capabilities import get_capabilities
from agentheim_code.provider_discovery import list_remote_models
from agentheim_code.provider_health import load_health
from agentheim_code.provider_management import (
    ValidationError,
    add_account,
    add_model,
    assign_role,
    create_profile,
    delete_account,
    delete_model,
    delete_profile,
    duplicate_profile,
    export_profile,
    get_profile,
    import_discovered_models,
    import_profile,
    list_profiles,
    rotate_secret,
    set_default_model,
    set_default_profile,
    test_account,
    update_account,
    update_model,
    update_profile,
    validate_account_draft,
)
from agentheim_code.provider_wizard import (
    create_profile as wizard_create_profile,
)
from agentheim_code.provider_wizard import (
    delete_profile as wizard_delete_profile,
)
from agentheim_code.provider_wizard import (
    get_templates,
    verify_provider_connection,
)
from agentheim_code.structured_errors import (
    E_CANCELLATION_FAILED,
    E_CONTEXT_VALIDATION_FAILED,
    E_REQUEST_TOO_LARGE,
    E_RESUME_INVALID_STATE,
    E_SESSION_LOCKED,
    E_SESSION_NOT_FOUND,
    from_exception,
)
from agentheim_code.usage_api import aggregate_session_usage
from config.config import (
    ModelBinding,
    ProviderAccount,
    list_provider_templates,
    load_profiles_document,
    save_profiles_document,
)
from core.run_view import RunView, list_run_views
from workflows.coder.models import (
    CoderApproval,
    CoderCommandResult,
    CoderDiff,
    CoderEvent,
    CoderMessage,
    CoderModelSelection,
    CoderSession,
    CoderSessionView,
)
from workflows.coder.runtime import (
    approve_request,
    available_commands,
    browse_file_tree,
    cancel_session,
    create_session,
    get_session,
    get_session_view,
    list_file_tree,
    list_model_options,
    list_sessions,
    post_message,
    queue_message,
    resume_session,
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
    use_context_bundle: bool = True


class ContextValidateRequest(BaseModel):
    paths: list[str] = Field(default_factory=list)


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


class FileEntryResponse(BaseModel):
    path: str
    type: str


class FileBrowseResponse(BaseModel):
    items: list[FileEntryResponse]
    next_offset: int | None = None
    has_more: bool
    query: str = ""


class CommandRegistryEntry(BaseModel):
    id: str
    label: str
    cli: str
    surface: str


class TranscriptEntryResponse(BaseModel):
    role: str
    content: str
    timestamp: str


class SessionModelSelectionResponse(BaseModel):
    profile: str = "auto"
    provider: str = "auto"
    model: str = "auto"
    actual_profile: str | None = None
    actual_provider: str | None = None
    actual_model: str | None = None


class SessionResponse(BaseModel):
    session_id: str
    status: str
    mode: str
    trust_mode: str
    workspace_root: str
    model_selection: SessionModelSelectionResponse
    transcript: list[TranscriptEntryResponse] = Field(default_factory=list)
    current_user_prompt: str | None = None
    current_assistant_message: str | None = None
    changed_files: list[str] = Field(default_factory=list)
    repair_attempts: int = 0
    last_failure_reason: str = ""
    last_verification_command: list[str] = Field(default_factory=list)
    last_verification_exit_code: int | None = None


class SessionEventResponse(BaseModel):
    event_id: str
    type: str
    message: str
    timestamp: str
    payload: dict[str, str] = Field(default_factory=dict)


class CommandResultResponse(BaseModel):
    command: list[str] = Field(default_factory=list)
    exit_code: int | None = None
    status: str
    stdout: str = ""
    stderr: str = ""
    timestamp: str


class SessionDiffResponse(BaseModel):
    path: str
    status: str
    before: str
    after: str
    timestamp: str


class ApprovalDisplayResponse(BaseModel):
    request_id: str
    tool_id: str
    risk_level: str
    reason: str
    status: str
    params: dict[str, Any] = Field(default_factory=dict)
    target: str = ""
    action_kind: str = "tool"


class SessionViewResponse(BaseModel):
    session: SessionResponse
    queued_prompts: list[str] = Field(default_factory=list)
    available_commands: list[str] = Field(default_factory=list)
    events: list[SessionEventResponse] = Field(default_factory=list)
    approvals: list[ApprovalDisplayResponse] = Field(default_factory=list)
    diffs: list[SessionDiffResponse] = Field(default_factory=list)
    command_results: list[CommandResultResponse] = Field(default_factory=list)
    artifacts: list[str] = Field(default_factory=list)


class ContextPreviewResponse(BaseModel):
    path: str
    status: str
    size: int
    preview: str
    truncation_reason: str
    token_estimate: int


class ContextValidationResponse(BaseModel):
    session_id: str
    items: list[ContextPreviewResponse] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    total_token_estimate: int


class UsageBreakdownResponse(BaseModel):
    sequence: int
    timestamp: str
    model: str | None = None
    provider: str | None = None
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost_usd: float | None = None


class UsageResponse(BaseModel):
    session_id: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost_usd: float | None = None
    calls: int
    breakdown: list[UsageBreakdownResponse] = Field(default_factory=list)


def _utcnow() -> str:
    from datetime import UTC, datetime

    return datetime.now(tz=UTC).isoformat()


def _redact_account(account: ProviderAccount) -> dict[str, Any]:
    d: dict[str, Any] = account.model_dump()
    if account.secret_ref:
        d["secret_ref"] = "***"
    d["has_secret"] = bool(account.secret_ref)
    redacted_headers: dict[str, str] = {}
    for k, v in account.headers.items():
        if any(s in k.lower() for s in ("secret", "key", "token", "password", "credential")):
            redacted_headers[k] = f"{v[:2]}***{v[-2:]}" if len(v) > 4 else "****"
        else:
            redacted_headers[k] = v
    d["headers"] = redacted_headers
    return d


def _redact_binding(binding: ModelBinding) -> dict[str, Any]:
    return cast(dict[str, Any], binding.model_dump())


def _version() -> str:
    return __version__


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


def _transcript_entry_response(message: CoderMessage) -> TranscriptEntryResponse:
    return TranscriptEntryResponse(
        role=message.role,
        content=message.content,
        timestamp=message.created_at,
    )


def _model_selection_response(
    selection: CoderModelSelection,
) -> SessionModelSelectionResponse:
    return SessionModelSelectionResponse(
        profile=selection.profile,
        provider=selection.provider,
        model=selection.model,
        actual_profile=selection.actual_profile,
        actual_provider=selection.actual_provider,
        actual_model=selection.actual_model,
    )


def _session_response(session: CoderSession) -> SessionResponse:
    return SessionResponse(
        session_id=session.session_id,
        status=session.status.value,
        mode=session.mode.value,
        trust_mode=session.trust_mode.value,
        workspace_root=session.workspace_root,
        model_selection=_model_selection_response(session.model_selection),
        transcript=[_transcript_entry_response(entry) for entry in session.transcript],
        current_user_prompt=session.current_user_prompt,
        current_assistant_message=session.current_assistant_message,
        changed_files=session.changed_files,
        repair_attempts=session.repair_attempts,
        last_failure_reason=session.last_failure_reason,
        last_verification_command=session.last_verification_command,
        last_verification_exit_code=session.last_verification_exit_code,
    )


def _session_event_response(event: CoderEvent) -> SessionEventResponse:
    return SessionEventResponse(
        event_id=event.event_id,
        type=event.kind,
        message=event.message,
        timestamp=event.created_at,
        payload=event.details,
    )


def _command_result_response(result: CoderCommandResult) -> CommandResultResponse:
    exit_code = result.exit_code
    status = "ok" if exit_code in {0, None} else "failed"
    return CommandResultResponse(
        command=result.command,
        exit_code=exit_code,
        status=status,
        stdout=result.stdout,
        stderr=result.stderr,
        timestamp=result.created_at,
    )


def _session_diff_response(diff: CoderDiff) -> SessionDiffResponse:
    return SessionDiffResponse(
        path=diff.path,
        status=diff.status,
        before=diff.before,
        after=diff.after,
        timestamp=diff.created_at,
    )


def _approval_response(
    approval: CoderApproval,
    session: CoderSession,
) -> ApprovalDisplayResponse:
    display = _approval_display_fields(
        approval.model_dump(mode="json"),
        session.model_dump(mode="json"),
    )
    return ApprovalDisplayResponse(
        request_id=approval.request_id,
        tool_id=approval.tool_id,
        risk_level=approval.risk_level,
        reason=approval.reason,
        status=approval.status,
        params=cast(dict[str, Any], display.get("params", {})),
        target=str(display.get("target", "")),
        action_kind=str(display.get("action_kind", "tool")),
    )


def _session_view_response(view: CoderSessionView) -> SessionViewResponse:
    return SessionViewResponse(
        session=_session_response(view.session),
        queued_prompts=view.queued_prompts,
        available_commands=view.available_commands,
        events=[_session_event_response(event) for event in view.events],
        approvals=[_approval_response(approval, view.session) for approval in view.approvals],
        diffs=[_session_diff_response(diff) for diff in view.diffs],
        command_results=[_command_result_response(result) for result in view.command_results],
        artifacts=view.artifacts,
    )


def _usage_response(payload: dict[str, Any]) -> UsageResponse:
    return UsageResponse(
        session_id=str(payload.get("session_id", "")),
        input_tokens=int(payload.get("input_tokens", 0) or 0),
        output_tokens=int(payload.get("output_tokens", 0) or 0),
        total_tokens=int(payload.get("total_tokens", 0) or 0),
        estimated_cost_usd=cast(float | None, payload.get("estimated_cost_usd")),
        calls=int(payload.get("calls", 0) or 0),
        breakdown=[
            UsageBreakdownResponse.model_validate(item)
            for item in cast(list[dict[str, Any]], payload.get("breakdown", []))
        ],
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


def _sse(event: str, data: dict[str, Any]) -> str:
    payload = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


def _chunk_text(text: str, size: int = 24) -> list[str]:
    if not text:
        return []
    return [text[index : index + size] for index in range(0, len(text), size)]


def _prompt_with_context(
    prompt: str, context_files: list[str], workspace: Path, use_bundle: bool = True
) -> tuple[str, list[str]]:
    """Build prompt with context. Returns (prompt, error_messages).

    If use_bundle is True, reads file contents into explicit context blocks.
    Otherwise falls back to legacy path-only listing.
    """
    files = [path.strip() for path in context_files if path.strip()]
    if not files:
        return prompt, []

    if not use_bundle:
        listed = "\n".join(f"- {path}" for path in files)
        return f"Selected context files:\n{listed}\n\nUser prompt:\n{prompt}", []

    bundle = build_context_bundle(workspace, files)
    block = bundle.to_prompt_block()
    errors = bundle.errors
    if block:
        return f"{block}\n\nUser prompt:\n{prompt}", errors
    return prompt, errors


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

    @app.get("/api/coder/sessions", response_model=list[SessionResponse])
    def api_list_sessions(workspace_root: str | None = None) -> list[SessionResponse]:
        return [
            _session_response(session)
            for session in list_sessions(_workspace(workspace_path, workspace_root))
        ]

    @app.post("/api/coder/sessions", response_model=SessionResponse)
    def api_create_session(body: CoderSessionCreateRequest) -> SessionResponse:
        session = create_session(
            _workspace(workspace_path, body.workspace_root),
            trust_mode=body.trust_mode,
            mode=body.mode,
            profile=body.profile,
            provider=body.provider,
            model=body.model,
        )
        return _session_response(session)

    @app.get("/api/coder/sessions/{session_id}", response_model=SessionResponse)
    def api_get_session(session_id: str, workspace_root: str | None = None) -> SessionResponse:
        try:
            return _session_response(
                get_session(_workspace(workspace_path, workspace_root), session_id)
            )
        except Exception as exc:
            if "not found" in str(exc).lower():
                raise HTTPException(status_code=404, detail=E_SESSION_NOT_FOUND.to_dict()) from exc
            raise HTTPException(status_code=500, detail=from_exception(exc).to_dict()) from exc

    @app.get("/api/coder/sessions/{session_id}/view", response_model=SessionViewResponse)
    def api_get_session_view(
        session_id: str, workspace_root: str | None = None
    ) -> SessionViewResponse:
        return _session_view_response(
            get_session_view(_workspace(workspace_path, workspace_root), session_id)
        )

    @app.post("/api/coder/sessions/{session_id}/messages", response_model=SessionResponse)
    def api_post_message(
        session_id: str,
        request: Request,
        body: CoderSessionMessageRequest,
        workspace_root: str | None = None,
    ) -> SessionResponse:
        request_id = str(getattr(request.state, "request_id", ""))
        if len(body.prompt.encode("utf-8")) > MAX_JSON_BODY_BYTES:
            raise HTTPException(status_code=413, detail=E_REQUEST_TOO_LARGE.to_dict())
        workspace = _workspace(workspace_path, workspace_root)
        prompt, errors = _prompt_with_context(
            body.prompt, body.context_files, workspace, use_bundle=body.use_context_bundle
        )
        if errors:
            raise HTTPException(
                status_code=400,
                detail={
                    **E_CONTEXT_VALIDATION_FAILED.to_dict(),
                    "context_errors": errors,
                },
            )
        try:
            return _session_response(
                post_message(workspace, session_id, prompt, request_id=request_id)
            )
        except ValueError as exc:
            if "already running" in str(exc).lower():
                raise HTTPException(status_code=409, detail=E_SESSION_LOCKED.to_dict()) from exc
            raise HTTPException(status_code=400, detail=from_exception(exc).to_dict()) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=from_exception(exc).to_dict()) from exc

    @app.post("/api/coder/sessions/{session_id}/messages/stream")
    async def api_post_message_stream(
        session_id: str,
        request: Request,
        body: CoderSessionMessageRequest,
        workspace_root: str | None = None,
    ) -> StreamingResponse:
        request_id = str(getattr(request.state, "request_id", ""))
        if len(body.prompt.encode("utf-8")) > MAX_JSON_BODY_BYTES:
            raise HTTPException(status_code=413, detail=E_REQUEST_TOO_LARGE.to_dict())
        workspace = _workspace(workspace_path, workspace_root)
        prompt, errors = _prompt_with_context(
            body.prompt, body.context_files, workspace, use_bundle=body.use_context_bundle
        )

        async def events() -> AsyncIterator[str]:
            yield _sse("start", {"session_id": session_id})
            if errors:
                yield _sse(
                    "error",
                    {
                        "session_id": session_id,
                        "structured_error": {
                            **E_CONTEXT_VALIDATION_FAILED.to_dict(),
                            "context_errors": errors,
                        },
                    },
                )
                return

            task = asyncio.create_task(
                asyncio.to_thread(
                    post_message,
                    workspace,
                    session_id,
                    prompt,
                    request_id=request_id,
                )
            )
            sent_event_count = 0
            sent_text_length = 0
            try:
                while not task.done():
                    try:
                        view = get_session_view(workspace, session_id)
                    except Exception:
                        view = None
                    if view is not None:
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
                        "structured_error": from_exception(exc).to_dict(),
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

    @app.post("/api/coder/sessions/{session_id}/queue", response_model=SessionResponse)
    def api_queue_message(
        session_id: str, body: CoderQueueRequest, workspace_root: str | None = None
    ) -> SessionResponse:
        if len(body.prompt.encode("utf-8")) > MAX_JSON_BODY_BYTES:
            raise HTTPException(status_code=413, detail=E_REQUEST_TOO_LARGE.to_dict())
        return _session_response(
            queue_message(_workspace(workspace_path, workspace_root), session_id, body.prompt)
        )

    @app.patch("/api/coder/sessions/{session_id}/model", response_model=SessionResponse)
    def api_update_model(
        session_id: str, body: CoderSessionModelRequest, workspace_root: str | None = None
    ) -> SessionResponse:
        return _session_response(
            update_session_model(
                _workspace(workspace_path, workspace_root),
                session_id,
                profile=body.profile,
                provider=body.provider,
                model=body.model,
            )
        )

    @app.patch("/api/coder/sessions/{session_id}/mode", response_model=SessionResponse)
    def api_update_mode(
        session_id: str, body: CoderSessionModeRequest, workspace_root: str | None = None
    ) -> SessionResponse:
        return _session_response(
            set_session_mode(_workspace(workspace_path, workspace_root), session_id, body.mode)
        )

    @app.post("/api/coder/sessions/{session_id}/cancel", response_model=SessionResponse)
    def api_cancel_session(
        session_id: str,
        request: Request,
        workspace_root: str | None = None,
    ) -> SessionResponse:
        request_id = str(getattr(request.state, "request_id", ""))
        try:
            return _session_response(
                cancel_session(
                    _workspace(workspace_path, workspace_root), session_id, request_id=request_id
                )
            )
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail={
                    **E_CANCELLATION_FAILED.to_dict(),
                    "original_error": str(exc),
                },
            ) from exc

    @app.post("/api/coder/sessions/{session_id}/resume", response_model=SessionResponse)
    def api_resume_session(
        session_id: str,
        request: Request,
        workspace_root: str | None = None,
    ) -> SessionResponse:
        request_id = str(getattr(request.state, "request_id", ""))
        workspace = _workspace(workspace_path, workspace_root)
        try:
            session = resume_session(workspace, session_id, request_id=request_id)
        except ValueError as exc:
            if "not found" in str(exc).lower():
                raise HTTPException(status_code=404, detail=E_SESSION_NOT_FOUND.to_dict()) from exc
            if (
                "not in a resumable state" in str(exc).lower()
                or "already running" in str(exc).lower()
            ):
                raise HTTPException(
                    status_code=409, detail=E_RESUME_INVALID_STATE.to_dict()
                ) from exc
            raise HTTPException(status_code=400, detail=from_exception(exc).to_dict()) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=from_exception(exc).to_dict()) from exc
        return _session_response(session)

    @app.post(
        "/api/coder/sessions/{session_id}/context/validate",
        response_model=ContextValidationResponse,
    )
    def api_validate_context(
        session_id: str, body: ContextValidateRequest, workspace_root: str | None = None
    ) -> ContextValidationResponse:
        workspace = _workspace(workspace_path, workspace_root)
        bundle = build_context_bundle(workspace, body.paths)
        return ContextValidationResponse(
            session_id=session_id,
            items=[
                ContextPreviewResponse.model_validate(item) for item in bundle.to_preview_payload()
            ],
            errors=bundle.errors,
            total_token_estimate=bundle.total_token_estimate(),
        )

    @app.post(
        "/api/coder/sessions/{session_id}/approvals/{request_id}/grant",
        response_model=SessionResponse,
    )
    def api_grant_approval(
        session_id: str,
        request_id: str,
        req: Request,
        workspace_root: str | None = None,
    ) -> SessionResponse:
        caller_request_id = str(getattr(req.state, "request_id", ""))
        return _session_response(
            approve_request(
                _workspace(workspace_path, workspace_root),
                session_id,
                request_id,
                grant=True,
                caller_request_id=caller_request_id,
            )
        )

    @app.post(
        "/api/coder/sessions/{session_id}/approvals/{request_id}/deny",
        response_model=SessionResponse,
    )
    def api_deny_approval(
        session_id: str,
        request_id: str,
        req: Request,
        workspace_root: str | None = None,
    ) -> SessionResponse:
        caller_request_id = str(getattr(req.state, "request_id", ""))
        return _session_response(
            approve_request(
                _workspace(workspace_path, workspace_root),
                session_id,
                request_id,
                grant=False,
                caller_request_id=caller_request_id,
            )
        )

    @app.get("/api/coder/sessions/{session_id}/diff", response_model=list[SessionDiffResponse])
    def api_diff(session_id: str, workspace_root: str | None = None) -> list[SessionDiffResponse]:
        return [
            _session_diff_response(diff)
            for diff in get_session_view(
                _workspace(workspace_path, workspace_root), session_id
            ).diffs
        ]

    @app.get("/api/coder/files", response_model=list[FileEntryResponse])
    def api_files(workspace_root: str | None = None) -> list[FileEntryResponse]:
        return cast(
            list[FileEntryResponse],
            [
                FileEntryResponse.model_validate(item)
                for item in list_file_tree(_workspace(workspace_path, workspace_root))
            ],
        )

    @app.get("/api/coder/files/browser", response_model=FileBrowseResponse)
    def api_file_browser(
        q: str = "",
        limit: int = 100,
        offset: int = 0,
        workspace_root: str | None = None,
    ) -> FileBrowseResponse:
        bounded_limit = max(1, min(limit, 200))
        bounded_offset = max(offset, 0)
        items, next_offset = browse_file_tree(
            _workspace(workspace_path, workspace_root),
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

    @app.get("/api/coder/files/search", response_model=list[FileEntryResponse])
    def api_file_search(
        q: str = "", limit: int = 50, workspace_root: str | None = None
    ) -> list[FileEntryResponse]:
        bounded_limit = max(1, min(limit, 200))
        return [
            FileEntryResponse.model_validate(item)
            for item in _search_file_tree(
                _workspace(workspace_path, workspace_root), q, bounded_limit
            )
        ]

    @app.get("/api/coder/files/preview")
    def api_file_preview(path: str = "", workspace_root: str | None = None) -> str:
        workspace = _workspace(workspace_path, workspace_root)
        if not path:
            raise HTTPException(status_code=400, detail="Path is required.")
        if ".." in path:
            raise HTTPException(status_code=400, detail="Invalid path.")
        target = workspace / path
        try:
            target.resolve().relative_to(workspace.resolve())
        except ValueError:
            raise HTTPException(status_code=400, detail="Path is outside workspace.") from None
        if not target.exists() or not target.is_file():
            raise HTTPException(status_code=404, detail="File not found.")
        try:
            return target.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Could not read file: {exc}") from exc

    @app.get("/api/coder/runs", response_model=list[RunView])
    def api_runs(workspace_root: str | None = None) -> list[RunView]:
        return cast(list[RunView], list_run_views(_workspace(workspace_path, workspace_root)))

    @app.get("/api/coder/models")
    def api_models() -> dict[str, Any]:
        options = cast(dict[str, Any], list_model_options())
        health = load_health()
        for profile in options.get("profiles", []):
            for model in profile.get("models", []):
                provider_id = model.get("provider", "")
                key = f"{profile['name']}/{provider_id}"
                h = health.get(key)
                if h:
                    model["health"] = h.to_dict()
                else:
                    model["health"] = None
                # Basic recommendation metadata
                model["recommendations"] = {
                    "planner_suitable": "json" in model.get("capabilities", []),
                    "context_window_hint": "unknown",
                    "cost_support": True,
                }
        return options

    @app.get("/api/providers/health")
    def api_provider_health() -> dict[str, Any]:
        health = load_health()
        return {"health": {k: v.to_dict() for k, v in health.items()}}

    @app.get("/api/coder/commands", response_model=list[CommandRegistryEntry])
    def api_commands() -> list[CommandRegistryEntry]:
        return [CommandRegistryEntry.model_validate(item) for item in available_commands()]

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
        profile = wizard_create_profile(
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
        wizard_delete_profile(name)
        return {"ok": True}

    @app.post("/api/providers/test")
    def api_test_provider(body: dict[str, Any]) -> dict[str, Any]:
        return verify_provider_connection(
            provider_kind=body["provider_kind"],
            fields=body.get("fields", {}),
            model_id=body.get("model_id", ""),
        )

    # ------------------------------------------------------------------
    # Provider Management API (new)
    # ------------------------------------------------------------------

    def _management_error(exc: ValidationError) -> Never:
        raise HTTPException(
            status_code=400,
            detail=exc.to_dict(),
            headers={REQUEST_ID_HEADER: new_request_id()},
        )

    @app.get("/api/provider-management/profiles")
    def api_mgmt_list_profiles() -> dict[str, Any]:
        return list_profiles()

    @app.post("/api/provider-management/profiles")
    def api_mgmt_create_profile(body: dict[str, Any]) -> dict[str, Any]:
        try:
            profile = create_profile(
                name=body["name"],
                set_as_default=body.get("set_as_default", False),
            )
            return {"ok": True, "profile": {"name": profile.name}}
        except ValidationError as exc:
            return _management_error(exc)

    @app.get("/api/provider-management/profiles/{profile_name}")
    def api_mgmt_get_profile(profile_name: str) -> dict[str, Any]:
        try:
            return {"ok": True, "profile": get_profile(profile_name)}
        except ValidationError as exc:
            return _management_error(exc)

    @app.patch("/api/provider-management/profiles/{profile_name}")
    def api_mgmt_patch_profile(profile_name: str, body: dict[str, Any]) -> dict[str, Any]:
        try:
            profile = update_profile(profile_name, body)
            return {"ok": True, "profile": {"name": profile.name}}
        except ValidationError as exc:
            return _management_error(exc)

    @app.delete("/api/provider-management/profiles/{profile_name}")
    def api_mgmt_delete_profile(profile_name: str) -> dict[str, Any]:
        try:
            delete_profile(profile_name)
            return {"ok": True}
        except ValidationError as exc:
            return _management_error(exc)

    @app.post("/api/provider-management/profiles/{profile_name}/duplicate")
    def api_mgmt_duplicate_profile(profile_name: str, body: dict[str, Any]) -> dict[str, Any]:
        try:
            target = body.get("target_name", f"{profile_name} copy")
            profile = duplicate_profile(profile_name, target)
            return {"ok": True, "profile": {"name": profile.name}}
        except ValidationError as exc:
            return _management_error(exc)

    @app.post("/api/provider-management/profiles/{profile_name}/set-default")
    def api_mgmt_set_default_profile(profile_name: str) -> dict[str, Any]:
        try:
            set_default_profile(profile_name)
            return {"ok": True}
        except ValidationError as exc:
            return _management_error(exc)

    @app.get("/api/provider-management/profiles/{profile_name}/export")
    def api_mgmt_export_profile(profile_name: str) -> dict[str, Any]:
        try:
            return {"ok": True, "data": export_profile(profile_name)}
        except ValidationError as exc:
            return _management_error(exc)

    @app.post("/api/provider-management/profiles/import")
    def api_mgmt_import_profile(body: dict[str, Any]) -> dict[str, Any]:
        try:
            profile = import_profile(body.get("data", {}), name=body.get("name"))
            return {"ok": True, "profile": {"name": profile.name}}
        except ValidationError as exc:
            return _management_error(exc)

    @app.post("/api/provider-management/profiles/{profile_name}/accounts")
    def api_mgmt_add_account(profile_name: str, body: dict[str, Any]) -> dict[str, Any]:
        try:
            account = ProviderAccount.model_validate(body)
            add_account(profile_name, account)
            return {"ok": True, "account": _redact_account(account)}
        except ValidationError as exc:
            return _management_error(exc)

    @app.patch("/api/provider-management/profiles/{profile_name}/accounts/{account_id}")
    def api_mgmt_patch_account(
        profile_name: str, account_id: str, body: dict[str, Any]
    ) -> dict[str, Any]:
        try:
            account = update_account(profile_name, account_id, body)
            return {"ok": True, "account": _redact_account(account)}
        except ValidationError as exc:
            return _management_error(exc)

    @app.delete("/api/provider-management/profiles/{profile_name}/accounts/{account_id}")
    def api_mgmt_delete_account(
        profile_name: str, account_id: str, cascade: bool = False
    ) -> dict[str, Any]:
        try:
            delete_account(profile_name, account_id, cascade=cascade)
            return {"ok": True}
        except ValidationError as exc:
            return _management_error(exc)

    @app.post("/api/provider-management/profiles/{profile_name}/accounts/{account_id}/test")
    def api_mgmt_test_account(
        profile_name: str, account_id: str, body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        try:
            result = test_account(
                profile_name,
                account_id,
                sample_model=(body or {}).get("model_id", ""),
            )
            return {"ok": True, "result": result}
        except ValidationError as exc:
            return _management_error(exc)

    @app.post("/api/provider-management/accounts/test-draft")
    def api_mgmt_test_account_draft(body: dict[str, Any]) -> dict[str, Any]:
        try:
            if "account" not in body:
                raise ValidationError(
                    "missing_account", "Draft account payload is required.", "account"
                )
            account = ProviderAccount.model_validate(body["account"])
            result = validate_account_draft(
                account,
                secret_value=body.get("secret_value", ""),
                sample_model=body.get("model_id", ""),
                profile_name=body.get("profile_name"),
                existing_account_id=body.get("existing_account_id"),
            )
            return {"ok": True, "result": result}
        except ValidationError as exc:
            return _management_error(exc)

    @app.post(
        "/api/provider-management/profiles/{profile_name}/accounts/{account_id}/rotate-secret"
    )
    def api_mgmt_rotate_secret(
        profile_name: str, account_id: str, body: dict[str, Any]
    ) -> dict[str, Any]:
        try:
            rotate_secret(
                profile_name,
                account_id,
                secret_name=body.get("secret_name", "api_key"),
                secret_value=body.get("secret_value", ""),
            )
            return {"ok": True}
        except ValidationError as exc:
            return _management_error(exc)

    @app.post(
        "/api/provider-management/profiles/{profile_name}/accounts/{account_id}/discover-models"
    )
    def api_mgmt_discover_models(profile_name: str, account_id: str) -> dict[str, Any]:
        try:
            doc = load_profiles_document()
            profile = doc.profiles.get(profile_name)
            if not profile:
                raise ValidationError("profile_not_found", f"Profile '{profile_name}' not found.")
            account = profile.providers.get(account_id)
            if not account:
                raise ValidationError("account_not_found", f"Account '{account_id}' not found.")
            caps = get_capabilities(account.kind)
            if not caps.supports_remote_model_listing:
                return {
                    "ok": True,
                    "supported": False,
                    "discovery_mode": caps.discovery_mode,
                    "models": [],
                }
            discovered = list_remote_models(account)
            # Persist sync timestamp
            account = account.model_copy(update={"last_model_sync_at": _utcnow()})
            profile.providers[account_id] = account
            doc.profiles[profile_name] = profile
            save_profiles_document(doc)
            return {
                "ok": True,
                "supported": True,
                "discovery_mode": caps.discovery_mode,
                "models": [m.to_dict() for m in discovered],
            }
        except ValidationError as exc:
            return _management_error(exc)

    @app.get(
        "/api/provider-management/profiles/{profile_name}/accounts/{account_id}/discovered-models"
    )
    def api_mgmt_get_discovered_models(profile_name: str, account_id: str) -> dict[str, Any]:
        # Re-run discovery without persisting; useful for UI refresh
        return cast(dict[str, Any], api_mgmt_discover_models(profile_name, account_id))

    @app.post("/api/provider-management/profiles/{profile_name}/models")
    def api_mgmt_add_model(profile_name: str, body: dict[str, Any]) -> dict[str, Any]:
        try:
            binding = ModelBinding.model_validate(body)
            add_model(profile_name, binding)
            return {"ok": True, "model": _redact_binding(binding)}
        except ValidationError as exc:
            return _management_error(exc)

    @app.patch("/api/provider-management/profiles/{profile_name}/models/{binding_id}")
    def api_mgmt_patch_model(
        profile_name: str, binding_id: str, body: dict[str, Any]
    ) -> dict[str, Any]:
        try:
            binding = update_model(profile_name, binding_id, body)
            return {"ok": True, "model": _redact_binding(binding)}
        except ValidationError as exc:
            return _management_error(exc)

    @app.delete("/api/provider-management/profiles/{profile_name}/models/{binding_id}")
    def api_mgmt_delete_model(profile_name: str, binding_id: str) -> dict[str, Any]:
        try:
            delete_model(profile_name, binding_id)
            return {"ok": True}
        except ValidationError as exc:
            return _management_error(exc)

    @app.post("/api/provider-management/profiles/{profile_name}/models/{binding_id}/set-default")
    def api_mgmt_set_default_model(profile_name: str, binding_id: str) -> dict[str, Any]:
        try:
            binding = set_default_model(profile_name, binding_id)
            return {"ok": True, "model": _redact_binding(binding)}
        except ValidationError as exc:
            return _management_error(exc)

    @app.post("/api/provider-management/profiles/{profile_name}/models/{binding_id}/assign-role")
    def api_mgmt_assign_role(
        profile_name: str, binding_id: str, body: dict[str, Any]
    ) -> dict[str, Any]:
        try:
            binding = assign_role(profile_name, binding_id, body.get("role", "planner"))
            return {"ok": True, "model": _redact_binding(binding)}
        except ValidationError as exc:
            return _management_error(exc)

    @app.post("/api/provider-management/profiles/{profile_name}/models/import-discovered")
    def api_mgmt_import_discovered(profile_name: str, body: dict[str, Any]) -> dict[str, Any]:
        try:
            imported = import_discovered_models(
                profile_name,
                account_id=body["account_id"],
                models=body.get("models", []),
            )
            return {"ok": True, "models": [_redact_binding(m) for m in imported]}
        except ValidationError as exc:
            return _management_error(exc)

    @app.get("/api/provider-management/templates")
    def api_mgmt_templates() -> list[dict[str, Any]]:
        templates = list_provider_templates(include_experimental=True)
        for t in templates:
            caps = get_capabilities(t["kind"])
            t["capabilities_meta"] = caps.to_dict()
        return cast(list[dict[str, Any]], templates)

    @app.get("/api/provider-management/templates/{template_id}")
    def api_mgmt_template(template_id: str) -> dict[str, Any]:
        templates = {t["kind"]: t for t in list_provider_templates(include_experimental=True)}
        if template_id not in templates:
            raise HTTPException(status_code=404, detail="Template not found")
        t = templates[template_id]
        caps = get_capabilities(template_id)
        return {"ok": True, "template": {**t, "capabilities_meta": caps.to_dict()}}

    @app.get("/api/coder/sessions/{session_id}/usage", response_model=UsageResponse)
    def api_session_usage(session_id: str, workspace_root: str | None = None) -> UsageResponse:
        return _usage_response(
            aggregate_session_usage(_workspace(workspace_path, workspace_root), session_id)
        )

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
