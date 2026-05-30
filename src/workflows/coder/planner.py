from __future__ import annotations

import contextlib
import json
from pathlib import Path
from typing import Any, cast

from config.config import ModelRole, PlannerOutputTokenBudget, load_team_config
from core.public_api import EventType, RunLedger, build_model_registry, repair_json_text
from providers.base import ModelRequest
from workflows.coder.models import (
    CoderAction,
    CoderMode,
    CoderSession,
    CoderTurnPlan,
    canonical_mode,
)
from workflows.coder.prompt_builder import (
    _allow_noop_plan,
    _assistant_message_reads_like_future_intent,
    _mode_planner_guidance,
    _planner_command_guidance,
    _session_has_coding_context,
    _trust_mode_planner_guidance,
    _workspace_action_requested,
    _workspace_scan_summary,
)

PLANNER_OUTPUT_TOKEN_METADATA_KEY = "planner_output_tokens"


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
    return cast(CoderTurnPlan, plan.model_copy(update={"actions": sanitized}))


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


def _coder_output_token_budget(model_config: Any) -> tuple[int, int]:
    """Return configured planner output budgets for full-file JSON plans."""
    metadata = getattr(model_config, "metadata", {}) or {}
    raw_budget = (
        metadata.get(PLANNER_OUTPUT_TOKEN_METADATA_KEY) if isinstance(metadata, dict) else None
    )
    with contextlib.suppress(Exception):
        budget = PlannerOutputTokenBudget.model_validate(raw_budget)
        return budget.first_pass, budget.retry
    default_budget = PlannerOutputTokenBudget()
    return default_budget.first_pass, default_budget.retry


def _parse_turn_plan(raw_content: str) -> CoderTurnPlan:
    return cast(
        CoderTurnPlan, CoderTurnPlan.model_validate(json.loads(repair_json_text(raw_content)))
    )


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
                "enum": ["list_files", "read_file", "write_file", "apply_patch", "run_command"],
            },
            "summary": {"type": "STRING"},
            "path": {"type": "STRING"},
            "content": {"type": "STRING"},
            "content_lines": {"type": "ARRAY", "items": {"type": "STRING"}},
            "content_base64": {"type": "STRING"},
            "patch": {"type": "STRING"},
            "old_string": {"type": "STRING"},
            "new_string": {"type": "STRING"},
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
    return cast(CoderTurnPlan, plan.model_copy(update={"actions": actions}))


def _plan_turn(
    workspace_root: Path,
    session: CoderSession,
    prompt: str,
    *,
    verification_command: list[str] | None = None,
    ledger: RunLedger | None = None,
) -> CoderTurnPlan:
    workspace_summary, _ = _workspace_scan_summary(workspace_root)
    normalized_mode = canonical_mode(session.mode)
    workspace_action_requested = _workspace_action_requested(session, prompt)
    needs_verification = normalized_mode == CoderMode.CODE and _session_has_coding_context(
        session, prompt
    )
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
        'Schema: {"assistant_message":"string","summary":"string","actions":[{"kind":"list_files|read_file|write_file|apply_patch|run_command","summary":"string","path":"optional relative path","content":"optional full file contents","content_lines":["optional file line"],"content_base64":"optional UTF-8 base64 full file contents","patch":"optional full replacement text","old_string":"optional existing text to find","new_string":"optional replacement text","command":["optional","command"]}],"next_actions":["string"]}. '
        "For existing files, prefer apply_patch with old_string + new_string for precise edits instead of full-file write_file. "
        "For new files or complete rewrites, use write_file with full contents in content_lines or content_base64. "
        "Avoid large multiline content strings. "
        "Choose the language, framework, file layout, and architecture that best fit the user's request; do not force a static web app unless that is the right solution. "
        "For empty-workspace project builds, create every necessary source/config/test/doc file in this response; do not promise later file creation. "
        "For non-trivial project builds, include appropriate tests or smoke-check files and clear run instructions for the chosen stack. "
        "Prefer small, justified dependency footprints. If dependencies are needed, add the proper manifest/config files and use normal local setup/test commands for that ecosystem. "
        "For build, fix, refactor, test, or project-creation tasks, include at least one run_command action that verifies the result locally. "
        "Never claim tests, builds, or smoke checks passed unless a run_command action actually runs them. "
        "Respect explicit offline/local-first requirements. Only use package installs, network actions, external URLs, CDNs, remote assets, or generated dependency downloads when the user request or selected stack makes them necessary and policy allows it. "
        f"{_planner_command_guidance()} "
        f"{_mode_planner_guidance(session.mode)} "
        f"{_trust_mode_planner_guidance(session.trust_mode)}"
    )
    user_prompt = (
        f"Workspace summary: {json.dumps(workspace_summary)}\n"
        f"Trust mode: {session.trust_mode.value}\n"
        f"Coder mode: {normalized_mode.value}\n"
        f"Model selection: {session.model_selection.model_dump(mode='json')}\n"
        f"Workspace action requested: {workspace_action_requested}\n"
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
    if plan.actions and _assistant_message_reads_like_future_intent(plan.assistant_message):
        plan = _invoke_planner_json(
            provider=provider,
            role=model_config.role,
            system_prompt=(
                f"{system_prompt} "
                "assistant_message must be the final post-action reply the user sees after all actions finish. "
                "Do not use future tense such as 'I will', 'I'll', or 'let me'."
            ),
            user_prompt=(
                f"{user_prompt}\n\n"
                f"Previous assistant_message sounded like a plan instead of a final reply: {plan.assistant_message}\n"
                "Return a replacement full JSON plan now."
            ),
            max_output_tokens=min(retry_tokens, first_pass_tokens),
            ledger=ledger,
        )
        plan = _sanitize_plan(plan)
    normalized_mode = canonical_mode(session.mode)
    if (
        normalized_mode in {CoderMode.ASK, CoderMode.REVIEW}
        and not workspace_action_requested
        and plan.actions
    ):
        plan = _invoke_planner_json(
            provider=provider,
            role=model_config.role,
            system_prompt=(
                f"{system_prompt} "
                "For this request, respond conversationally and do not use any actions. "
                "Return actions as an empty array."
            ),
            user_prompt=user_prompt,
            max_output_tokens=min(retry_tokens, first_pass_tokens),
            ledger=ledger,
        )
        plan = _sanitize_plan(plan)
        if plan.actions:
            plan = plan.model_copy(update={"actions": []})
    if not plan.actions and workspace_action_requested:
        plan = _invoke_planner_json(
            provider=provider,
            role=model_config.role,
            system_prompt=(
                f"{system_prompt} "
                "The user is explicitly asking you to inspect the local workspace now. "
                "Use the least risky local actions needed to answer honestly. "
                "If read-only inspection is enough, do it without asking for another permission. "
                "Return at least one action when inspection is needed."
            ),
            user_prompt=user_prompt,
            max_output_tokens=min(retry_tokens, first_pass_tokens),
            ledger=ledger,
        )
        plan = _sanitize_plan(plan)
    if not plan.actions and not _allow_noop_plan(session, prompt):
        raise ValueError("Model returned a valid plan with no actions.")
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
