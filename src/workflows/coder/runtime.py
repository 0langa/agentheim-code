from __future__ import annotations

# ruff: noqa: SIM905
import contextlib
import importlib
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from config.config import ModelRole, load_profiles_document
from core.public_api import ApprovalRequest, EventType, RiskLevel, RunLedger, safe_project_path
from workflows.coder.action_engine import (
    _apply_plan,
    _approval_denied_message,
    _create_invoker,
    _run_actions,
    _tool_context,
)
from workflows.coder.commands import command_ids, command_registry
from workflows.coder.models import (
    ActivityKind,
    CoderApproval,
    CoderCommandResult,
    CoderDiff,
    CoderEvent,
    CoderMessage,
    CoderMode,
    CoderModelSelection,
    CoderSession,
    CoderSessionView,
    RuntimeEventKind,
    SessionStatus,
    TrustMode,
    canonical_mode,
)
from workflows.coder.planner import _plan_turn
from workflows.coder.prompt_builder import (
    _session_has_coding_context,
    _workspace_action_requested,
    _workspace_scan_summary,
)
from workflows.coder.repair import _repair_failed_verification
from workflows.coder.session_store import (
    _append_diff,
    _append_event,
    _append_message,
    _artifacts,
    _load_session,
    _open_ledger,
    _read_jsonl_model,
    _record_activity,
    _save_session,
    _session_paths,
    _SessionLock,
    _set_status,
    _utcnow,
)
from workflows.coder.verification import _detect_verification_profiles

WORKFLOW_ID = "coder"
PRESET_ID = "coder"


def _simple_workspace_health_reply(summary: dict[str, Any]) -> str:
    languages = summary.get("languages") or []
    manifests = summary.get("manifests") or []
    warnings = summary.get("warnings") or []
    file_count = int(summary.get("file_count") or 0)
    git_available = bool(summary.get("git_available"))

    primary_language = ", ".join(languages[:2]) if languages else "local"
    parts = [
        f"I checked the workspace locally. It looks like a {primary_language} workspace with {file_count} files."
    ]
    if manifests:
        parts.append(f"Detected project files: {', '.join(manifests[:3])}.")
    else:
        parts.append("I did not detect a dependency manifest or standard project file.")
    if warnings:
        parts.append(f"Main concern: {warnings[0]}.")
    if not git_available:
        parts.append("Git is not available in this workspace.")
    return " ".join(parts)


def _command_ids() -> list[str]:
    return list(command_ids())


def available_commands() -> list[dict[str, str]]:
    return [
        {
            "id": item["id"],
            "label": item["label"],
            "cli": item["cli"],
            "surface": item["surface"],
        }
        for item in command_registry()
    ]


def _normalize_model_selection(
    *,
    profile: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    role: str | None = None,
) -> CoderModelSelection:
    return CoderModelSelection(
        profile=profile or "auto",
        provider=provider or "auto",
        model=model or "auto",
        role=role or ModelRole.PLANNER.value,
    )


def _should_use_local_workspace_fallback(
    session: CoderSession, prompt: str, exc: Exception
) -> bool:
    if canonical_mode(session.mode) != CoderMode.CODE:
        return False
    if _session_has_coding_context(session, prompt):
        return False
    if not _workspace_action_requested(session, prompt):
        return False
    lowered = str(exc).lower()
    return any(
        marker in lowered
        for marker in ("content_filter", "responsibleaipolicyviolation", "jailbreak")
    )


def _complete_local_workspace_fallback(
    workspace_root: Path, session: CoderSession, prompt: str
) -> CoderSession:
    workspace_summary, _ = _workspace_scan_summary(workspace_root)
    reply = _simple_workspace_health_reply(workspace_summary)
    session = session.model_copy(
        update={
            "current_user_prompt": prompt,
            "current_summary": reply,
            "current_assistant_message": None,
            "planned_assistant_message": None,
            "pending_assistant_message": None,
            "last_failure_reason": "",
            "updated_at": _utcnow(),
        }
    )
    session = _record_activity(
        workspace_root,
        session,
        ActivityKind.SCANNING,
        "Used local workspace inspection fallback after provider planning was blocked.",
    )
    message = CoderMessage(role="assistant", content=reply, created_at=_utcnow())
    _append_message(workspace_root, session.session_id, message)
    session = session.model_copy(
        update={
            "transcript": [*session.transcript, message],
            "updated_at": message.created_at,
        }
    )
    session = _record_activity(workspace_root, session, ActivityKind.COMPLETED, reply)
    return _set_status(session, SessionStatus.COMPLETED)


def create_session(
    workspace_root: str | Path,
    *,
    trust_mode: str = "ask",
    mode: str = "code",
    profile: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    request_id: str = "",
) -> CoderSession:
    workspace = safe_project_path(workspace_root)
    trust = TrustMode(trust_mode)
    normalized_mode = canonical_mode(mode)
    scan_summary, git_available = _workspace_scan_summary(workspace)
    ledger = RunLedger.create(workspace, "coder")
    verification_profiles = _detect_verification_profiles(workspace)
    session = CoderSession(
        session_id=ledger.run_dir.name,
        workspace_root=str(workspace),
        trust_mode=trust,
        mode=normalized_mode,
        model_selection=_normalize_model_selection(profile=profile, provider=provider, model=model),
        created_at=_utcnow(),
        updated_at=_utcnow(),
        git_available=git_available,
        verification_profiles=verification_profiles,
    )
    run_json_payload: dict[str, Any] = {
        "run_id": session.session_id,
        "product": "agentheim-code",
        "workflow_id": WORKFLOW_ID,
        "preset_id": PRESET_ID,
        "repo_root": str(workspace),
        "created_at": session.created_at,
        "trust_mode": trust.value,
        "mode": normalized_mode.value,
        "model_selection": _normalize_model_selection(
            profile=profile, provider=provider, model=model
        ).model_dump(mode="json"),
        "status": session.status.value,
        "workspace_summary": scan_summary,
    }
    if request_id:
        run_json_payload["request_id"] = request_id
    ledger.write_json("run.json", run_json_payload)
    init_payload: dict[str, Any] = {
        "workflow_id": WORKFLOW_ID,
        "repo_root": str(workspace),
        "metadata": {"trust_mode": trust.value},
    }
    if request_id:
        init_payload["request_id"] = request_id
    ledger.emit_event(EventType.RUN_INITIATED, payload=init_payload)
    _save_session(workspace, session)
    return session


def get_session(workspace_root: str | Path, session_id: str) -> CoderSession:
    workspace = safe_project_path(workspace_root)
    return _load_session(workspace, session_id)


def list_sessions(workspace_root: str | Path) -> list[CoderSession]:
    workspace = safe_project_path(workspace_root)
    runs_dir = workspace / ".ai-team" / "runs"
    if not runs_dir.exists():
        return []
    sessions: list[CoderSession] = []
    for run_dir in sorted(runs_dir.iterdir(), reverse=True):
        run_json = run_dir / "run.json"
        session_json = run_dir / "session.json"
        if not run_json.exists() or not session_json.exists():
            continue
        try:
            run_data = json.loads(run_json.read_text(encoding="utf-8"))
        except Exception:
            continue
        if run_data.get("workflow_id") != WORKFLOW_ID:
            continue
        try:
            sessions.append(_load_session(workspace, run_dir.name))
        except Exception:
            continue
    sessions.sort(key=lambda item: item.updated_at, reverse=True)
    return sessions


def get_session_view(workspace_root: str | Path, session_id: str) -> CoderSessionView:
    workspace = safe_project_path(workspace_root)
    paths = _session_paths(workspace, session_id)
    session = _load_session(workspace, session_id)
    approvals = []
    if session.pending_approval:
        approvals.append(
            CoderApproval(
                request_id=session.pending_approval.request_id,
                tool_id=session.pending_approval.tool_id,
                risk_level=session.pending_approval.risk_level,
                reason=session.pending_approval.reason,
                status=session.pending_approval.status,
            )
        )
    return CoderSessionView(
        session=session,
        events=_read_jsonl_model(paths["events"], CoderEvent),
        approvals=approvals,
        diffs=_read_jsonl_model(paths["diffs"], CoderDiff),
        command_results=_read_jsonl_model(paths["commands"], CoderCommandResult),
        artifacts=_artifacts(workspace, session_id),
        queued_prompts=list(session.queued_prompts),
        available_commands=_command_ids(),
    )


def list_session_views(workspace_root: str | Path) -> list[CoderSessionView]:
    workspace = safe_project_path(workspace_root)
    return [get_session_view(workspace, session.session_id) for session in list_sessions(workspace)]


def cancel_session(
    workspace_root: str | Path, session_id: str, *, request_id: str = ""
) -> CoderSession:
    workspace = safe_project_path(workspace_root)
    session = _load_session(workspace, session_id)
    session = session.model_copy(
        update={"pending_approval": None, "pending_assistant_message": None}
    )
    cancel_details: dict[str, str] = {"status": "cancelled"}
    if session.planned_actions and session.next_action_index < len(session.planned_actions):
        current_action = session.planned_actions[session.next_action_index]
        cancel_details["interrupted_action"] = current_action.kind
        cancel_details["action_index"] = str(session.next_action_index)
    if request_id:
        cancel_details["request_id"] = request_id
    session = _record_activity(
        workspace,
        session,
        ActivityKind.BLOCKED,
        "Session cancelled.",
        cancel_details,
        request_id=request_id,
    )
    _append_event(
        workspace,
        session_id,
        CoderEvent(
            event_id=uuid4().hex,
            kind="cancelled",
            message="Session cancelled.",
            created_at=_utcnow(),
            details=cancel_details,
        ),
    )
    # Release any stale lock so the session can be resumed or re-used.
    lock_path = _session_paths(workspace, session_id)["lock"]
    with contextlib.suppress(FileNotFoundError):
        lock_path.unlink()
    return _save_session(workspace, _set_status(session, SessionStatus.CANCELLED))


def resume_session(
    workspace_root: str | Path, session_id: str, *, request_id: str = ""
) -> CoderSession:
    """Resume a session after interruption, failure, or approval-pending state.

    Sanity checks:
    - Session must exist
    - Session must not be currently running
    - If blocked/failed/cancelled, reset to idle so the user can send a new message
    - If awaiting approval, leave as-is (user must grant/deny)
    """
    workspace = safe_project_path(workspace_root)
    session = _load_session(workspace, session_id)

    if session.status == SessionStatus.RUNNING:
        raise ValueError(f"Session '{session_id}' is already running and cannot be resumed.")

    if session.status == SessionStatus.AWAITING_APPROVAL:
        # Leave as-is; user must handle approval
        return session

    if session.status in {SessionStatus.BLOCKED, SessionStatus.FAILED, SessionStatus.CANCELLED}:
        resume_details = {"previous_status": session.status.value}
        if request_id:
            resume_details["request_id"] = request_id
        session = _record_activity(
            workspace,
            session,
            ActivityKind.THINKING,
            "Session resumed.",
            resume_details,
            request_id=request_id,
        )
        session = _set_status(
            session.model_copy(update={"pending_assistant_message": None}),
            SessionStatus.IDLE,
        )
        return _save_session(workspace, session)

    # IDLE or COMPLETED: just return
    return session


def update_session_model(
    workspace_root: str | Path,
    session_id: str,
    *,
    profile: str | None = None,
    provider: str | None = None,
    model: str | None = None,
) -> CoderSession:
    workspace = safe_project_path(workspace_root)
    session = _load_session(workspace, session_id)
    current = session.model_selection
    selection = current.model_copy(
        update={
            "profile": profile if profile is not None else current.profile,
            "provider": provider if provider is not None else current.provider,
            "model": model if model is not None else current.model,
        }
    )
    updated = session.model_copy(update={"model_selection": selection, "updated_at": _utcnow()})
    updated = _record_activity(
        workspace,
        updated,
        ActivityKind.THINKING,
        f"Model selection updated: {selection.provider}/{selection.model}",
    )
    return _save_session(workspace, updated)


def update_session_trust_mode(
    workspace_root: str | Path, session_id: str, trust_mode: str
) -> CoderSession:
    workspace = safe_project_path(workspace_root)
    session = _load_session(workspace, session_id)
    trust = TrustMode(trust_mode)
    updated = session.model_copy(update={"trust_mode": trust, "updated_at": _utcnow()})
    updated = _record_activity(
        workspace, updated, ActivityKind.THINKING, f"Trust mode changed: {trust.value}"
    )
    return _save_session(workspace, updated)


def set_session_mode(workspace_root: str | Path, session_id: str, mode: str) -> CoderSession:
    workspace = safe_project_path(workspace_root)
    session = _load_session(workspace, session_id)
    normalized = canonical_mode(mode)
    updated = session.model_copy(update={"mode": normalized, "updated_at": _utcnow()})
    updated = _record_activity(
        workspace, updated, ActivityKind.THINKING, f"Mode changed: {normalized.value}"
    )
    return _save_session(workspace, updated)


def queue_message(workspace_root: str | Path, session_id: str, prompt: str) -> CoderSession:
    workspace = safe_project_path(workspace_root)
    session = _load_session(workspace, session_id)
    queued = [*session.queued_prompts, prompt]
    updated = session.model_copy(update={"queued_prompts": queued, "updated_at": _utcnow()})
    updated = _record_activity(workspace, updated, ActivityKind.THINKING, "Prompt queued.")
    return _save_session(workspace, updated)


def list_model_options() -> dict[str, Any]:
    try:
        document = load_profiles_document()
    except Exception as exc:
        return {
            "configured": False,
            "default_profile": "default",
            "profiles": [],
            "error": "Provider profiles are not configured.",
            "detail": type(exc).__name__,
        }
    profiles = []
    for profile_name in sorted(document.profiles):
        profile = document.profiles[profile_name]
        profiles.append(
            {
                "name": profile_name,
                "default": profile_name == document.default_profile,
                "providers": [
                    {
                        "id": provider.id,
                        "kind": provider.kind,
                        "auth_mode": provider.auth_mode,
                        "endpoint": provider.endpoint,
                    }
                    for provider in profile.providers.values()
                ],
                "models": [
                    {
                        "id": model.id,
                        "role": model.role.value,
                        "provider": model.provider,
                        "model": model.model,
                        "display_name": model.display_name or model.model,
                        "capabilities": model.capabilities,
                    }
                    for model in profile.models.values()
                ],
            }
        )
    return {"configured": True, "default_profile": document.default_profile, "profiles": profiles}


def post_message(
    workspace_root: str | Path, session_id: str, prompt: str, *, request_id: str = ""
) -> CoderSession:
    workspace = safe_project_path(workspace_root)
    with _SessionLock(workspace, session_id):
        session = _load_session(workspace, session_id)
        user_message = CoderMessage(role="user", content=prompt, created_at=_utcnow())
        _append_message(workspace, session.session_id, user_message)
        session = session.model_copy(update={"transcript": [*session.transcript, user_message]})
        session = _set_status(session, SessionStatus.RUNNING)
        session = _record_activity(
            workspace,
            session,
            RuntimeEventKind.TURN_STARTED,
            "Turn started.",
            details={"prompt": prompt, "mode": session.mode.value, "request_id": request_id},
        )
        session = _record_activity(
            workspace, session, ActivityKind.THINKING, "Planning next turn.", request_id=request_id
        )
        session = _record_activity(
            workspace,
            session,
            ActivityKind.SCANNING,
            "Scanning workspace state.",
            request_id=request_id,
        )

        ledger = _open_ledger(workspace, session_id)
        try:
            plan = _plan_turn(workspace, session, prompt, ledger=ledger)
            session = _record_activity(
                workspace,
                session,
                RuntimeEventKind.PLANNER_RESULT,
                f"Planner produced {len(plan.actions)} action(s).",
                details={
                    "action_count": len(plan.actions),
                    "action_kinds": [a.kind for a in plan.actions],
                    "summary": plan.summary,
                },
            )
        except Exception as exc:
            if _should_use_local_workspace_fallback(session, prompt, exc):
                session = _complete_local_workspace_fallback(workspace, session, prompt)
                return _save_session(workspace, session)
            from agentheim_code.structured_errors import from_exception

            structured = from_exception(exc, event_id=request_id)
            ledger.emit_event(
                EventType.RUN_FAILED,
                payload={
                    "workflow_id": WORKFLOW_ID,
                    "reason": str(exc),
                    "error_type": type(exc).__name__,
                    "structured_error": structured.to_dict(),
                    "request_id": request_id,
                },
            )
            session = _record_activity(
                workspace,
                session,
                RuntimeEventKind.TURN_FAILED,
                f"Turn failed during planning: {structured.message}",
                details={"error_type": type(exc).__name__, "error": structured.message},
            )
            session = session.model_copy(
                update={
                    "current_summary": "Coder turn failed",
                    "current_assistant_message": structured.message,
                    "last_failure_reason": structured.message,
                }
            )
            session = _set_status(session, SessionStatus.FAILED)
            return _save_session(workspace, session)

        session = _apply_plan(session, prompt, plan)
        session = _run_actions(workspace, ledger, session, verify_prompt=prompt)
        if session.status == SessionStatus.BLOCKED:
            session = _record_activity(
                workspace,
                session,
                RuntimeEventKind.REPAIR_STARTED,
                "Verification failed; starting repair.",
                details={
                    "last_verification_command": session.last_verification_command,
                    "last_verification_exit_code": session.last_verification_exit_code,
                },
            )
            session = _repair_failed_verification(workspace, ledger, session, prompt)
            if session.status == SessionStatus.BLOCKED:
                session = _record_activity(
                    workspace,
                    session,
                    RuntimeEventKind.REPAIR_EXHAUSTED,
                    "Repair attempts exhausted.",
                    details={
                        "repair_attempts": session.repair_attempts,
                        "last_verification_command": session.last_verification_command,
                    },
                )
            elif session.status == SessionStatus.COMPLETED:
                session = _record_activity(
                    workspace,
                    session,
                    RuntimeEventKind.REPAIR_COMPLETED,
                    "Repair succeeded.",
                )
        if session.status == SessionStatus.COMPLETED:
            session = _record_activity(
                workspace,
                session,
                RuntimeEventKind.TURN_COMPLETED,
                session.current_summary or "Turn completed.",
                details={
                    "changed_files": session.changed_files,
                    "summary": session.current_summary,
                },
            )
        return _save_session(workspace, session)


def approve_request(
    workspace_root: str | Path,
    session_id: str,
    request_id: str,
    *,
    grant: bool,
    caller_request_id: str = "",
) -> CoderSession:
    workspace = safe_project_path(workspace_root)
    session = _load_session(workspace, session_id)
    pending = session.pending_approval
    if pending is None or pending.request_id != request_id:
        raise ValueError(f"Approval request '{request_id}' not found for session '{session_id}'.")

    ledger = _open_ledger(workspace, session_id)
    if not grant:
        ledger.emit_event(
            EventType.APPROVAL_DENIED, tool_id=pending.tool_id, payload={"request_id": request_id}
        )
        session = session.model_copy(
            update={
                "pending_approval": None,
                "planned_assistant_message": None,
                "pending_assistant_message": _approval_denied_message(pending),
                "current_summary": "Approval denied",
            }
        )
        session = _record_activity(workspace, session, ActivityKind.BLOCKED, "Approval denied.")
        session = _set_status(session, SessionStatus.BLOCKED)
        return _save_session(workspace, session)

    ledger.emit_event(
        EventType.APPROVAL_GRANTED, tool_id=pending.tool_id, payload={"request_id": request_id}
    )
    invoker = _create_invoker(workspace, session.trust_mode)
    before_content = ""
    pending_path = str(pending.params.get("path", ""))
    if pending.tool_id == "filesystem" and pending_path:
        target = workspace / pending_path
        if target.exists() and target.is_file():
            before_content = target.read_text(encoding="utf-8", errors="ignore")
    result = invoker.invoke(
        pending.tool_id,
        pending.params,
        _tool_context(workspace),
        ledger=ledger,
        granted_request=ApprovalRequest(
            request_id=request_id,
            tool_id=pending.tool_id,
            action=str(pending.params.get("operation", "invoke")),
            target=str(pending.params.get("path", pending.params.get("command", pending.tool_id))),
            risk_level=RiskLevel(pending.risk_level),
            justification=pending.reason,
            params_redacted=pending.params,
            timestamp=_utcnow(),
            decision="allow",
            policy_id="coder_approval_override",
            override_possible=False,
        ),
    )
    if not result.success:
        session = session.model_copy(
            update={
                "pending_approval": None,
                "planned_assistant_message": None,
                "pending_assistant_message": None,
            }
        )
        session = _record_activity(
            workspace, session, ActivityKind.BLOCKED, result.error or "Approved action failed."
        )
        session = _set_status(session, SessionStatus.BLOCKED)
        return _save_session(workspace, session)

    changed_files = list(session.changed_files)
    path = str(pending.params.get("path", ""))
    if pending.tool_id == "filesystem" and path and path not in changed_files:
        changed_files.append(path)
    if pending.tool_id == "filesystem" and path:
        _append_diff(
            workspace,
            session.session_id,
            CoderDiff(
                path=path,
                before=before_content,
                after=str(pending.params.get("content", "")),
                created_at=_utcnow(),
            ),
        )
    session = session.model_copy(
        update={
            "pending_approval": None,
            "current_assistant_message": None,
            "pending_assistant_message": None,
            "changed_files": changed_files,
            "next_action_index": pending.action_index + 1,
            "updated_at": _utcnow(),
        }
    )
    session = _run_actions(workspace, ledger, _set_status(session, SessionStatus.RUNNING))
    return _save_session(workspace, session)


_COMPAT_EXPORTS = {
    **dict.fromkeys(
        "_command_exit_code _complete_turn _invoke_action _policy_config _tool_result_data".split(),
        "workflows.coder.action_engine",
    ),
    **dict.fromkeys("CoderAction".split(), "workflows.coder.models"),
    **dict.fromkeys(
        "_clean_raw_file_content _coder_output_token_budget _compact_planner_user_prompt "
        "_content_preview _fill_missing_write_contents _invoke_planner_json "
        "_offline_violations _parse_turn_plan _plan_has_verification _sanitize_plan "
        "_turn_plan_response_schema _write_file_content_issues".split(),
        "workflows.coder.planner",
    ),
    **dict.fromkeys(
        "_allow_noop_plan _assistant_message_reads_like_future_intent "
        "_assistant_requested_workspace_action _mode_allows_noop_plan _mode_planner_guidance "
        "_normalize_completed_assistant_message _normalized_prompt_text "
        "_planner_command_guidance _prompt_explicitly_requests_workspace_action "
        "_prompt_is_workspace_action_affirmation _requires_coding_verification "
        "_trust_mode_planner_guidance".split(),
        "workflows.coder.prompt_builder",
    ),
    **dict.fromkeys(
        "_append_activity _append_command_result _append_diff _append_jsonl "
        "_last_command_result _session_lock_is_stale _session_lock_pid _write_json "
        "browse_file_tree list_file_tree".split(),
        "workflows.coder.session_store",
    ),
}


def __getattr__(name: str) -> Any:
    if name in _COMPAT_EXPORTS:
        value = getattr(importlib.import_module(_COMPAT_EXPORTS[name]), name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
