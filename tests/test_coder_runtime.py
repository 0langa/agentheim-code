from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from core.ledger import RunLedger
from workflows.coder import runtime
from workflows.coder.models import (
    CoderAction,
    CoderSession,
    CoderTurnPlan,
    SessionStatus,
    TrustMode,
)


def _session(tmp_path: Path) -> CoderSession:
    ledger = RunLedger.create(tmp_path, "coder")
    return CoderSession(
        session_id=ledger.run_dir.name,
        workspace_root=str(tmp_path),
        trust_mode=TrustMode.WORKSPACE,
        created_at=runtime._utcnow(),
        updated_at=runtime._utcnow(),
    )


def test_coding_verification_detects_empty_workspace_project() -> None:
    assert runtime._requires_coding_verification(
        "Build a small desktop app from an empty workspace."
    )
    assert not runtime._requires_coding_verification("Explain how this repository is organized.")


def test_coder_action_accepts_base64_content() -> None:
    action = CoderAction(
        kind="write_file",
        path="main.py",
        summary="write source",
        content_base64=base64.b64encode(b'print("hello")\n').decode("ascii"),
    )

    assert action.content == 'print("hello")\n'


def test_coder_action_accepts_provider_aliases() -> None:
    action = CoderAction.model_validate(
        {
            "type": "write_file",
            "file_path": "todo.py",
            "summary": "write file",
            "content": "print('ok')\n",
        }
    )

    assert action.kind == "write_file"
    assert action.path == "todo.py"


def test_repair_uses_prior_coding_context(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    session = _session(tmp_path)
    runtime._append_message(
        tmp_path,
        session.session_id,
        runtime.CoderMessage(
            role="user",
            content="Build a simple app from an empty workspace.",
            created_at=runtime._utcnow(),
        ),
    )
    runtime._append_command_result(
        tmp_path,
        session.session_id,
        runtime.CoderCommandResult(
            command=["node", "tests/smoke-test.js"],
            exit_code=1,
            stdout="",
            stderr="boom",
            created_at=runtime._utcnow(),
        ),
    )
    session = session.model_copy(
        update={
            "status": SessionStatus.BLOCKED,
            "transcript": [
                runtime.CoderMessage(
                    role="user",
                    content="Build a simple CLI app from an empty workspace.",
                    created_at=runtime._utcnow(),
                )
            ],
        }
    )
    ledger = runtime._open_ledger(tmp_path, session.session_id)

    def fake_plan(*args: Any, **kwargs: Any) -> CoderTurnPlan:
        return CoderTurnPlan(
            assistant_message="repair",
            summary="repair",
            actions=[CoderAction(kind="run_command", summary="verify", command=["node", "-v"])],
        )

    observed_commands: list[list[str]] = []

    def fake_run_actions(*args: Any, **kwargs: Any) -> CoderSession:
        current = args[2]
        observed_commands.extend(
            action.command for action in current.planned_actions if action.kind == "run_command"
        )
        return current.model_copy(update={"status": SessionStatus.COMPLETED})

    monkeypatch.setattr(runtime, "_plan_turn", fake_plan)
    monkeypatch.setattr(runtime, "_run_actions", fake_run_actions)

    repaired = runtime._repair_failed_verification(
        tmp_path,
        ledger,
        session,
        "continue fixing tests",
    )

    assert repaired.status == SessionStatus.COMPLETED
    assert ["node", "tests/smoke-test.js"] in observed_commands
