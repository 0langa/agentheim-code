"""Background run executor for workflow and preset execution via API.

Runs long-lived tasks in background threads and exposes status polling
and SSE streaming.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class RunStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class RunRecord:
    run_id: str
    status: RunStatus
    started_at: float
    finished_at: float | None = None
    result: Any = None
    error: str | None = None
    artifacts: list[str] = field(default_factory=list)
    logs: list[str] = field(default_factory=list)


class RunHook(Protocol):
    """Protocol for hooks that observe run lifecycle events."""

    def start_run(self, run_id: str) -> None: ...

    def end_run(self, run_id: str) -> None: ...

    def record_error(self, run_id: str) -> None: ...

    def on_run_complete(self, run_id: str, success: bool, error: str | None = None) -> None: ...


class RunExecutor:
    """Singleton executor that manages background runs."""

    _instance: RunExecutor | None = None
    _lock = threading.Lock()
    _runs: dict[str, RunRecord]
    _run_lock: threading.Lock
    _subscribers: dict[str, list[Callable[[RunRecord], None]]]
    _hooks: list[RunHook]

    def __new__(cls) -> RunExecutor:
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._runs = {}
                cls._instance._run_lock = threading.Lock()
                cls._instance._subscribers = {}
                cls._instance._hooks = []
            return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the singleton (mainly for tests)."""
        with cls._lock:
            if cls._instance is not None:
                cls._instance = None

    def submit(
        self,
        fn: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> str:
        """Submit *fn* for background execution and return a run ID."""
        run_id = str(uuid.uuid4())
        record = RunRecord(
            run_id=run_id,
            status=RunStatus.PENDING,
            started_at=time.time(),
        )
        with self._run_lock:
            self._runs[run_id] = record
            self._subscribers[run_id] = []

        def _run() -> None:
            for hook in self._hooks:
                try:
                    hook.start_run(run_id)
                except Exception:
                    logger.exception("Run start hook failed for %s", run_id)

            with self._run_lock:
                record.status = RunStatus.RUNNING
            self._notify(run_id)
            try:
                result = fn(*args, **kwargs)
                with self._run_lock:
                    record.status = RunStatus.COMPLETED
                    record.result = result
                    record.finished_at = time.time()
                    if isinstance(result, tuple) and len(result) == 2:
                        # Coding runtime returns (report, ledger_dir)
                        report, ledger_dir = result
                        if hasattr(report, "run_id"):
                            record.artifacts = [report.run_id]
                        if isinstance(ledger_dir, Path):
                            record.artifacts.append(str(ledger_dir.name))
                for hook in self._hooks:
                    try:
                        hook.end_run(run_id)
                    except Exception:
                        logger.exception("Run end hook failed for %s", run_id)
                    try:
                        hook.on_run_complete(run_id, success=True)
                    except Exception:
                        logger.exception("Run complete hook failed for %s", run_id)
            except Exception as exc:
                logger.exception("Run %s failed", run_id)
                with self._run_lock:
                    record.status = RunStatus.FAILED
                    record.error = str(exc)
                    record.finished_at = time.time()
                for hook in self._hooks:
                    try:
                        hook.record_error(run_id)
                    except Exception:
                        logger.exception("Run error hook failed for %s", run_id)
                    try:
                        hook.on_run_complete(run_id, success=False, error=str(exc))
                    except Exception:
                        logger.exception("Run complete hook failed for %s", run_id)
            self._notify(run_id)

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        return run_id

    def get(self, run_id: str) -> RunRecord | None:
        with self._run_lock:
            return self._runs.get(run_id)

    def list_runs(self) -> list[RunRecord]:
        with self._run_lock:
            return list(self._runs.values())

    def subscribe(self, run_id: str, callback: Callable[[RunRecord], None]) -> None:
        with self._run_lock:
            if run_id in self._subscribers:
                self._subscribers[run_id].append(callback)

    def unsubscribe(self, run_id: str, callback: Callable[[RunRecord], None]) -> None:
        with self._run_lock:
            if run_id in self._subscribers:
                with suppress(ValueError):
                    self._subscribers[run_id].remove(callback)

    def _notify(self, run_id: str) -> None:
        with self._run_lock:
            record = self._runs.get(run_id)
            callbacks = list(self._subscribers.get(run_id, []))
        if record is None:
            return
        for cb in callbacks:
            try:
                cb(record)
            except Exception:
                logger.exception("Run status subscriber failed for run_id=%s", run_id)

    def add_hook(self, hook: RunHook) -> None:
        """Register a lifecycle hook if not already registered."""
        if not any(h is hook for h in self._hooks):
            self._hooks.append(hook)

    def log(self, run_id: str, message: str) -> None:
        with self._run_lock:
            record = self._runs.get(run_id)
            if record is not None:
                record.logs.append(message)
        self._notify(run_id)
