from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

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


def test_session_lock_replaces_dead_pid_lock(tmp_path: Path) -> None:
    session = _session(tmp_path)
    lock_path = runtime._session_paths(tmp_path, session.session_id)["lock"]
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(
        json.dumps({"pid": 999_999_999, "created_at": runtime._utcnow()}),
        encoding="utf-8",
    )

    with runtime._SessionLock(tmp_path, session.session_id):
        payload = json.loads(lock_path.read_text(encoding="utf-8"))
        assert payload["pid"] == os.getpid()

    assert not lock_path.exists()


def test_session_lock_blocks_live_pid_lock(tmp_path: Path) -> None:
    session = _session(tmp_path)
    lock_path = runtime._session_paths(tmp_path, session.session_id)["lock"]
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(
        json.dumps({"pid": os.getpid(), "created_at": runtime._utcnow()}),
        encoding="utf-8",
    )

    with (
        pytest.raises(RuntimeError, match="already running"),
        runtime._SessionLock(tmp_path, session.session_id),
    ):
        pass


def test_coder_output_token_budget_reads_model_config_metadata() -> None:
    model_config = SimpleNamespace(
        provider="custom",
        model="neutral-model",
        metadata={"planner_output_tokens": {"first_pass": 1234, "retry": 5678}},
    )

    assert runtime._coder_output_token_budget(model_config) == (1234, 5678)


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


def test_workspace_action_request_detects_affirmative_follow_up_after_permission_prompt(
    tmp_path: Path,
) -> None:
    session = _session(tmp_path).model_copy(
        update={
            "transcript": [
                runtime.CoderMessage(
                    role="assistant",
                    content=(
                        "I can inspect the workspace files and run a smoke test if you want me to "
                        "check whether anything looks broken."
                    ),
                    created_at=runtime._utcnow(),
                )
            ]
        }
    )

    assert runtime._workspace_action_requested(session, "Yes, please do that now.") is True


def test_code_mode_allows_noop_plan_for_plain_conversational_prompts(tmp_path: Path) -> None:
    session = _session(tmp_path).model_copy(update={"mode": CoderMode.CODE})

    assert runtime._allow_noop_plan(session, "Hello") is True
    assert runtime._allow_noop_plan(session, "Is the weather nice?") is True
    assert runtime._allow_noop_plan(session, "Read the files in this workspace.") is False


def test_future_tense_assistant_messages_are_detected() -> None:
    assert runtime._assistant_message_reads_like_future_intent("I will inspect the workspace now.")
    assert runtime._assistant_message_reads_like_future_intent("Let me check the repo.")
    assert runtime._assistant_message_reads_like_future_intent(
        "Created the file successfully. Verifying the file content now."
    )
    assert not runtime._assistant_message_reads_like_future_intent(
        "I checked the workspace and found no manifest."
    )


def test_completed_assistant_message_is_normalized_to_past_tense() -> None:
    assert (
        runtime._normalize_completed_assistant_message(
            "Created the file successfully. Verifying the file content."
        )
        == "Created the file successfully. Verified the file content."
    )


def test_post_message_falls_back_to_local_inspection_when_simple_code_turn_hits_content_filter(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    (tmp_path / "main.py").write_text("print('ok')\n", encoding="utf-8")
    session = runtime.create_session(tmp_path, mode="code", trust_mode="read_only")

    def fail_plan(*args: Any, **kwargs: Any) -> CoderTurnPlan:
        raise ValueError("content_filter")

    monkeypatch.setattr(runtime, "_plan_turn", fail_plan)

    updated = runtime.post_message(tmp_path, session.session_id, "Can you check the workspace now?")

    assert updated.status == SessionStatus.COMPLETED
    assert updated.transcript[-1].role == "assistant"
    assert "workspace" in updated.transcript[-1].content.lower()


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
    assert completed.current_summary == "Final answer"
    assert completed.transcript[-1].content == "Final answer"


def test_approval_pause_keeps_original_turn_summary(tmp_path: Path, monkeypatch: Any) -> None:
    ledger = RunLedger.create(tmp_path, "coder")
    session = CoderSession(
        session_id=ledger.run_dir.name,
        workspace_root=str(tmp_path),
        trust_mode=TrustMode.ASK,
        created_at=runtime._utcnow(),
        updated_at=runtime._utcnow(),
        current_summary="Created the file and verified the result.",
        next_action_index=0,
    )
    action = CoderAction(
        kind="write_file",
        path="note.txt",
        summary="Create note.txt",
        content="hi\n",
    )

    class _ApprovalResult:
        requires_approval = True
        success = False
        error = None
        data = {}
        policy = type(
            "_Policy",
            (),
            {"risk_level": type("_Risk", (), {"value": "medium"})(), "reason": "approval required"},
        )()

    class _Invoker:
        def invoke(self, *_args: Any, **_kwargs: Any) -> Any:
            return _ApprovalResult()

    monkeypatch.setattr(runtime, "_create_invoker", lambda *_args, **_kwargs: _Invoker())

    updated, should_continue = runtime._invoke_action(tmp_path, ledger, session, action)

    assert should_continue is False
    assert updated.status == SessionStatus.AWAITING_APPROVAL
    assert updated.current_summary == "Created the file and verified the result."
    assert updated.pending_assistant_message is not None


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
