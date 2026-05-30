from __future__ import annotations

import contextlib
import json
import os
import subprocess
from collections.abc import Iterator
from datetime import UTC, datetime
from itertools import islice
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from pydantic import BaseModel

from core.public_api import RunLedger, safe_project_path, safe_run_id
from workflows.coder.models import (
    ActivityKind,
    CoderActivity,
    CoderCommandResult,
    CoderDiff,
    CoderEvent,
    CoderMessage,
    CoderSession,
    SessionStatus,
    canonical_mode,
)

SESSION_LOCK_STALE_SECONDS = 60 * 60


def _utcnow() -> str:
    return datetime.now(tz=UTC).isoformat()


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


def _load_session(workspace_root: Path, session_id: str) -> CoderSession:
    paths = _session_paths(workspace_root, session_id)
    if not paths["session"].exists():
        raise ValueError(f"Session '{session_id}' not found.")
    data = json.loads(paths["session"].read_text(encoding="utf-8"))
    session = CoderSession.model_validate(data)
    normalized_mode = canonical_mode(session.mode)
    if session.mode != normalized_mode:
        session = session.model_copy(update={"mode": normalized_mode})
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
    return cast(
        CoderSession,
        session.model_copy(update={"transcript": transcript, "activities": activities}),
    )


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


def _read_jsonl_model[TModel: BaseModel](path: Path, model_type: type[TModel]) -> list[TModel]:
    items: list[TModel] = []
    if not path.exists():
        return items
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            items.append(model_type.model_validate(json.loads(line)))
    return items


def _record_activity(
    workspace_root: Path,
    session: CoderSession,
    kind: ActivityKind | str,
    message: str,
    details: dict[str, Any] | None = None,
    request_id: str = "",
) -> CoderSession:
    activity_kind = kind if isinstance(kind, ActivityKind) else ActivityKind.THINKING
    activity = CoderActivity(
        kind=activity_kind,
        message=message,
        created_at=_utcnow(),
        details={str(k): str(v) for k, v in (details or {}).items()},
    )
    _append_activity(workspace_root, session.session_id, activity)
    event_details = dict(details or {})
    if request_id:
        event_details["request_id"] = request_id
    event_kind = kind.value if isinstance(kind, ActivityKind) else str(kind)
    _append_event(
        workspace_root,
        session.session_id,
        CoderEvent(
            event_id=uuid4().hex,
            kind=event_kind,
            message=message,
            created_at=activity.created_at,
            details=event_details,
        ),
    )
    activities = [*session.activities, activity]
    return cast(
        CoderSession,
        session.model_copy(update={"activities": activities, "updated_at": activity.created_at}),
    )


def _set_status(session: CoderSession, status: SessionStatus) -> CoderSession:
    return cast(
        CoderSession,
        session.model_copy(update={"status": status, "updated_at": _utcnow()}),
    )


def _open_ledger(workspace_root: Path, session_id: str) -> RunLedger:
    ledger = RunLedger(
        repo_root=workspace_root, run_dir=_session_paths(workspace_root, session_id)["run_dir"]
    )
    if (ledger.run_dir / "ledger.jsonl").exists():
        ledger._restore_sequence_from_ledger()  # type: ignore[attr-defined]
    return ledger


class _SessionLock:
    def __init__(self, workspace_root: Path, session_id: str) -> None:
        self.path = _session_paths(workspace_root, session_id)["lock"]
        self._owns_lock = False

    def __enter__(self) -> _SessionLock:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = self._acquire()
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump({"pid": os.getpid(), "created_at": _utcnow()}, handle, sort_keys=True)
        self._owns_lock = True
        return self

    def _acquire(self) -> int:
        try:
            return os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            if not _session_lock_is_stale(self.path):
                raise RuntimeError(
                    f"Coder session already running: {self.path.parent.name}"
                ) from exc
            with contextlib.suppress(FileNotFoundError):
                self.path.unlink()
        try:
            return os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise RuntimeError(f"Coder session already running: {self.path.parent.name}") from exc

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if not self._owns_lock:
            return
        if _session_lock_pid(self.path) != os.getpid():
            return
        with contextlib.suppress(FileNotFoundError):
            self.path.unlink()


def _session_lock_pid(path: Path) -> int | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    pid = payload.get("pid")
    if isinstance(pid, int):
        return pid
    if isinstance(pid, str) and pid.isdecimal():
        return int(pid)
    return None


def _pid_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if pid == os.getpid():
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        if os.name != "nt":
            return False
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                capture_output=True,
                check=False,
                text=True,
                timeout=2,
            )
        except (OSError, subprocess.TimeoutExpired):
            return True
        return str(pid) in result.stdout
    return True


def _session_lock_is_stale(path: Path) -> bool:
    pid = _session_lock_pid(path)
    if pid is not None:
        return not _pid_is_alive(pid)
    try:
        age_seconds = datetime.now(tz=UTC).timestamp() - path.stat().st_mtime
    except OSError:
        return True
    return age_seconds >= SESSION_LOCK_STALE_SECONDS


def _artifacts(workspace: Path, session_id: str) -> list[str]:
    run_dir = _session_paths(workspace, session_id)["run_dir"]
    if not run_dir.exists():
        return []
    return sorted(path.name for path in run_dir.iterdir() if path.is_file())


def _iter_file_tree_entries(workspace: Path) -> Iterator[dict[str, str]]:
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

    def filtered_entries() -> Iterator[dict[str, str]]:
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
