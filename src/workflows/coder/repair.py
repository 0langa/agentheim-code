from __future__ import annotations

import sys
from pathlib import Path

from core.public_api import EventType, RunLedger
from workflows.coder.action_engine import _apply_plan, _run_actions
from workflows.coder.models import (
    ActivityKind,
    CoderAction,
    CoderSession,
    SessionStatus,
)
from workflows.coder.planner import _plan_turn
from workflows.coder.prompt_builder import _session_has_coding_context
from workflows.coder.session_store import _last_command_result, _record_activity, _set_status
from workflows.coder.verification import _classify_repair_context

WORKFLOW_ID = "coder"


def _repair_failed_verification(
    workspace: Path,
    ledger: RunLedger,
    session: CoderSession,
    original_prompt: str,
    *,
    max_attempts: int = 4,
) -> CoderSession:
    runtime = sys.modules.get("workflows.coder.runtime")
    plan_turn = getattr(runtime, "_plan_turn", _plan_turn) if runtime is not None else _plan_turn
    run_actions = (
        getattr(runtime, "_run_actions", _run_actions) if runtime is not None else _run_actions
    )
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
        repair_ctx = _classify_repair_context(
            list(last_result.command),
            last_result.exit_code,
            last_result.stdout,
            last_result.stderr,
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
            f"Failure type: {repair_ctx.kind.value}\n"
            f"Failure reason: {repair_ctx.message}\n"
            f"stdout:\n{last_result.stdout[-4000:]}\n"
            f"stderr:\n{last_result.stderr[-4000:]}"
        )
        try:
            repair_plan = plan_turn(
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
        session = run_actions(workspace, ledger, session, verify_prompt=original_prompt)
        if session.status != SessionStatus.BLOCKED:
            return session
    return session
