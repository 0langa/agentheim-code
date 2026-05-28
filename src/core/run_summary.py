"""Canonical run summary builder from ledger events and persisted artifacts."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field

from core.error_classification import error_summary_from_text
from core.events import EventType
from core.path_security import safe_child_path, safe_project_path, safe_run_id
from core.run_executor import RunRecord


class ModelSelectionSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    role: str
    model_id: str
    provider: str | None = None
    capability: str | None = None
    fallback_count: int = 0


class StateTransitionSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    sequence: int
    step_id: str | None = None
    from_state: str | None = None
    to_state: str | None = None
    output_preview: str | None = None


class ToolCountSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    total_calls: int = 0
    by_tool: dict[str, int] = Field(default_factory=dict)


class PolicyDecisionSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    total: int = 0
    by_decision: dict[str, int] = Field(default_factory=dict)


class ApprovalSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    requested: int = 0
    granted: int = 0
    denied: int = 0
    pending: int = 0


class VerificationCheckSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    status: str
    details: str = ""
    command: list[str] = Field(default_factory=list)


class VerificationSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: str = "not_run"
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    checks: list[VerificationCheckSummary] = Field(default_factory=list)


class RunErrorSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: str
    message: str
    category: str
    retryable: bool
    halt: bool
    next_action: str
    troubleshooting_doc: str
    troubleshooting_section: str


class CanonicalRunSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str
    tracking_run_id: str | None = None
    workflow_id: str | None = None
    preset_id: str | None = None
    status: str
    summary: str
    started_at: str | None = None
    finished_at: str | None = None
    duration_seconds: float | None = None
    repo_root: str | None = None
    report_path: str | None = None
    artifact_dir: str | None = None
    provider_models_by_role: dict[str, ModelSelectionSummary] = Field(default_factory=dict)
    state_transitions: list[StateTransitionSummary] = Field(default_factory=list)
    tool_counts: ToolCountSummary = Field(default_factory=ToolCountSummary)
    policy_decisions: PolicyDecisionSummary = Field(default_factory=PolicyDecisionSummary)
    approvals: ApprovalSummary = Field(default_factory=ApprovalSummary)
    verification: VerificationSummary = Field(default_factory=VerificationSummary)
    artifacts: list[str] = Field(default_factory=list)
    error: RunErrorSummary | None = None
    next_recommended_action: str | None = None
    final_report: dict[str, Any] | None = None


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _list_artifacts(run_dir: Path) -> list[str]:
    return sorted(item.name for item in run_dir.iterdir())


def _normalize_status(raw: str | None) -> str:
    value = (raw or "").strip().lower()
    if value in {"done", "completed", "complete"}:
        return "completed"
    if value in {"blocked"}:
        return "blocked"
    if value in {"failed", "error"}:
        return "failed"
    if value in {"cancelled", "canceled"}:
        return "cancelled"
    if value in {"pending", "initiated"}:
        return "pending"
    if value in {"running", "in_progress"}:
        return "running"
    if value in {"planned", "plan"}:
        return "planned"
    return value or "unknown"


def _iso_or_none(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).astimezone(UTC).isoformat()
    except ValueError:
        return value


def _mtime_iso(path: Path) -> str | None:
    if not path.exists():
        return None
    return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).isoformat()


def _duration_seconds(started_at: str | None, finished_at: str | None) -> float | None:
    if not started_at or not finished_at:
        return None
    try:
        started = datetime.fromisoformat(started_at)
        finished = datetime.fromisoformat(finished_at)
    except ValueError:
        return None
    return max((finished - started).total_seconds(), 0.0)


def _extract_summary(
    final_report: dict[str, Any] | None, plan_report: dict[str, Any] | None
) -> str:
    data = final_report or plan_report or {}
    if "task_summary" in data and data["task_summary"]:
        return str(data["task_summary"])
    if "query" in data and data["query"]:
        return f"Document query: {data['query']}"
    if "topic" in data and data["topic"]:
        return f"Research topic: {data['topic']}"
    if "summary" in data and data["summary"]:
        return str(data["summary"])
    if "scope" in data and "write_mode" in data:
        return f"Context run ({data['scope']} / {data['write_mode']})"
    return "Run summary unavailable"


def _verification_summary(
    final_report: dict[str, Any] | None, verification_report: dict[str, Any] | None
) -> VerificationSummary:
    checks: list[VerificationCheckSummary] = []
    passed = 0
    failed = 0
    skipped = 0

    for item in final_report.get("tests", []) if final_report else []:
        check = VerificationCheckSummary(
            name=str(item.get("name", "unknown")),
            status=str(item.get("status", "unknown")),
            details=str(item.get("details", "")),
            command=[str(part) for part in item.get("command", [])],
        )
        checks.append(check)
        normalized = check.status.lower()
        if normalized in {"pass", "passed", "success", "ok"}:
            passed += 1
        elif normalized in {"skip", "skipped"}:
            skipped += 1
        else:
            failed += 1

    if verification_report and not checks:
        status = str(verification_report.get("status", "unknown")).lower()
        if status in {"pass", "passed", "success", "ok"}:
            passed = 1
            overall = "passed"
        elif status in {"skip", "skipped"}:
            skipped = 1
            overall = "skipped"
        else:
            failed = 1
            overall = "failed"
        return VerificationSummary(
            status=overall,
            total=passed + failed + skipped,
            passed=passed,
            failed=failed,
            skipped=skipped,
            checks=[],
        )

    if checks:
        overall = "failed" if failed else "passed"
        if skipped and not passed and not failed:
            overall = "skipped"
        return VerificationSummary(
            status=overall,
            total=len(checks),
            passed=passed,
            failed=failed,
            skipped=skipped,
            checks=checks,
        )

    return VerificationSummary()


def _error_from_run(
    final_report: dict[str, Any] | None, run_failed_payload: dict[str, Any] | None
) -> RunErrorSummary | None:
    error_type = None
    message = None
    if run_failed_payload:
        error_type = run_failed_payload.get("error_type")
        message = run_failed_payload.get("reason")
    if (
        (not message)
        and final_report
        and _normalize_status(final_report.get("status")) == "blocked"
    ):
        risks = [str(item) for item in final_report.get("remaining_risks", []) if str(item).strip()]
        if risks:
            error_type = "VerificationError"
            message = risks[0]
    if not message:
        return None
    return cast(
        RunErrorSummary,
        RunErrorSummary.model_validate(
            error_summary_from_text(str(message), str(error_type) if error_type else None)
        ),
    )


def _infer_next_action(
    run_id: str,
    status: str,
    final_report: dict[str, Any] | None,
    error: RunErrorSummary | None,
) -> str | None:
    suggestions = final_report.get("next_command_suggestions", []) if final_report else []
    if suggestions:
        return str(suggestions[0])
    if error is not None:
        return error.next_action
    if status == "blocked":
        return f"agentheim-code runs inspect {run_id}"
    if status in {"pending", "running"}:
        return "Poll the run status endpoint or subscribe to stream/ws updates."
    if status == "planned":
        return f"agentheim-code runs inspect {run_id}"
    return None


def build_run_summary(
    repo_root: str | Path, run_id: str, *, tracking_run_id: str | None = None
) -> CanonicalRunSummary:
    repo_root = safe_project_path(repo_root)
    run_id = safe_run_id(run_id)
    run_dir = safe_child_path(repo_root, ".ai-team", "runs", run_id)
    if not run_dir.exists():
        raise FileNotFoundError(f"Run '{run_id}' not found under {repo_root}")

    run_data = _load_json(run_dir / "run.json") or {}
    final_report = _load_json(run_dir / "final_report.json")
    plan_report = _load_json(run_dir / "plan.json")
    verification_report = _load_json(run_dir / "verification.json")
    artifacts = _list_artifacts(run_dir)

    events = []
    ledger_path = run_dir / "ledger.jsonl"
    if ledger_path.exists():
        for line in ledger_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                events.append(json.loads(line))

    workflow_id = run_data.get("workflow_id")
    preset_id = run_data.get("preset_id")
    repo_path = run_data.get("repo_root")
    started_event = next(
        (event for event in events if event.get("event_type") == EventType.RUN_INITIATED.value),
        None,
    )
    completed_event = next(
        (
            event
            for event in reversed(events)
            if event.get("event_type") == EventType.RUN_COMPLETED.value
        ),
        None,
    )
    failed_event = next(
        (
            event
            for event in reversed(events)
            if event.get("event_type") == EventType.RUN_FAILED.value
        ),
        None,
    )

    if started_event:
        payload = started_event.get("payload", {})
        workflow_id = workflow_id or payload.get("workflow_id")
        repo_path = repo_path or payload.get("repo_root")
    started_at = _iso_or_none(
        (started_event or {}).get("timestamp")
        or run_data.get("created_at")
        or _mtime_iso(run_dir / "run.json")
    )
    finished_at = _iso_or_none(
        (completed_event or failed_event or {}).get("timestamp")
        or _mtime_iso(run_dir / "final_report.json")
        or _mtime_iso(run_dir / "final_report.md")
    )

    if final_report and final_report.get("status"):
        status = _normalize_status(final_report.get("status"))
    elif failed_event is not None:
        status = "failed"
    elif (
        completed_event is not None
        or final_report is not None
        or (run_dir / "final_report.md").exists()
    ):
        status = "completed"
    elif plan_report is not None:
        status = "planned"
    elif events:
        status = "running"
    else:
        status = _normalize_status(run_data.get("status"))

    provider_models: dict[str, ModelSelectionSummary] = {}
    state_transitions: list[StateTransitionSummary] = []
    tool_counts: dict[str, int] = {}
    policy_counts: dict[str, int] = {}
    approval_summary = ApprovalSummary()

    for event in events:
        event_type = event.get("event_type")
        payload = event.get("payload", {})
        if event_type == EventType.MODEL_SELECTED.value:
            role = str(payload.get("role", "unknown"))
            provider_models[role] = ModelSelectionSummary(
                role=role,
                model_id=str(payload.get("model_id", "unknown")),
                capability=str(payload.get("capability"))
                if payload.get("capability") is not None
                else None,
                fallback_count=int(payload.get("fallback_count", 0) or 0),
            )
        elif event_type == EventType.STATE_TRANSITION.value:
            state_transitions.append(
                StateTransitionSummary(
                    sequence=int(event.get("sequence", 0)),
                    step_id=event.get("step_id"),
                    from_state=str(payload.get("from"))
                    if payload.get("from") is not None
                    else None,
                    to_state=str(payload.get("to")) if payload.get("to") is not None else None,
                    output_preview=str(payload.get("output_preview"))
                    if payload.get("output_preview")
                    else None,
                )
            )
        elif event_type == EventType.TOOL_CALLED.value:
            tool_id = str(event.get("tool_id") or "unknown")
            tool_counts[tool_id] = tool_counts.get(tool_id, 0) + 1
        elif event_type == EventType.POLICY_EVALUATED.value:
            decision = str(payload.get("decision", "unknown"))
            policy_counts[decision] = policy_counts.get(decision, 0) + 1
        elif event_type == EventType.APPROVAL_REQUESTED.value:
            approval_summary = approval_summary.model_copy(
                update={"requested": approval_summary.requested + 1}
            )
        elif event_type == EventType.APPROVAL_GRANTED.value:
            approval_summary = approval_summary.model_copy(
                update={"granted": approval_summary.granted + 1}
            )
        elif event_type == EventType.APPROVAL_DENIED.value:
            approval_summary = approval_summary.model_copy(
                update={"denied": approval_summary.denied + 1}
            )

    approval_summary = approval_summary.model_copy(
        update={
            "pending": max(
                approval_summary.requested - approval_summary.granted - approval_summary.denied, 0
            )
        }
    )
    verification = _verification_summary(final_report, verification_report)
    error = _error_from_run(final_report, failed_event.get("payload") if failed_event else None)

    report_path: str | None = None
    if (run_dir / "final_report.md").exists():
        report_path = str(run_dir / "final_report.md")
    elif (run_dir / "final_report.json").exists():
        report_path = str(run_dir / "final_report.json")

    return CanonicalRunSummary(
        run_id=run_id,
        tracking_run_id=tracking_run_id if tracking_run_id and tracking_run_id != run_id else None,
        workflow_id=str(workflow_id) if workflow_id else None,
        preset_id=str(preset_id) if preset_id else None,
        status=status,
        summary=_extract_summary(final_report, plan_report),
        started_at=started_at,
        finished_at=finished_at,
        duration_seconds=_duration_seconds(started_at, finished_at),
        repo_root=repo_path,
        report_path=report_path,
        artifact_dir=str(run_dir),
        provider_models_by_role=provider_models,
        state_transitions=state_transitions,
        tool_counts=ToolCountSummary(total_calls=sum(tool_counts.values()), by_tool=tool_counts),
        policy_decisions=PolicyDecisionSummary(
            total=sum(policy_counts.values()), by_decision=policy_counts
        ),
        approvals=approval_summary,
        verification=verification,
        artifacts=artifacts,
        error=error,
        next_recommended_action=_infer_next_action(run_id, status, final_report, error),
        final_report=final_report or plan_report,
    )


def _render_diagnostics_md(summary: CanonicalRunSummary) -> str:
    lines: list[str] = [
        f"# Run Diagnostics — {summary.run_id}",
        "",
        f"- **Status**: {summary.status}",
        f"- **Workflow**: {summary.workflow_id or 'N/A'}",
        f"- **Preset**: {summary.preset_id or 'N/A'}",
        f"- **Duration**: {summary.duration_seconds:.1f}s"
        if summary.duration_seconds
        else "- **Duration**: N/A",
        "",
    ]

    if summary.error:
        lines.extend(
            [
                "## Error",
                "",
                f"- **Type**: {summary.error.type}",
                f"- **Category**: {summary.error.category}",
                f"- **Message**: {summary.error.message}",
                f"- **Retryable**: {'yes' if summary.error.retryable else 'no'}",
                f"- **Halt**: {'yes' if summary.error.halt else 'no'}",
                f"- **Next action**: {summary.error.next_action}",
                f"- **Troubleshooting**: [{summary.error.troubleshooting_section}]({summary.error.troubleshooting_doc})",
                "",
            ]
        )

    if summary.state_transitions:
        lines.extend(["## State Transitions", ""])
        for st in summary.state_transitions:
            lines.append(f"- {st.sequence}: {st.from_state or 'start'} → {st.to_state or 'end'}")
        lines.append("")

    if summary.tool_counts.total_calls:
        lines.extend(["## Tool Calls", ""])
        lines.append(f"- **Total**: {summary.tool_counts.total_calls}")
        for tool_id, count in summary.tool_counts.by_tool.items():
            lines.append(f"- {tool_id}: {count}")
        lines.append("")

    if summary.policy_decisions.total:
        lines.extend(["## Policy Decisions", ""])
        lines.append(f"- **Total**: {summary.policy_decisions.total}")
        for decision, count in summary.policy_decisions.by_decision.items():
            lines.append(f"- {decision}: {count}")
        lines.append("")

    if summary.approvals.requested:
        lines.extend(
            [
                "## Approvals",
                "",
                f"- Requested: {summary.approvals.requested}",
                f"- Granted: {summary.approvals.granted}",
                f"- Denied: {summary.approvals.denied}",
                f"- Pending: {summary.approvals.pending}",
                "",
            ]
        )

    if summary.verification.total:
        lines.extend(
            [
                "## Verification",
                "",
                f"- Status: {summary.verification.status}",
                f"- Passed: {summary.verification.passed}",
                f"- Failed: {summary.verification.failed}",
                f"- Skipped: {summary.verification.skipped}",
                "",
            ]
        )
        for check in summary.verification.checks:
            lines.append(f"- {check.name}: {check.status} — {check.details}")
        lines.append("")

    if summary.artifacts:
        lines.extend(["## Artifacts", ""])
        for name in summary.artifacts:
            lines.append(f"- {name}")
        lines.append("")

    if summary.next_recommended_action:
        lines.extend(["## Recommended Next Action", "", f"{summary.next_recommended_action}", ""])

    lines.extend(
        [
            "---",
            "",
            "*Generated by Agentheim run diagnostics.*",
        ]
    )
    return "\n".join(lines)


def write_diagnostics_bundle(run_dir: Path, run_id: str | None = None) -> tuple[Path, Path]:
    """Write `run_summary.json` and `diagnostics.md` into *run_dir*.

    Derives repo_root from the canonical ``.ai-team/runs/<run_id>`` path.
    """
    run_dir = Path(run_dir).resolve()
    if run_id is None:
        run_id = run_dir.name
    run_id = safe_run_id(run_id)
    repo_root = run_dir.parent.parent.parent
    summary = build_run_summary(repo_root, run_id)

    summary_path = run_dir / "run_summary.json"
    summary_path.write_text(json.dumps(summary.model_dump(mode="json"), indent=2), encoding="utf-8")

    diagnostics_path = run_dir / "diagnostics.md"
    diagnostics_path.write_text(_render_diagnostics_md(summary), encoding="utf-8")

    return summary_path, diagnostics_path


def build_live_run_summary(
    repo_root: str | Path,
    tracking_run_id: str,
    record: RunRecord,
) -> CanonicalRunSummary:
    """Return canonical payload for an executor-backed run."""
    resolved_run_id = resolve_run_id(record)
    if resolved_run_id is not None:
        safe_id = safe_run_id(resolved_run_id)
        repo_path = safe_project_path(repo_root)
        run_dir = safe_child_path(repo_path, ".ai-team", "runs", safe_id)
        if run_dir.exists():
            return build_run_summary(repo_path, safe_id, tracking_run_id=tracking_run_id)

    error = None
    if record.error:
        error = RunErrorSummary.model_validate(error_summary_from_text(record.error))
    status = _normalize_status(record.status.value)
    return CanonicalRunSummary(
        run_id=tracking_run_id,
        workflow_id=None,
        preset_id=None,
        status=status,
        summary="Run in progress"
        if status in {"pending", "running"}
        else "Run completed without persisted artifacts",
        started_at=datetime.fromtimestamp(record.started_at, tz=UTC).isoformat(),
        finished_at=datetime.fromtimestamp(record.finished_at, tz=UTC).isoformat()
        if record.finished_at
        else None,
        duration_seconds=max(
            (record.finished_at or datetime.now(tz=UTC).timestamp()) - record.started_at, 0.0
        ),
        repo_root=None,
        report_path=None,
        artifact_dir=None,
        artifacts=record.artifacts,
        error=error,
        next_recommended_action=error.next_action
        if error
        else (
            "Poll the run status endpoint or subscribe to stream/ws updates."
            if status in {"pending", "running"}
            else None
        ),
    )


def resolve_run_id(record: RunRecord) -> str | None:
    """Resolve the persisted run id from an executor result when available."""
    result = record.result
    if isinstance(result, tuple) and len(result) == 2:
        report, ledger_dir = result
        if hasattr(report, "run_id") and report.run_id:
            return str(report.run_id)
        if isinstance(ledger_dir, Path):
            return ledger_dir.name
    if hasattr(result, "run_id") and result.run_id:
        return str(result.run_id)
    return None
