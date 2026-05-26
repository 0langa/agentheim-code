from __future__ import annotations

import contextlib
import json
import os
from datetime import UTC, datetime
from itertools import islice
from pathlib import Path
from typing import Any
from uuid import uuid4

from config.config import ModelRole, load_profiles_document, load_team_config
from core.public_api import (
    ApprovalRequest,
    EventType,
    PolicyConfig,
    PolicyEngine,
    RiskLevel,
    RunLedger,
    ToolContext,
    ToolInvoker,
    build_model_registry,
    inspect_repository,
    repair_json_text,
    safe_project_path,
    safe_run_id,
)
from providers.base import ModelRequest
from tools.registry import create_core_tool_registry
from workflows.coder.commands import command_ids, command_registry
from workflows.coder.models import (
    ActivityKind,
    CoderAction,
    CoderActivity,
    CoderApproval,
    CoderCommandResult,
    CoderDiff,
    CoderEvent,
    CoderMessage,
    CoderMode,
    CoderModelSelection,
    CoderSession,
    CoderSessionView,
    CoderTurnPlan,
    PendingApproval,
    SessionStatus,
    TrustMode,
)

WORKFLOW_ID = "coder"
PRESET_ID = "coder"
SAFE_COMMANDS = ("python", "pytest", "git", "npm", "node", "pip", "poetry", "cargo", "go", "dotnet")
CODING_VERIFICATION_KEYWORDS = (
    "app",
    "application",
    "build",
    "create",
    "fix",
    "from scratch",
    "from the ground up",
    "empty workspace",
    "implement",
    "make",
    "project",
    "refactor",
    "scaffold",
    "test",
    "write code",
)


def _utcnow() -> str:
    return datetime.now(tz=UTC).isoformat()


def _planner_command_guidance(os_name: str | None = None) -> str:
    current_os = os_name or os.name
    allowlist = ", ".join(SAFE_COMMANDS)
    if current_os == "nt":
        return (
            "Current OS is Windows and run_command only allows these executable roots: "
            f"{allowlist}. "
            "Use argv command arrays only. "
            "Do not use sh, bash, cmd, powershell, shell pipelines, or Unix utilities like test, sed, find, ls, cat, grep, or tr. "
            "For file checks or smoke checks, prefer python -c one-liners or framework-native commands that start with an allowed executable."
        )
    return (
        "run_command only allows these executable roots: "
        f"{allowlist}. "
        "Use argv command arrays only and keep verification local."
    )


def _session_paths(workspace_root: Path, session_id: str) -> dict[str, Path]:
    run_dir = workspace_root / ".ai-team" / "runs" / safe_run_id(session_id)
    return {
        "run_dir": run_dir,
        "session": run_dir / "session.json",
        "transcript": run_dir / "transcript.jsonl",
        "activity": run_dir / "activity.jsonl",
        "events": run_dir / "events.jsonl",
        "diffs": run_dir / "diffs.jsonl",
        "commands": run_dir / "commands.jsonl",
        "lock": run_dir / "session.lock",
        "final_report": run_dir / "final_report.json",
        "final_report_md": run_dir / "final_report.md",
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def _policy_config(trust_mode: TrustMode) -> PolicyConfig:
    risk_rules = {
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
        denied_paths=[str(workspace_root / ".git")],
        allowed_commands=list(SAFE_COMMANDS),
        network_allowed=False,
    )


def _load_session(workspace_root: Path, session_id: str) -> CoderSession:
    paths = _session_paths(workspace_root, session_id)
    if not paths["session"].exists():
        raise ValueError(f"Session '{session_id}' not found.")
    data = json.loads(paths["session"].read_text(encoding="utf-8"))
    session = CoderSession.model_validate(data)
    transcript: list[CoderMessage] = []
    if paths["transcript"].exists():
        for line in paths["transcript"].read_text(encoding="utf-8").splitlines():
            if line.strip():
                transcript.append(CoderMessage.model_validate(json.loads(line)))
    activities: list[CoderActivity] = []
    if paths["activity"].exists():
        for line in paths["activity"].read_text(encoding="utf-8").splitlines():
            if line.strip():
                activities.append(CoderActivity.model_validate(json.loads(line)))
    return session.model_copy(update={"transcript": transcript, "activities": activities})


def _save_session(workspace_root: Path, session: CoderSession) -> CoderSession:
    paths = _session_paths(workspace_root, session.session_id)
    paths["run_dir"].mkdir(parents=True, exist_ok=True)
    _write_json(paths["session"], session.model_dump(mode="json"))
    _write_json(
        paths["final_report"],
        {
            "status": (
                "blocked"
                if session.status in {SessionStatus.AWAITING_APPROVAL, SessionStatus.BLOCKED}
                else "done"
                if session.status == SessionStatus.COMPLETED
                else "running"
                if session.status == SessionStatus.RUNNING
                else "failed"
                if session.status == SessionStatus.FAILED
                else "cancelled"
                if session.status == SessionStatus.CANCELLED
                else "pending"
            ),
            "task_summary": session.current_summary or "Coder session",
            "summary": session.current_assistant_message or "Coder session ready.",
            "changed_files": session.changed_files,
            "next_command_suggestions": [
                f"agentheim-code coder resume {session.session_id} --workspace {workspace_root}"
            ],
        },
    )
    paths["final_report_md"].write_text(
        "\n".join(
            [
                f"# Coder Session {session.session_id}",
                "",
                f"- Status: {session.status.value}",
                f"- Workspace: {session.workspace_root}",
                f"- Trust mode: {session.trust_mode.value}",
                "",
                session.current_assistant_message or "Coder session ready.",
            ]
        ),
        encoding="utf-8",
    )
    return session


def _append_message(workspace_root: Path, session_id: str, message: CoderMessage) -> None:
    _append_jsonl(
        _session_paths(workspace_root, session_id)["transcript"], message.model_dump(mode="json")
    )


def _append_activity(workspace_root: Path, session_id: str, activity: CoderActivity) -> None:
    _append_jsonl(
        _session_paths(workspace_root, session_id)["activity"], activity.model_dump(mode="json")
    )


def _append_event(workspace_root: Path, session_id: str, event: CoderEvent) -> None:
    _append_jsonl(
        _session_paths(workspace_root, session_id)["events"], event.model_dump(mode="json")
    )


def _append_diff(workspace_root: Path, session_id: str, diff: CoderDiff) -> None:
    _append_jsonl(_session_paths(workspace_root, session_id)["diffs"], diff.model_dump(mode="json"))


def _append_command_result(
    workspace_root: Path, session_id: str, result: CoderCommandResult
) -> None:
    _append_jsonl(
        _session_paths(workspace_root, session_id)["commands"], result.model_dump(mode="json")
    )


def _last_command_result(workspace_root: Path, session_id: str) -> CoderCommandResult | None:
    results = _read_jsonl_model(
        _session_paths(workspace_root, session_id)["commands"], CoderCommandResult
    )
    return results[-1] if results else None


def _tool_result_data(result: Any) -> dict[str, Any]:
    if hasattr(result.data, "model_dump"):
        return result.data.model_dump()
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


def _read_jsonl_model(path: Path, model_type):
    items = []
    if not path.exists():
        return items
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            items.append(model_type.model_validate(json.loads(line)))
    return items


def _record_activity(
    workspace_root: Path,
    session: CoderSession,
    kind: ActivityKind,
    message: str,
    details: dict[str, str] | None = None,
    request_id: str = "",
) -> CoderSession:
    activity = CoderActivity(
        kind=kind, message=message, created_at=_utcnow(), details=details or {}
    )
    _append_activity(workspace_root, session.session_id, activity)
    event_details = dict(details or {})
    if request_id:
        event_details["request_id"] = request_id
    _append_event(
        workspace_root,
        session.session_id,
        CoderEvent(
            event_id=uuid4().hex,
            kind=kind.value,
            message=message,
            created_at=activity.created_at,
            details=event_details,
        ),
    )
    activities = [*session.activities, activity]
    return session.model_copy(update={"activities": activities, "updated_at": activity.created_at})


def _set_status(session: CoderSession, status: SessionStatus) -> CoderSession:
    return session.model_copy(update={"status": status, "updated_at": _utcnow()})


def _workspace_scan_summary(workspace_root: Path) -> tuple[dict[str, Any], bool]:
    scan = inspect_repository(workspace_root)
    summary = {
        "repo_name": scan.repo_name,
        "languages": scan.languages,
        "manifests": scan.manifests,
        "warnings": scan.warnings,
        "file_count": len(scan.files),
        "git_available": scan.git.is_git_repo,
    }
    return summary, scan.git.is_git_repo


def _open_ledger(workspace_root: Path, session_id: str) -> RunLedger:
    ledger = RunLedger(
        repo_root=workspace_root, run_dir=_session_paths(workspace_root, session_id)["run_dir"]
    )
    if (ledger.run_dir / "ledger.jsonl").exists():
        ledger._restore_sequence_from_ledger()  # type: ignore[attr-defined]
    return ledger


def _command_ids() -> list[str]:
    return command_ids()


def available_commands() -> list[dict[str, str]]:
    return command_registry()


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


def _requires_coding_verification(prompt: str) -> bool:
    lowered = prompt.lower()
    return any(keyword in lowered for keyword in CODING_VERIFICATION_KEYWORDS)


def _session_has_coding_context(session: CoderSession, prompt: str) -> bool:
    if _requires_coding_verification(prompt):
        return True
    return any(
        message.role == "user" and _requires_coding_verification(message.content)
        for message in session.transcript
    )


def _plan_has_verification(plan: CoderTurnPlan) -> bool:
    return any(action.kind == "run_command" and action.command for action in plan.actions)


def _write_file_content_issues(plan: CoderTurnPlan) -> list[str]:
    issues: list[str] = []
    for index, action in enumerate(plan.actions):
        if action.kind != "write_file":
            continue
        target = action.path or f"write_file[{index}]"
        if not action.path:
            issues.append(f"{target}: missing path")
        elif not (action.content or "").strip():
            issues.append(f"{target}: missing non-empty content")
    return issues


def _sanitize_plan(plan: CoderTurnPlan) -> CoderTurnPlan:
    sanitized: list[CoderAction] = []
    for action in plan.actions:
        if action.kind == "run_command" and action.command:
            executable = action.command[0].lower()
            if executable in {"mkdir", "md"}:
                continue
        sanitized.append(action)
    return plan.model_copy(update={"actions": sanitized})


def _offline_violations(plan: CoderTurnPlan, prompt: str) -> list[str]:
    lowered = prompt.lower()
    if "offline" not in lowered and "do not use the network" not in lowered:
        return []
    violations: list[str] = []
    for action in plan.actions:
        if (
            action.kind == "write_file"
            and action.path
            and action.content
            and ("http://" in action.content or "https://" in action.content)
        ):
            violations.append(action.path)
    return violations


def _mode_allows_noop_plan(mode: CoderMode) -> bool:
    return mode in {CoderMode.ASK, CoderMode.PLAN, CoderMode.REVIEW, CoderMode.DOCS}


class _SessionLock:
    def __init__(self, workspace_root: Path, session_id: str) -> None:
        self.path = _session_paths(workspace_root, session_id)["lock"]

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise RuntimeError(f"Coder session already running: {self.path.parent.name}") from exc
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(_utcnow())
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        with contextlib.suppress(FileNotFoundError):
            self.path.unlink()


def _coder_output_token_budget(model_config: Any) -> tuple[int, int]:
    """Return provider-safe planner output budgets for full-file JSON plans."""
    provider = str(getattr(model_config, "provider", "")).lower()
    model = str(getattr(model_config, "model", "")).lower()
    if provider == "bedrock" or "nova" in model:
        return 9000, 9000
    if provider == "oci-genai":
        return 3000, 5000
    if "gemini" in model:
        return 6000, 8000
    return 12000, 16000


def _parse_turn_plan(raw_content: str) -> CoderTurnPlan:
    return CoderTurnPlan.model_validate(json.loads(repair_json_text(raw_content)))


def _content_preview(content: str, limit: int = 500) -> str:
    preview = content.replace("\r", "\\r").replace("\n", "\\n")
    if len(preview) > limit:
        preview = preview[:limit] + "...[truncated]"
    return preview


def _compact_planner_user_prompt(user_prompt: str) -> str:
    marker = "User prompt:"
    if marker in user_prompt:
        return user_prompt[user_prompt.rfind(marker) :].strip()
    return user_prompt[-2000:]


def _turn_plan_response_schema() -> dict[str, Any]:
    action_schema = {
        "type": "OBJECT",
        "properties": {
            "kind": {
                "type": "STRING",
                "enum": ["list_files", "read_file", "write_file", "run_command"],
            },
            "summary": {"type": "STRING"},
            "path": {"type": "STRING"},
            "content": {"type": "STRING"},
            "content_lines": {"type": "ARRAY", "items": {"type": "STRING"}},
            "content_base64": {"type": "STRING"},
            "command": {"type": "ARRAY", "items": {"type": "STRING"}},
        },
        "required": ["kind", "summary"],
    }
    return {
        "type": "OBJECT",
        "properties": {
            "assistant_message": {"type": "STRING"},
            "summary": {"type": "STRING"},
            "actions": {"type": "ARRAY", "items": action_schema},
            "next_actions": {"type": "ARRAY", "items": {"type": "STRING"}},
        },
        "required": ["assistant_message", "summary", "actions"],
    }


def _invoke_planner_json(
    *,
    provider: Any,
    role: str,
    system_prompt: str,
    user_prompt: str,
    max_output_tokens: int,
    ledger: RunLedger | None = None,
) -> CoderTurnPlan:
    request = ModelRequest(
        role=role,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=0.0,
        max_output_tokens=max_output_tokens,
        response_schema=_turn_plan_response_schema(),
    )
    response = provider.invoke(request)
    if response.usage and ledger is not None:
        ledger.emit_event(
            EventType.AGENT_INVOKED,
            payload={
                "model": response.model,
                "provider": response.provider,
                "usage": response.usage.to_dict(),
            },
        )
    if not response.content or not response.content.strip():
        raise ValueError("Provider returned an empty response.")
    if (
        response.usage
        and max_output_tokens
        and response.usage.output_tokens >= int(max_output_tokens * 0.95)
    ):
        raise ValueError(
            f"Provider response may be truncated: output_tokens={response.usage.output_tokens} "
            f"approaches max_output_tokens={max_output_tokens}."
        )
    try:
        return _parse_turn_plan(response.content)
    except Exception as exc:
        retry = ModelRequest(
            role=role,
            system_prompt=(
                f"{system_prompt} "
                "Your previous response was not parseable JSON. For write_file actions, use content_base64 "
                "containing UTF-8 base64 file bytes instead of content/content_lines whenever quoting source code is risky. "
                "Every array item must be a valid JSON string. Return only a complete replacement JSON object."
            ),
            user_prompt=f"{user_prompt}\n\nJSON parse error from previous response: {type(exc).__name__}: {exc}",
            temperature=0.0,
            max_output_tokens=max_output_tokens,
            response_schema=_turn_plan_response_schema(),
        )
        retry_response = provider.invoke(retry)
        if retry_response.usage and ledger is not None:
            ledger.emit_event(
                EventType.AGENT_INVOKED,
                payload={
                    "model": retry_response.model,
                    "provider": retry_response.provider,
                    "usage": retry_response.usage.to_dict(),
                },
            )
        try:
            return _parse_turn_plan(retry_response.content)
        except Exception as retry_exc:
            compact = ModelRequest(
                role=role,
                system_prompt=(
                    "Return JSON only. Build a tiny complete project plan. "
                    "Keys: assistant_message, summary, actions, next_actions. "
                    "Actions use kind, summary, path, content, command. "
                    "Use at most two write_file actions and one run_command."
                ),
                user_prompt=_compact_planner_user_prompt(user_prompt),
                temperature=0.0,
                max_output_tokens=min(max_output_tokens, 3000),
            )
            compact_response = provider.invoke(compact)
            if compact_response.usage and ledger is not None:
                ledger.emit_event(
                    EventType.AGENT_INVOKED,
                    payload={
                        "model": compact_response.model,
                        "provider": compact_response.provider,
                        "usage": compact_response.usage.to_dict(),
                    },
                )
            try:
                return _parse_turn_plan(compact_response.content)
            except Exception as compact_exc:
                compact_preview = _content_preview(compact_response.content)
                retry_preview = _content_preview(retry_response.content)
                raise ValueError(
                    "Model did not return parseable coder JSON after retries. "
                    f"First error: {type(exc).__name__}: {exc}. "
                    f"Retry error: {type(retry_exc).__name__}: {retry_exc}. "
                    f"Retry output preview: {retry_preview}. "
                    f"Compact retry error: {type(compact_exc).__name__}: {compact_exc}. "
                    f"Compact output preview: {compact_preview}"
                ) from compact_exc


def _clean_raw_file_content(content: str) -> str:
    text = content.strip()
    if text.startswith("```"):
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1 :]
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    if text.startswith("{") and text.endswith("}"):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            value = parsed.get("content") or parsed.get("file_content")
            if isinstance(value, str):
                text = value.strip()
    if not text.endswith("\n"):
        text += "\n"
    return text


def _fill_missing_write_contents(
    *,
    provider: Any,
    role: str,
    prompt: str,
    plan: CoderTurnPlan,
    max_output_tokens: int,
    ledger: RunLedger | None = None,
) -> CoderTurnPlan:
    planned_files = [
        {"path": action.path, "summary": action.summary}
        for action in plan.actions
        if action.kind == "write_file"
    ]
    actions: list[CoderAction] = []
    for action in plan.actions:
        if action.kind != "write_file" or not action.path or (action.content or "").strip():
            actions.append(action)
            continue
        response = provider.invoke(
            ModelRequest(
                role=role,
                system_prompt=(
                    "You are Agentheim Code generating one project file. "
                    "Return only the complete raw file content. No markdown fences, no JSON, no commentary."
                ),
                user_prompt=(
                    f"Original user request:\n{prompt}\n\n"
                    f"Planned project files:\n{json.dumps(planned_files, indent=2)}\n\n"
                    f"Generate complete content for: {action.path}\n"
                    f"File purpose: {action.summary}"
                ),
                temperature=0.0,
                max_output_tokens=max_output_tokens,
            )
        )
        if response.usage and ledger is not None:
            ledger.emit_event(
                EventType.AGENT_INVOKED,
                payload={
                    "model": response.model,
                    "provider": response.provider,
                    "usage": response.usage.to_dict(),
                },
            )
        content = _clean_raw_file_content(response.content)
        actions.append(action.model_copy(update={"content": content}))
    return plan.model_copy(update={"actions": actions})


def _plan_turn(
    workspace_root: Path,
    session: CoderSession,
    prompt: str,
    *,
    verification_command: list[str] | None = None,
    ledger: RunLedger | None = None,
) -> CoderTurnPlan:
    workspace_summary, _ = _workspace_scan_summary(workspace_root)
    config = load_team_config(
        profile=session.model_selection.profile
        if session.model_selection.profile != "auto"
        else None
    )
    registry = build_model_registry(config)
    planner_model = registry.resolve_model(ModelRole.PLANNER.value, "json")
    model_config = planner_model.config
    if session.model_selection.provider != "auto" or session.model_selection.model != "auto":
        model_config = model_config.model_copy(
            update={
                "provider": session.model_selection.provider
                if session.model_selection.provider != "auto"
                else model_config.provider,
                "model": session.model_selection.model
                if session.model_selection.model != "auto"
                else model_config.model,
            }
        )
    provider = registry.create_provider(model_config)
    first_pass_tokens, retry_tokens = _coder_output_token_budget(model_config)
    system_prompt = (
        "You are Agentheim Code, a local coding agent. Return only valid JSON, no markdown, no prose outside JSON. "
        'Schema: {"assistant_message":"string","summary":"string","actions":[{"kind":"list_files|read_file|write_file|run_command","summary":"string","path":"optional relative path","content":"optional full file contents","content_lines":["optional file line"],"content_base64":"optional UTF-8 base64 full file contents","command":["optional","command"]}],"next_actions":["string"]}. '
        "For write_file actions, put the full file contents in content_lines or content_base64. Avoid large multiline content strings. "
        "Choose the language, framework, file layout, and architecture that best fit the user's request; do not force a static web app unless that is the right solution. "
        "For empty-workspace project builds, create every necessary source/config/test/doc file in this response; do not promise later file creation. "
        "For non-trivial project builds, include appropriate tests or smoke-check files and clear run instructions for the chosen stack. "
        "Prefer small, justified dependency footprints. If dependencies are needed, add the proper manifest/config files and use normal local setup/test commands for that ecosystem. "
        "For build, fix, refactor, test, or project-creation tasks, include at least one run_command action that verifies the result locally. "
        "Never claim tests, builds, or smoke checks passed unless a run_command action actually runs them. "
        "Respect explicit offline/local-first requirements. Only use package installs, network actions, external URLs, CDNs, remote assets, or generated dependency downloads when the user request or selected stack makes them necessary and policy allows it. "
        f"{_planner_command_guidance()}"
    )
    user_prompt = (
        f"Workspace summary: {json.dumps(workspace_summary)}\n"
        f"Trust mode: {session.trust_mode.value}\n"
        f"Coder mode: {session.mode.value}\n"
        f"Model selection: {session.model_selection.model_dump(mode='json')}\n"
        f"Transcript tail: {[m.model_dump(mode='json') for m in session.transcript[-6:]]}\n"
        f"User prompt: {prompt}"
    )
    plan = _invoke_planner_json(
        provider=provider,
        role=model_config.role,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        max_output_tokens=first_pass_tokens,
        ledger=ledger,
    )
    plan = _sanitize_plan(plan)
    if not plan.actions and not _mode_allows_noop_plan(session.mode):
        raise ValueError("Model returned a valid plan with no actions.")
    needs_verification = _session_has_coding_context(session, prompt)
    write_issues = _write_file_content_issues(plan)
    if write_issues:
        plan = _fill_missing_write_contents(
            provider=provider,
            role=model_config.role,
            prompt=prompt,
            plan=plan,
            max_output_tokens=max(retry_tokens, 12000),
            ledger=ledger,
        )
        plan = _sanitize_plan(plan)
        write_issues = _write_file_content_issues(plan)
    offline_violations = _offline_violations(plan, prompt)
    if (
        (needs_verification and not _plan_has_verification(plan))
        or write_issues
        or offline_violations
    ):
        plan = _invoke_planner_json(
            provider=provider,
            role=model_config.role,
            system_prompt=system_prompt,
            user_prompt=(
                f"{user_prompt}\n\n"
                "Previous JSON did not meet the universal coding-agent contract. "
                f"Needs local verification command: {needs_verification}. "
                f"Has local verification command: {_plan_has_verification(plan)}. "
                f"Invalid write_file actions: {write_issues}. "
                f"Files with forbidden external URL references for explicit offline/local prompt: {offline_violations}. "
                "Return a replacement full JSON plan now. Keep the best language/framework for the task, include all needed files, "
                "include non-empty file content for every write_file action, and include a real local run_command verification when required."
            ),
            max_output_tokens=retry_tokens,
            ledger=ledger,
        )
        plan = _sanitize_plan(plan)
        if needs_verification and not _plan_has_verification(plan):
            if verification_command:
                plan = plan.model_copy(
                    update={
                        "actions": [
                            *plan.actions,
                            CoderAction(
                                kind="run_command",
                                summary="Rerun the previously failed verification command.",
                                command=verification_command,
                            ),
                        ]
                    }
                )
            else:
                raise ValueError(
                    "Model returned a coding plan without a local verification command."
                )
        write_issues = _write_file_content_issues(plan)
        if write_issues:
            raise ValueError(
                "Model returned invalid write_file actions: " + "; ".join(write_issues)
            )
        offline_violations = _offline_violations(plan, prompt)
        if offline_violations:
            raise ValueError(
                "Model returned external URL references despite an explicit offline/local prompt: "
                + ", ".join(offline_violations)
            )
    return plan


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
    activity_kind = ActivityKind.THINKING
    if action.kind == "list_files":
        params = {"operation": "list", "path": action.path or "."}
        activity_kind = ActivityKind.SCANNING
    elif action.kind == "read_file":
        params = {"operation": "read", "path": action.path or "."}
        activity_kind = ActivityKind.SCANNING
    elif action.kind == "write_file":
        params = {"operation": "write", "path": action.path or ".", "content": action.content or ""}
        activity_kind = ActivityKind.EDITING
    elif action.kind == "run_command":
        tool_id = "shell.execute"
        params = {"command": action.command, "timeout_seconds": 120}
        activity_kind = ActivityKind.RUNNING
    else:
        session = _record_activity(
            workspace_root, session, ActivityKind.BLOCKED, f"Unsupported action kind: {action.kind}"
        )
        return _set_status(session, SessionStatus.FAILED), False

    session = _record_activity(
        workspace_root, session, activity_kind, action.summary or action.kind
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
        session = session.model_copy(update={"pending_approval": pending})
        session = _record_activity(workspace_root, session, ActivityKind.AWAITING_APPROVAL, reason)
        return _set_status(session, SessionStatus.AWAITING_APPROVAL), False
    if not result.success:
        session = _record_activity(
            workspace_root, session, ActivityKind.BLOCKED, result.error or f"{tool_id} failed"
        )
        return _set_status(session, SessionStatus.BLOCKED), False

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
                ActivityKind.BLOCKED,
                f"Command failed with exit code {exit_code}: {' '.join(action.command)}",
            )
            return _set_status(session, SessionStatus.BLOCKED), False
    session = session.model_copy(
        update={
            "changed_files": changed_files,
            "next_action_index": session.next_action_index + 1,
            "updated_at": _utcnow(),
        }
    )
    return session, True


def _complete_turn(workspace_root: Path, ledger: RunLedger, session: CoderSession) -> CoderSession:
    message = CoderMessage(
        role="assistant",
        content=session.current_assistant_message or "Coder turn completed.",
        created_at=_utcnow(),
    )
    _append_message(workspace_root, session.session_id, message)
    session = session.model_copy(
        update={"transcript": [*session.transcript, message], "updated_at": message.created_at}
    )
    session = _record_activity(
        workspace_root, session, ActivityKind.COMPLETED, session.current_summary or "Turn completed"
    )
    ledger.emit_event(
        EventType.RUN_COMPLETED, payload={"workflow_id": WORKFLOW_ID, "status": "completed"}
    )
    return _set_status(session, SessionStatus.COMPLETED)


def _run_actions(
    workspace_root: Path,
    ledger: RunLedger,
    session: CoderSession,
    *,
    verify_prompt: str | None = None,
) -> CoderSession:
    _ = verify_prompt
    while session.next_action_index < len(session.planned_actions):
        action = session.planned_actions[session.next_action_index]
        session, should_continue = _invoke_action(workspace_root, ledger, session, action)
        if not should_continue:
            return session
    return _complete_turn(workspace_root, ledger, session)


def _apply_plan(session: CoderSession, prompt: str, plan: CoderTurnPlan) -> CoderSession:
    return session.model_copy(
        update={
            "current_user_prompt": prompt,
            "current_assistant_message": plan.assistant_message,
            "current_summary": plan.summary,
            "planned_actions": plan.actions,
            "next_action_index": 0,
            "pending_approval": None,
            "updated_at": _utcnow(),
        }
    )


def _repair_failed_verification(
    workspace: Path,
    ledger: RunLedger,
    session: CoderSession,
    original_prompt: str,
    *,
    max_attempts: int = 4,
) -> CoderSession:
    if session.status != SessionStatus.BLOCKED or not _session_has_coding_context(
        session, original_prompt
    ):
        return session
    for attempt in range(1, max_attempts + 1):
        last_result = _last_command_result(workspace, session.session_id)
        if last_result is None or last_result.exit_code in (None, 0):
            return session
        session = _set_status(session, SessionStatus.RUNNING)
        session = session.model_copy(
            update={
                "repair_attempts": attempt,
                "last_verification_command": list(last_result.command),
                "last_verification_exit_code": last_result.exit_code,
            }
        )
        session = _record_activity(
            workspace,
            session,
            ActivityKind.THINKING,
            f"Repairing failed verification ({attempt}/{max_attempts}).",
        )
        repair_prompt = (
            "Repair the current workspace so it satisfies the user's original coding request. "
            "Keep the chosen language, framework, and architecture unless changing them is the smallest reliable fix. "
            "Prefer dependency-light local changes, but use the correct ecosystem tools when the project requires them. "
            "Inspect/read the relevant current files when needed so implementation, tests, and CLI commands agree. "
            "Do not claim success unless you include and run a local verification command. "
            "Rewrite only the files needed to fix the failure.\n\n"
            f"Original request:\n{original_prompt}\n\n"
            f"Failed command: {' '.join(last_result.command)}\n"
            f"Exit code: {last_result.exit_code}\n"
            f"stdout:\n{last_result.stdout[-4000:]}\n"
            f"stderr:\n{last_result.stderr[-4000:]}"
        )
        try:
            repair_plan = _plan_turn(
                workspace,
                session,
                repair_prompt,
                verification_command=list(last_result.command),
                ledger=ledger,
            )
            if not any(action.command == last_result.command for action in repair_plan.actions):
                repair_plan = repair_plan.model_copy(
                    update={
                        "actions": [
                            *repair_plan.actions,
                            CoderAction(
                                kind="run_command",
                                summary="Rerun the previously failed verification command.",
                                command=list(last_result.command),
                            ),
                        ]
                    }
                )
        except Exception as exc:
            ledger.emit_event(
                EventType.RUN_FAILED,
                payload={
                    "workflow_id": WORKFLOW_ID,
                    "reason": str(exc),
                    "error_type": type(exc).__name__,
                },
            )
            failed = session.model_copy(
                update={
                    "current_summary": "Coder repair failed",
                    "current_assistant_message": str(exc),
                    "last_failure_reason": str(exc),
                }
            )
            return _set_status(failed, SessionStatus.FAILED)
        session = _apply_plan(session, repair_prompt, repair_plan)
        session = _run_actions(workspace, ledger, session, verify_prompt=original_prompt)
        if session.status != SessionStatus.BLOCKED:
            return session
    return session


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
    scan_summary, git_available = _workspace_scan_summary(workspace)
    ledger = RunLedger.create(workspace, "coder")
    session = CoderSession(
        session_id=ledger.run_dir.name,
        workspace_root=str(workspace),
        trust_mode=trust,
        mode=CoderMode(mode),
        model_selection=_normalize_model_selection(profile=profile, provider=provider, model=model),
        created_at=_utcnow(),
        updated_at=_utcnow(),
        git_available=git_available,
    )
    run_json_payload: dict[str, Any] = {
        "run_id": session.session_id,
        "product": "agentheim-code",
        "workflow_id": WORKFLOW_ID,
        "preset_id": PRESET_ID,
        "repo_root": str(workspace),
        "created_at": session.created_at,
        "trust_mode": trust.value,
        "mode": mode,
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


def _artifacts(workspace: Path, session_id: str) -> list[str]:
    run_dir = _session_paths(workspace, session_id)["run_dir"]
    if not run_dir.exists():
        return []
    return sorted(path.name for path in run_dir.iterdir() if path.is_file())


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


def _iter_file_tree_entries(workspace: Path):
    for root, dirnames, filenames in os.walk(workspace):
        current = Path(root)
        relative_root = current.relative_to(workspace)
        dirnames[:] = sorted(name for name in dirnames if name not in {".ai-team", ".git"})
        for dirname in dirnames:
            path = (relative_root / dirname).as_posix()
            yield {"path": path, "type": "directory"}
        for filename in sorted(filenames):
            path = (relative_root / filename).as_posix()
            yield {"path": path, "type": "file"}


def browse_file_tree(
    workspace_root: str | Path,
    *,
    offset: int = 0,
    limit: int = 100,
    query: str = "",
) -> tuple[list[dict[str, Any]], int | None]:
    workspace = safe_project_path(workspace_root)
    normalized_query = query.strip().lower()
    bounded_offset = max(offset, 0)
    bounded_limit = max(1, limit)

    def filtered_entries():
        for item in _iter_file_tree_entries(workspace):
            if normalized_query and normalized_query not in str(item["path"]).lower():
                continue
            yield item

    window = list(islice(filtered_entries(), bounded_offset, bounded_offset + bounded_limit + 1))
    has_more = len(window) > bounded_limit
    items = window[:bounded_limit]
    next_offset = bounded_offset + bounded_limit if has_more else None
    return items, next_offset


def list_file_tree(workspace_root: str | Path, *, limit: int = 500) -> list[dict[str, Any]]:
    items, _ = browse_file_tree(workspace_root, offset=0, limit=limit)
    return items


def cancel_session(
    workspace_root: str | Path, session_id: str, *, request_id: str = ""
) -> CoderSession:
    workspace = safe_project_path(workspace_root)
    session = _load_session(workspace, session_id)
    session = session.model_copy(update={"pending_approval": None})
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
        session = _set_status(session, SessionStatus.IDLE)
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


def set_session_mode(workspace_root: str | Path, session_id: str, mode: str) -> CoderSession:
    workspace = safe_project_path(workspace_root)
    session = _load_session(workspace, session_id)
    updated = session.model_copy(update={"mode": CoderMode(mode), "updated_at": _utcnow()})
    updated = _record_activity(workspace, updated, ActivityKind.THINKING, f"Mode changed: {mode}")
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
        except Exception as exc:
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
        session = _repair_failed_verification(workspace, ledger, session, prompt)
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
        session = session.model_copy(update={"pending_approval": None})
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
        session = session.model_copy(update={"pending_approval": None})
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
            "changed_files": changed_files,
            "next_action_index": pending.action_index + 1,
            "updated_at": _utcnow(),
        }
    )
    session = _run_actions(workspace, ledger, _set_status(session, SessionStatus.RUNNING))
    return _save_session(workspace, session)
