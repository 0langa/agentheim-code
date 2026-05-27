from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from core.ledger import RunLedger
from workflows.coder import runtime
from workflows.coder.models import (
    CoderAction,
    CoderMode,
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


def test_mode_allows_noop_plan_for_non_coding_modes() -> None:
    assert runtime._mode_allows_noop_plan(CoderMode.ASK) is True
    assert runtime._mode_allows_noop_plan(CoderMode.PLAN) is True
    assert runtime._mode_allows_noop_plan(CoderMode.REVIEW) is True
    assert runtime._mode_allows_noop_plan(CoderMode.CODE) is False
    assert runtime._mode_allows_noop_plan(CoderMode.DOCS) is False
    assert runtime._mode_allows_noop_plan(CoderMode.FIX) is False
    assert runtime._mode_allows_noop_plan(CoderMode.TEST) is False


def test_canonical_mode_maps_legacy_aliases() -> None:
    assert runtime.canonical_mode(CoderMode.PLAN) == CoderMode.ASK
    assert runtime.canonical_mode(CoderMode.FIX) == CoderMode.CODE
    assert runtime.canonical_mode(CoderMode.DOCS) == CoderMode.CODE
    assert runtime.canonical_mode(CoderMode.TEST) == CoderMode.CODE


def test_create_session_normalizes_legacy_mode(tmp_path: Path) -> None:
    session = runtime.create_session(tmp_path, mode="plan", trust_mode="ask")

    assert session.mode == CoderMode.ASK


def test_post_message_persists_exactly_one_user_and_one_assistant_message(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    session = runtime.create_session(tmp_path, mode="ask", trust_mode="ask")

    monkeypatch.setattr(
        runtime,
        "_plan_turn",
        lambda *args, **kwargs: CoderTurnPlan(
            assistant_message="Here is the answer you asked for.",
            summary="Answered the question.",
            actions=[],
        ),
    )

    updated = runtime.post_message(tmp_path, session.session_id, "What changed?")
    reloaded = runtime.get_session(tmp_path, session.session_id)

    assert updated.status == SessionStatus.COMPLETED
    assert len(reloaded.transcript) == 2
    assert [message.role for message in reloaded.transcript] == ["user", "assistant"]
    assert reloaded.transcript[0].content == "What changed?"
    assert reloaded.transcript[1].content == "Here is the answer you asked for."


def test_planner_command_guidance_for_windows_avoids_shell_wrappers() -> None:
    guidance = runtime._planner_command_guidance("nt")

    assert "python, pytest, git, npm, node, pip, poetry, cargo, go, dotnet" in guidance
    assert "Do not use sh, bash, cmd, powershell" in guidance
    assert "python -c" in guidance


def test_prompt_explicitly_requests_workspace_action_detects_real_actions() -> None:
    assert runtime._prompt_explicitly_requests_workspace_action(
        "Create a file named note.txt in this workspace."
    )
    assert not runtime._prompt_explicitly_requests_workspace_action(
        "Review this proposed tiny app in two short bullet points."
    )


def test_complete_turn_clears_draft_message_after_persisting_reply(tmp_path: Path) -> None:
    ledger = RunLedger.create(tmp_path, "coder")
    session = CoderSession(
        session_id=ledger.run_dir.name,
        workspace_root=str(tmp_path),
        trust_mode=TrustMode.WORKSPACE,
        created_at=runtime._utcnow(),
        updated_at=runtime._utcnow(),
        planned_assistant_message="Final answer",
        current_assistant_message="Draft answer",
    )

    completed = runtime._complete_turn(tmp_path, ledger, session)

    assert completed.status == SessionStatus.COMPLETED
    assert completed.current_assistant_message is None
    assert completed.planned_assistant_message is None
    assert completed.transcript[-1].content == "Final answer"


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
