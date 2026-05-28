from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

from core.errors import ResumeError
from core.events import EventType
from core.ledger import RunLedger
from core.path_security import safe_child_path, safe_project_path, safe_run_id
from core.resume import list_runs
from core.run_summary import build_run_summary


class RunView(BaseModel):
    run_id: str
    status: str
    summary: str = ""
    workflow_id: str | None = None
    preset_id: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    report_path: str | None = None
    artifact_dir: str
    resume_available: bool = False
    next_actions: list[str] = Field(default_factory=list)


def _can_resume(run_dir: Path) -> bool:
    ledger_path = run_dir / "ledger.jsonl"
    if not ledger_path.exists():
        return False
    try:
        ledger = RunLedger(run_dir=run_dir, repo_root=run_dir.parent.parent)
        events = ledger.read_ledger()
    except Exception:
        return False
    started = next((e for e in events if e.event_type == EventType.RUN_INITIATED), None)
    if started is None:
        return False
    workflow_id = str(started.payload.get("workflow_id", "")).strip()
    if not workflow_id:
        run_json = run_dir / "run.json"
        if run_json.exists():
            try:
                data = json.loads(run_json.read_text(encoding="utf-8"))
                workflow_id = str(data.get("workflow_id", data.get("workflow", ""))).strip()
            except Exception:
                pass
    return bool(workflow_id)


def _next_actions(status: str, resume_available: bool) -> list[str]:
    if status == "completed":
        return [
            "Open the run artifacts or use `agentheim-code runs` to inspect the run summary.",
        ]
    if status == "failed":
        actions = ["Run `agentheim-code doctor` to check provider status."]
        if resume_available:
            actions.append("Resume from the relevant workflow surface after resolving the failure.")
        return actions
    if status == "blocked":
        if resume_available:
            return [
                "Resume from the relevant workflow surface after resolving the block.",
            ]
        return ["Review the run report for block details."]
    if status in {"running", "pending"}:
        return [
            "Poll status with `agentheim-code runs`, or wait for completion.",
        ]
    if resume_available:
        return [
            "Resume from the relevant workflow surface to retry or continue.",
        ]
    return []


def build_run_view(repo_root: str | Path, run_id: str) -> RunView:
    repo_root = safe_project_path(repo_root)
    run_id = safe_run_id(run_id)
    run_dir = safe_child_path(repo_root, ".ai-team", "runs", run_id)

    if not run_dir.exists():
        raise ResumeError(f"Run '{run_id}' not found under {repo_root}")

    try:
        summary = build_run_summary(repo_root, run_id)
    except Exception:
        summary = None

    resume_available = _can_resume(run_dir)

    if summary is not None:
        report_path: str | None = None
        if (run_dir / "final_report.md").exists():
            report_path = str(run_dir / "final_report.md")
        elif (run_dir / "final_report.json").exists():
            report_path = str(run_dir / "final_report.json")

        return RunView(
            run_id=run_id,
            status=summary.status,
            summary=summary.summary,
            workflow_id=summary.workflow_id,
            preset_id=summary.preset_id,
            started_at=summary.started_at,
            completed_at=summary.finished_at,
            report_path=report_path,
            artifact_dir=str(run_dir),
            resume_available=resume_available,
            next_actions=_next_actions(summary.status, resume_available),
        )

    return RunView(
        run_id=run_id,
        status="unknown",
        summary="Run summary unavailable",
        artifact_dir=str(run_dir),
        resume_available=resume_available,
        next_actions=_next_actions("unknown", resume_available),
    )


def list_run_views(repo_root: str | Path) -> list[RunView]:
    repo_root = safe_project_path(repo_root)
    run_ids = list_runs(repo_root)
    views: list[RunView] = []
    for run_id in run_ids:
        try:
            views.append(build_run_view(repo_root, run_id))
        except Exception:
            run_dir = safe_child_path(repo_root, ".ai-team", "runs", safe_run_id(run_id))
            views.append(
                RunView(
                    run_id=run_id,
                    status="unknown",
                    summary="Run summary unavailable",
                    artifact_dir=str(run_dir),
                )
            )
    return views
