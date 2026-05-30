from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, cast
from uuid import uuid4

from core.patching import PatchApplier
from core.public_api import (
    EventType,
    PolicyConfig,
    PolicyEngine,
    RiskLevel,
    RunLedger,
    ToolContext,
    ToolInvoker,
    safe_project_path,
)
from tools.registry import create_core_tool_registry
from workflows.coder.models import (
    ActivityKind,
    CoderAction,
    CoderCommandResult,
    CoderDiff,
    CoderMessage,
    CoderSession,
    CoderTurnPlan,
    PendingApproval,
    RuntimeEventKind,
    SessionStatus,
    TrustMode,
)
from workflows.coder.prompt_builder import (
    _assistant_message_reads_like_future_intent,
    _normalize_completed_assistant_message,
)
from workflows.coder.session_store import (
    _append_command_result,
    _append_diff,
    _append_message,
    _record_activity,
    _set_status,
    _utcnow,
)

WORKFLOW_ID = "coder"
SAFE_COMMANDS = ("python", "pytest", "git", "npm", "node", "pip", "poetry", "cargo", "go", "dotnet")


def _policy_config(trust_mode: TrustMode) -> PolicyConfig:
    risk_rules: dict[RiskLevel, Literal["allow", "ask", "deny"]] = {
        RiskLevel.NONE: "allow",
        RiskLevel.LOW: "allow",
        RiskLevel.MEDIUM: "ask",
        RiskLevel.HIGH: "ask",
        RiskLevel.CRITICAL: "deny",
    }
    if trust_mode == TrustMode.READ_ONLY:
        risk_rules[RiskLevel.MEDIUM] = "deny"
        risk_rules[RiskLevel.HIGH] = "deny"
    elif trust_mode == TrustMode.WORKSPACE:
        risk_rules[RiskLevel.MEDIUM] = "allow"
        risk_rules[RiskLevel.HIGH] = "allow"
    return PolicyConfig(
        risk_rules=risk_rules,
        command_allowlist=list(SAFE_COMMANDS),
        network_allowed=False,
        local_only=True,
    )


def _tool_context(workspace_root: Path) -> ToolContext:
    return ToolContext(
        workspace=workspace_root,
        allowed_paths=[str(workspace_root)],
        denied_paths=[str(workspace_root / ".git"), str(workspace_root / ".ai-team")],
        allowed_commands=list(SAFE_COMMANDS),
        network_allowed=False,
    )


def _tool_result_data(result: Any) -> dict[str, Any]:
    if hasattr(result.data, "model_dump"):
        return cast(dict[str, Any], result.data.model_dump())
    if isinstance(result.data, dict):
        return result.data
    return {}


def _command_exit_code(data: dict[str, Any]) -> int | None:
    raw = data.get("returncode")
    if raw is None:
        raw = data.get("exit_code")
    try:
        return int(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def _approval_target_summary(pending: PendingApproval) -> str:
    if pending.tool_id == "shell.execute":
        command = pending.params.get("command", [])
        if isinstance(command, list) and command:
            return "run `" + " ".join(str(part) for part in command) + "`"
    path = pending.params.get("path")
    if path:
        operation = str(pending.params.get("operation", "update"))
        return f"{operation} `{path}`"
    return f"use `{pending.tool_id}`"


def _approval_wait_message(session: CoderSession, pending: PendingApproval) -> str:
    return (
        f"This turn is paused until you approve {_approval_target_summary(pending)}. "
        f"Reason: {pending.reason}."
    )


def _approval_denied_message(pending: PendingApproval) -> str:
    return (
        f"I stopped because approval was denied for {_approval_target_summary(pending)}. "
        "You can grant approval on a retry or send a new instruction to take a different path."
    )


def _create_invoker(workspace_root: Path, trust_mode: TrustMode) -> ToolInvoker:
    registry = create_core_tool_registry(workspace_root)
    policy_engine = PolicyEngine(_policy_config(trust_mode))
    return ToolInvoker(registry=registry, policy_engine=policy_engine)


def _invoke_action(
    workspace_root: Path,
    ledger: RunLedger,
    session: CoderSession,
    action: CoderAction,
) -> tuple[CoderSession, bool]:
    invoker = _create_invoker(workspace_root, session.trust_mode)
    context = _tool_context(workspace_root)

    tool_id = "filesystem"
    params: dict[str, Any]
    if action.kind == "list_files":
        params = {"operation": "list", "path": action.path or "."}
    elif action.kind == "read_file":
        params = {"operation": "read", "path": action.path or "."}
    elif action.kind == "write_file":
        params = {"operation": "write", "path": action.path or ".", "content": action.content or ""}
    elif action.kind == "apply_patch":
        return _invoke_patch_action(workspace_root, ledger, session, action)
    elif action.kind == "run_command":
        tool_id = "shell.execute"
        params = {"command": action.command, "timeout_seconds": 120}
    else:
        session = _record_activity(
            workspace_root, session, ActivityKind.BLOCKED, f"Unsupported action kind: {action.kind}"
        )
        return _set_status(session, SessionStatus.FAILED), False

    session = _record_activity(
        workspace_root,
        session,
        RuntimeEventKind.TOOL_PROPOSED,
        action.summary or action.kind,
        details={"tool_id": tool_id, "action_kind": action.kind, "path": action.path or ""},
    )
    before_content = ""
    if action.kind == "write_file" and action.path:
        target = safe_project_path(workspace_root) / action.path
        if target.exists() and target.is_file():
            before_content = target.read_text(encoding="utf-8", errors="ignore")
    result = invoker.invoke(tool_id, params, context, ledger=ledger)
    if result.requires_approval:
        request_id = uuid4().hex
        risk_level = result.policy.risk_level.value if result.policy else "medium"
        reason = result.policy.reason if result.policy else "approval required"
        ledger.emit_event(
            EventType.APPROVAL_REQUESTED,
            tool_id=tool_id,
            payload={
                "request_id": request_id,
                "params": params,
                "risk_level": risk_level,
                "reason": reason,
            },
        )
        pending = PendingApproval(
            request_id=request_id,
            tool_id=tool_id,
            params=params,
            risk_level=risk_level,
            reason=reason,
            action_index=session.next_action_index,
        )
        session = session.model_copy(
            update={
                "pending_approval": pending,
                "pending_assistant_message": _approval_wait_message(session, pending),
            }
        )
        session = _record_activity(
            workspace_root, session, RuntimeEventKind.APPROVAL_REQUESTED, reason
        )
        return _set_status(session, SessionStatus.AWAITING_APPROVAL), False
    if not result.success:
        session = _record_activity(
            workspace_root,
            session,
            RuntimeEventKind.TOOL_OUTPUT,
            result.error or f"{tool_id} failed",
            details={"tool_id": tool_id, "success": False, "error": result.error or ""},
        )
        session = _record_activity(
            workspace_root, session, ActivityKind.BLOCKED, result.error or f"{tool_id} failed"
        )
        return _set_status(session, SessionStatus.BLOCKED), False

    session = _record_activity(
        workspace_root,
        session,
        RuntimeEventKind.TOOL_OUTPUT,
        f"{tool_id} succeeded",
        details={"tool_id": tool_id, "success": True},
    )

    changed_files = list(session.changed_files)
    if action.kind == "write_file" and action.path and action.path not in changed_files:
        changed_files.append(action.path)
    if action.kind == "write_file" and action.path:
        _append_diff(
            workspace_root,
            session.session_id,
            CoderDiff(
                path=action.path,
                before=before_content,
                after=action.content or "",
                created_at=_utcnow(),
            ),
        )
    if action.kind == "run_command":
        data = _tool_result_data(result)
        exit_code = _command_exit_code(data)
        _append_command_result(
            workspace_root,
            session.session_id,
            CoderCommandResult(
                command=action.command,
                exit_code=exit_code,
                stdout=str(data.get("stdout", "")),
                stderr=str(data.get("stderr", "")),
                created_at=_utcnow(),
            ),
        )
        if exit_code not in (None, 0):
            session = _record_activity(
                workspace_root,
                session,
                RuntimeEventKind.VERIFICATION_FAILED,
                f"Command failed with exit code {exit_code}: {' '.join(action.command)}",
                details={
                    "command": " ".join(action.command),
                    "exit_code": exit_code,
                    "stdout": str(data.get("stdout", "")),
                    "stderr": str(data.get("stderr", "")),
                },
            )
            session = _record_activity(
                workspace_root,
                session,
                ActivityKind.BLOCKED,
                f"Command failed with exit code {exit_code}: {' '.join(action.command)}",
            )
            return _set_status(session, SessionStatus.BLOCKED), False
        session = _record_activity(
            workspace_root,
            session,
            RuntimeEventKind.VERIFICATION_PASSED,
            f"Command succeeded: {' '.join(action.command)}",
            details={"command": " ".join(action.command), "exit_code": exit_code},
        )
    session = session.model_copy(
        update={
            "changed_files": changed_files,
            "next_action_index": session.next_action_index + 1,
            "pending_assistant_message": None,
            "updated_at": _utcnow(),
        }
    )
    return session, True


def _invoke_patch_action(
    workspace_root: Path,
    ledger: RunLedger,
    session: CoderSession,
    action: CoderAction,
) -> tuple[CoderSession, bool]:
    if not action.path:
        session = _record_activity(
            workspace_root, session, ActivityKind.BLOCKED, "apply_patch missing path"
        )
        return _set_status(session, SessionStatus.BLOCKED), False

    session = _record_activity(
        workspace_root,
        session,
        RuntimeEventKind.PATCH_PROPOSED,
        action.summary or f"Apply patch to {action.path}",
        details={"path": action.path},
    )

    target = safe_project_path(workspace_root) / action.path
    before_content = ""
    is_new_file = not target.exists()
    if not is_new_file and target.is_file():
        before_content = target.read_text(encoding="utf-8", errors="ignore")

    applier = PatchApplier(workspace_root)
    file_change: dict[str, Any] = {
        "path": action.path,
        "change_type": "create" if is_new_file else "update",
    }
    if action.patch is not None:
        file_change["patch"] = action.patch
    elif action.old_string is not None and action.new_string is not None:
        file_change["old_string"] = action.old_string
        file_change["new_string"] = action.new_string
    else:
        session = _record_activity(
            workspace_root,
            session,
            ActivityKind.BLOCKED,
            f"apply_patch to {action.path} missing patch or old_string/new_string",
        )
        return _set_status(session, SessionStatus.BLOCKED), False

    try:
        result = applier.apply_changes([file_change])
    except Exception as exc:
        session = _record_activity(
            workspace_root,
            session,
            ActivityKind.BLOCKED,
            f"Patch failed for {action.path}: {exc}",
        )
        return _set_status(session, SessionStatus.BLOCKED), False

    if result.errors:
        session = _record_activity(
            workspace_root,
            session,
            ActivityKind.BLOCKED,
            f"Patch failed for {action.path}: {'; '.join(result.errors)}",
        )
        return _set_status(session, SessionStatus.BLOCKED), False

    after_content = ""
    if result.file_changes:
        after_content = result.file_changes[0].after_text

    _append_diff(
        workspace_root,
        session.session_id,
        CoderDiff(
            path=action.path,
            before=before_content,
            after=after_content,
            created_at=_utcnow(),
        ),
    )

    changed_files = list(session.changed_files)
    if action.path not in changed_files:
        changed_files.append(action.path)

    session = _record_activity(
        workspace_root,
        session,
        RuntimeEventKind.PATCH_APPLIED,
        f"Patch applied to {action.path}",
        details={"path": action.path, "is_new_file": is_new_file},
    )

    session = session.model_copy(
        update={
            "changed_files": changed_files,
            "next_action_index": session.next_action_index + 1,
            "pending_assistant_message": None,
            "updated_at": _utcnow(),
        }
    )
    return session, True


def _turn_report(session: CoderSession) -> str:
    """Build a concise structured summary of what the turn actually did."""
    parts: list[str] = []
    if session.changed_files:
        files = session.changed_files
        if len(files) <= 3:
            parts.append(f"Changed: {', '.join(files)}.")
        else:
            parts.append(f"Changed {len(files)} files.")
    if session.last_verification_command and session.last_verification_exit_code is not None:
        cmd = " ".join(session.last_verification_command)
        if session.last_verification_exit_code == 0:
            parts.append(f"Verified: {cmd}.")
        else:
            parts.append(
                f"Verification failed: {cmd} (exit {session.last_verification_exit_code})."
            )
    if session.repair_attempts > 0:
        parts.append(f"Repaired after {session.repair_attempts} attempt(s).")
    return "\n".join(parts)


def _complete_turn(workspace_root: Path, ledger: RunLedger, session: CoderSession) -> CoderSession:
    final_message = (
        session.planned_assistant_message
        or session.current_assistant_message
        or session.current_summary
        or "Coder turn completed."
    )
    if (
        session.planned_assistant_message
        and _assistant_message_reads_like_future_intent(session.planned_assistant_message)
        and session.current_summary
    ):
        final_message = session.current_summary
    final_message = _normalize_completed_assistant_message(final_message)
    report = _turn_report(session)
    if report and report not in final_message:
        final_message = f"{final_message}\n\n{report}"
    message = CoderMessage(
        role="assistant",
        content=final_message,
        created_at=_utcnow(),
    )
    _append_message(workspace_root, session.session_id, message)
    session = session.model_copy(
        update={
            "transcript": [*session.transcript, message],
            "current_summary": final_message,
            "current_assistant_message": None,
            "planned_assistant_message": None,
            "pending_assistant_message": None,
            "updated_at": message.created_at,
        }
    )
    session = _record_activity(
        workspace_root,
        session,
        RuntimeEventKind.TURN_COMPLETED,
        final_message,
        details={
            "changed_files": session.changed_files,
            "summary": final_message,
        },
    )
    session = _record_activity(
        workspace_root, session, ActivityKind.COMPLETED, session.current_summary or "Turn completed"
    )
    ledger.emit_event(
        EventType.RUN_COMPLETED, payload={"workflow_id": WORKFLOW_ID, "status": "completed"}
    )
    return _set_status(session, SessionStatus.COMPLETED)


def _run_verification_step(
    workspace_root: Path,
    ledger: RunLedger,
    session: CoderSession,
    command: list[str],
    description: str,
) -> tuple[CoderSession, bool]:
    """Run a single verification command and record the result."""
    invoker = _create_invoker(workspace_root, session.trust_mode)
    context = _tool_context(workspace_root)
    session = _record_activity(
        workspace_root,
        session,
        RuntimeEventKind.VERIFICATION_STARTED,
        description,
        details={"command": " ".join(command)},
    )
    result = invoker.invoke(
        "shell.execute", {"command": command, "timeout_seconds": 120}, context, ledger=ledger
    )
    data = _tool_result_data(result)
    exit_code = _command_exit_code(data)
    stdout = str(data.get("stdout", ""))
    stderr = str(data.get("stderr", ""))
    _append_command_result(
        workspace_root,
        session.session_id,
        CoderCommandResult(
            command=command,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            created_at=_utcnow(),
        ),
    )
    if not result.success or exit_code not in (None, 0):
        session = _record_activity(
            workspace_root,
            session,
            RuntimeEventKind.VERIFICATION_FAILED,
            f"Verification failed: {description}",
            details={
                "command": " ".join(command),
                "exit_code": exit_code,
                "stdout": stdout,
                "stderr": stderr,
            },
        )
        return session, False
    session = _record_activity(
        workspace_root,
        session,
        RuntimeEventKind.VERIFICATION_PASSED,
        f"Verification passed: {description}",
        details={"command": " ".join(command), "exit_code": exit_code},
    )
    return session, True


def _run_actions(
    workspace_root: Path,
    ledger: RunLedger,
    session: CoderSession,
    *,
    verify_prompt: str | None = None,
) -> CoderSession:
    while session.next_action_index < len(session.planned_actions):
        action = session.planned_actions[session.next_action_index]
        session, should_continue = _invoke_action(workspace_root, ledger, session, action)
        if not should_continue:
            return session

    # Post-action auto-verification when edits were made
    had_edits = any(a.kind in ("write_file", "apply_patch") for a in session.planned_actions)
    if had_edits and session.verification_profiles and verify_prompt:
        for profile in session.verification_profiles:
            if not profile.detected:
                continue
            for step in profile.steps:
                if not step.required:
                    continue
                session, ok = _run_verification_step(
                    workspace_root, ledger, session, step.command, step.description
                )
                if not ok:
                    return _set_status(session, SessionStatus.BLOCKED)

    return _complete_turn(workspace_root, ledger, session)


def _apply_plan(session: CoderSession, prompt: str, plan: CoderTurnPlan) -> CoderSession:
    return cast(
        CoderSession,
        session.model_copy(
            update={
                "current_user_prompt": prompt,
                "current_assistant_message": None,
                "planned_assistant_message": plan.assistant_message,
                "pending_assistant_message": None,
                "current_summary": plan.summary,
                "planned_actions": plan.actions,
                "next_action_index": 0,
                "pending_approval": None,
                "updated_at": _utcnow(),
            },
        ),
    )
