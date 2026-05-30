from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any, cast

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from agentheim_code.http_context import MAX_JSON_BODY_BYTES
from agentheim_code.routes.utils import request_id as get_request_id
from agentheim_code.routes.utils import workspace_from_request
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
from core.run_view import RunView, list_run_views
from workflows.coder.models import (
    TRUST_MODE_DESCRIPTIONS,
    CoderApproval,
    CoderCommandResult,
    CoderDiff,
    CoderEvent,
    CoderMessage,
    CoderMode,
    CoderModelSelection,
    CoderSession,
    CoderSessionView,
    canonical_mode,
    mode_metadata,
)

router = APIRouter(prefix="/api/coder")


def _backend() -> Any:
    from agentheim_code import backend

    return backend


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


class CoderSessionTrustModeRequest(BaseModel):
    trust_mode: str = "ask"


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
    pending_assistant_message: str | None = None
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
    payload: dict[str, Any] = Field(default_factory=dict)


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


class ModeDescriptorResponse(BaseModel):
    id: str
    label: str
    description: str
    edits_expected: bool
    legacy_aliases: list[str] = Field(default_factory=list)


class TrustModeDescriptorResponse(BaseModel):
    id: str
    label: str
    description: str


class ModeCatalogResponse(BaseModel):
    modes: list[ModeDescriptorResponse]
    trust_modes: list[TrustModeDescriptorResponse]


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
    normalized_mode = canonical_mode(session.mode)
    return SessionResponse(
        session_id=session.session_id,
        status=session.status.value,
        mode=normalized_mode.value,
        trust_mode=session.trust_mode.value,
        workspace_root=session.workspace_root,
        model_selection=_model_selection_response(session.model_selection),
        transcript=[_transcript_entry_response(entry) for entry in session.transcript],
        current_user_prompt=session.current_user_prompt,
        current_assistant_message=session.current_assistant_message,
        pending_assistant_message=session.pending_assistant_message,
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


def _mode_catalog_response() -> ModeCatalogResponse:
    modes = [
        ModeDescriptorResponse.model_validate(mode_metadata(mode))
        for mode in (CoderMode.ASK, CoderMode.CODE, CoderMode.REVIEW)
    ]
    trust_modes = [
        TrustModeDescriptorResponse(
            id=trust_mode.value,
            label=trust_mode.value,
            description=description,
        )
        for trust_mode, description in TRUST_MODE_DESCRIPTIONS.items()
    ]
    return ModeCatalogResponse(modes=modes, trust_modes=trust_modes)


def _sse(event: str, data: dict[str, Any]) -> str:
    payload = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


def _chunk_text(text: str, size: int = 24) -> list[str]:
    if not text:
        return []
    return [text[index : index + size] for index in range(0, len(text), size)]


def _prompt_with_context(
    prompt: str, context_files: list[str], workspace: Any, use_bundle: bool = True
) -> tuple[str, list[str]]:
    files = [path.strip() for path in context_files if path.strip()]
    if not files:
        return prompt, []

    if not use_bundle:
        listed = "\n".join(f"- {path}" for path in files)
        return f"Selected context files:\n{listed}\n\nUser prompt:\n{prompt}", []

    bundle = _backend().build_context_bundle(workspace, files)
    block = bundle.to_prompt_block()
    errors = bundle.errors
    if block:
        return f"{block}\n\nUser prompt:\n{prompt}", errors
    return prompt, errors


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


@router.get("/sessions", response_model=list[SessionResponse])
def api_list_sessions(request: Request, workspace_root: str | None = None) -> list[SessionResponse]:
    return [
        _session_response(session)
        for session in _backend().list_sessions(workspace_from_request(request, workspace_root))
    ]


@router.post("/sessions", response_model=SessionResponse)
def api_create_session(request: Request, body: CoderSessionCreateRequest) -> SessionResponse:
    session = _backend().create_session(
        workspace_from_request(request, body.workspace_root),
        trust_mode=body.trust_mode,
        mode=body.mode,
        profile=body.profile,
        provider=body.provider,
        model=body.model,
    )
    return _session_response(session)


@router.get("/sessions/{session_id}", response_model=SessionResponse)
def api_get_session(
    request: Request, session_id: str, workspace_root: str | None = None
) -> SessionResponse:
    try:
        return _session_response(
            _backend().get_session(workspace_from_request(request, workspace_root), session_id)
        )
    except Exception as exc:
        if "not found" in str(exc).lower():
            raise HTTPException(status_code=404, detail=E_SESSION_NOT_FOUND.to_dict()) from exc
        raise HTTPException(status_code=500, detail=from_exception(exc).to_dict()) from exc


@router.get("/sessions/{session_id}/view", response_model=SessionViewResponse)
def api_get_session_view(
    request: Request, session_id: str, workspace_root: str | None = None
) -> SessionViewResponse:
    return _session_view_response(
        _backend().get_session_view(workspace_from_request(request, workspace_root), session_id)
    )


@router.post("/sessions/{session_id}/messages", response_model=SessionResponse)
def api_post_message(
    session_id: str,
    request: Request,
    body: CoderSessionMessageRequest,
    workspace_root: str | None = None,
) -> SessionResponse:
    req_id = get_request_id(request)
    if len(body.prompt.encode("utf-8")) > MAX_JSON_BODY_BYTES:
        raise HTTPException(status_code=413, detail=E_REQUEST_TOO_LARGE.to_dict())
    workspace = workspace_from_request(request, workspace_root)
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
            _backend().post_message(workspace, session_id, prompt, request_id=req_id)
        )
    except ValueError as exc:
        if "already running" in str(exc).lower():
            raise HTTPException(status_code=409, detail=E_SESSION_LOCKED.to_dict()) from exc
        raise HTTPException(status_code=400, detail=from_exception(exc).to_dict()) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=from_exception(exc).to_dict()) from exc


@router.post("/sessions/{session_id}/messages/stream")
async def api_post_message_stream(
    session_id: str,
    request: Request,
    body: CoderSessionMessageRequest,
    workspace_root: str | None = None,
) -> StreamingResponse:
    req_id = get_request_id(request)
    if len(body.prompt.encode("utf-8")) > MAX_JSON_BODY_BYTES:
        raise HTTPException(status_code=413, detail=E_REQUEST_TOO_LARGE.to_dict())
    workspace = workspace_from_request(request, workspace_root)
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

        backend = _backend()
        task = asyncio.create_task(
            asyncio.to_thread(
                backend.post_message,
                workspace,
                session_id,
                prompt,
                request_id=req_id,
            )
        )
        sent_event_count = 0
        sent_text_length = 0
        try:
            while not task.done():
                try:
                    view = backend.get_session_view(workspace, session_id)
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


@router.post("/sessions/{session_id}/queue", response_model=SessionResponse)
def api_queue_message(
    request: Request, session_id: str, body: CoderQueueRequest, workspace_root: str | None = None
) -> SessionResponse:
    if len(body.prompt.encode("utf-8")) > MAX_JSON_BODY_BYTES:
        raise HTTPException(status_code=413, detail=E_REQUEST_TOO_LARGE.to_dict())
    return _session_response(
        _backend().queue_message(
            workspace_from_request(request, workspace_root), session_id, body.prompt
        )
    )


@router.patch("/sessions/{session_id}/model", response_model=SessionResponse)
def api_update_model(
    request: Request,
    session_id: str,
    body: CoderSessionModelRequest,
    workspace_root: str | None = None,
) -> SessionResponse:
    return _session_response(
        _backend().update_session_model(
            workspace_from_request(request, workspace_root),
            session_id,
            profile=body.profile,
            provider=body.provider,
            model=body.model,
        )
    )


@router.patch("/sessions/{session_id}/mode", response_model=SessionResponse)
def api_update_mode(
    request: Request,
    session_id: str,
    body: CoderSessionModeRequest,
    workspace_root: str | None = None,
) -> SessionResponse:
    return _session_response(
        _backend().set_session_mode(
            workspace_from_request(request, workspace_root), session_id, body.mode
        )
    )


@router.patch("/sessions/{session_id}/trust-mode", response_model=SessionResponse)
def api_update_trust_mode(
    request: Request,
    session_id: str,
    body: CoderSessionTrustModeRequest,
    workspace_root: str | None = None,
) -> SessionResponse:
    return _session_response(
        _backend().update_session_trust_mode(
            workspace_from_request(request, workspace_root),
            session_id,
            body.trust_mode,
        )
    )


@router.post("/sessions/{session_id}/cancel", response_model=SessionResponse)
def api_cancel_session(
    session_id: str,
    request: Request,
    workspace_root: str | None = None,
) -> SessionResponse:
    req_id = get_request_id(request)
    try:
        return _session_response(
            _backend().cancel_session(
                workspace_from_request(request, workspace_root), session_id, request_id=req_id
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


@router.post("/sessions/{session_id}/resume", response_model=SessionResponse)
def api_resume_session(
    session_id: str,
    request: Request,
    workspace_root: str | None = None,
) -> SessionResponse:
    req_id = get_request_id(request)
    workspace = workspace_from_request(request, workspace_root)
    try:
        session = _backend().resume_session(workspace, session_id, request_id=req_id)
    except ValueError as exc:
        if "not found" in str(exc).lower():
            raise HTTPException(status_code=404, detail=E_SESSION_NOT_FOUND.to_dict()) from exc
        if "not in a resumable state" in str(exc).lower() or "already running" in str(exc).lower():
            raise HTTPException(status_code=409, detail=E_RESUME_INVALID_STATE.to_dict()) from exc
        raise HTTPException(status_code=400, detail=from_exception(exc).to_dict()) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=from_exception(exc).to_dict()) from exc
    return _session_response(session)


@router.post(
    "/sessions/{session_id}/context/validate",
    response_model=ContextValidationResponse,
)
def api_validate_context(
    request: Request,
    session_id: str,
    body: ContextValidateRequest,
    workspace_root: str | None = None,
) -> ContextValidationResponse:
    workspace = workspace_from_request(request, workspace_root)
    bundle = _backend().build_context_bundle(workspace, body.paths)
    return ContextValidationResponse(
        session_id=session_id,
        items=[ContextPreviewResponse.model_validate(item) for item in bundle.to_preview_payload()],
        errors=bundle.errors,
        total_token_estimate=bundle.total_token_estimate(),
    )


@router.post(
    "/sessions/{session_id}/approvals/{request_id}/grant",
    response_model=SessionResponse,
)
def api_grant_approval(
    session_id: str,
    request_id: str,
    req: Request,
    workspace_root: str | None = None,
) -> SessionResponse:
    caller_request_id = get_request_id(req)
    return _session_response(
        _backend().approve_request(
            workspace_from_request(req, workspace_root),
            session_id,
            request_id,
            grant=True,
            caller_request_id=caller_request_id,
        )
    )


@router.post(
    "/sessions/{session_id}/approvals/{request_id}/deny",
    response_model=SessionResponse,
)
def api_deny_approval(
    session_id: str,
    request_id: str,
    req: Request,
    workspace_root: str | None = None,
) -> SessionResponse:
    caller_request_id = get_request_id(req)
    return _session_response(
        _backend().approve_request(
            workspace_from_request(req, workspace_root),
            session_id,
            request_id,
            grant=False,
            caller_request_id=caller_request_id,
        )
    )


@router.get("/sessions/{session_id}/diff", response_model=list[SessionDiffResponse])
def api_diff(
    request: Request, session_id: str, workspace_root: str | None = None
) -> list[SessionDiffResponse]:
    return [
        _session_diff_response(diff)
        for diff in _backend()
        .get_session_view(workspace_from_request(request, workspace_root), session_id)
        .diffs
    ]


@router.get("/runs", response_model=list[RunView])
def api_runs(request: Request, workspace_root: str | None = None) -> list[RunView]:
    return cast(list[RunView], list_run_views(workspace_from_request(request, workspace_root)))


@router.get("/models")
def api_models() -> dict[str, Any]:
    backend = _backend()
    options = cast(dict[str, Any], backend.list_model_options())
    health = backend.load_health()
    for profile in options.get("profiles", []):
        for model in profile.get("models", []):
            provider_id = model.get("provider", "")
            key = f"{profile['name']}/{provider_id}"
            h = health.get(key)
            if h:
                model["health"] = h.to_dict()
            else:
                model["health"] = None
            model["recommendations"] = {
                "planner_suitable": "json" in model.get("capabilities", []),
                "context_window_hint": "unknown",
                "cost_support": True,
            }
    return options


@router.get("/modes", response_model=ModeCatalogResponse)
def api_modes() -> ModeCatalogResponse:
    return _mode_catalog_response()


@router.get("/commands", response_model=list[CommandRegistryEntry])
def api_commands() -> list[CommandRegistryEntry]:
    return [CommandRegistryEntry.model_validate(item) for item in _backend().available_commands()]


@router.get("/sessions/{session_id}/usage", response_model=UsageResponse)
def api_session_usage(
    request: Request, session_id: str, workspace_root: str | None = None
) -> UsageResponse:
    return _usage_response(
        aggregate_session_usage(workspace_from_request(request, workspace_root), session_id)
    )
