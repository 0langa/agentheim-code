from __future__ import annotations

from enum import StrEnum
from typing import Any

from core.errors import ExecutionError
from core.events import EventType
from core.ledger import RunLedger


class RuntimeState(StrEnum):
    INIT = "INIT"
    LOAD_CONFIG = "LOAD_CONFIG"
    PREPARE_WORKSPACE = "PREPARE_WORKSPACE"
    SCAN_REPOSITORY = "SCAN_REPOSITORY"
    BUILD_CONTEXT_PACK = "BUILD_CONTEXT_PACK"
    PLAN = "PLAN"
    EXECUTE_TASK = "EXECUTE_TASK"
    BASIC_VERIFY = "BASIC_VERIFY"
    VERIFY_TASK = "VERIFY_TASK"
    FIX_LOOP = "FIX_LOOP"
    FINAL_VERIFY = "FINAL_VERIFY"
    FINAL_REPORT = "FINAL_REPORT"
    RESUME_AVAILABLE = "RESUME_AVAILABLE"
    DONE = "DONE"
    BLOCKED = "BLOCKED"
    FAILED_AND_ROLLED_BACK = "FAILED_AND_ROLLED_BACK"


class RuntimeStateMachine:
    ALLOWED: dict[RuntimeState, set[RuntimeState]] = {
        RuntimeState.INIT: {
            RuntimeState.LOAD_CONFIG,
            RuntimeState.BLOCKED,
            RuntimeState.FAILED_AND_ROLLED_BACK,
        },
        RuntimeState.LOAD_CONFIG: {
            RuntimeState.PREPARE_WORKSPACE,
            RuntimeState.BLOCKED,
            RuntimeState.FAILED_AND_ROLLED_BACK,
        },
        RuntimeState.PREPARE_WORKSPACE: {
            RuntimeState.SCAN_REPOSITORY,
            RuntimeState.BLOCKED,
            RuntimeState.FAILED_AND_ROLLED_BACK,
        },
        RuntimeState.SCAN_REPOSITORY: {
            RuntimeState.BUILD_CONTEXT_PACK,
            RuntimeState.BLOCKED,
            RuntimeState.FAILED_AND_ROLLED_BACK,
        },
        RuntimeState.BUILD_CONTEXT_PACK: {
            RuntimeState.PLAN,
            RuntimeState.BLOCKED,
            RuntimeState.FAILED_AND_ROLLED_BACK,
        },
        RuntimeState.PLAN: {
            RuntimeState.EXECUTE_TASK,
            RuntimeState.FINAL_REPORT,
            RuntimeState.BLOCKED,
            RuntimeState.FAILED_AND_ROLLED_BACK,
        },
        RuntimeState.EXECUTE_TASK: {
            RuntimeState.BASIC_VERIFY,
            RuntimeState.VERIFY_TASK,
            RuntimeState.BLOCKED,
            RuntimeState.FAILED_AND_ROLLED_BACK,
        },
        RuntimeState.BASIC_VERIFY: {
            RuntimeState.VERIFY_TASK,
            RuntimeState.EXECUTE_TASK,
            RuntimeState.FINAL_VERIFY,
            RuntimeState.BLOCKED,
            RuntimeState.FAILED_AND_ROLLED_BACK,
        },
        RuntimeState.VERIFY_TASK: {
            RuntimeState.FIX_LOOP,
            RuntimeState.EXECUTE_TASK,
            RuntimeState.FINAL_VERIFY,
            RuntimeState.BLOCKED,
            RuntimeState.FAILED_AND_ROLLED_BACK,
        },
        RuntimeState.FIX_LOOP: {
            RuntimeState.EXECUTE_TASK,
            RuntimeState.BASIC_VERIFY,
            RuntimeState.BLOCKED,
            RuntimeState.FAILED_AND_ROLLED_BACK,
        },
        RuntimeState.FINAL_VERIFY: {
            RuntimeState.FINAL_REPORT,
            RuntimeState.BLOCKED,
            RuntimeState.FAILED_AND_ROLLED_BACK,
        },
        RuntimeState.FINAL_REPORT: {
            RuntimeState.RESUME_AVAILABLE,
            RuntimeState.DONE,
            RuntimeState.BLOCKED,
            RuntimeState.FAILED_AND_ROLLED_BACK,
        },
        RuntimeState.RESUME_AVAILABLE: {
            RuntimeState.DONE,
            RuntimeState.BLOCKED,
            RuntimeState.FAILED_AND_ROLLED_BACK,
        },
        RuntimeState.DONE: set(),
        RuntimeState.BLOCKED: {RuntimeState.RESUME_AVAILABLE, RuntimeState.DONE},
        RuntimeState.FAILED_AND_ROLLED_BACK: set(),
    }

    def __init__(self, ledger: RunLedger | None = None) -> None:
        self.current = RuntimeState.INIT
        self.ledger = ledger
        self.history: list[RuntimeState] = [self.current]
        self._record(self.current, None)

    def transition(
        self, new_state: RuntimeState, details: dict[str, Any] | None = None
    ) -> RuntimeState:
        if new_state not in self.ALLOWED[self.current]:
            raise ExecutionError(f"Invalid state transition: {self.current} -> {new_state}")
        self.current = new_state
        self.history.append(new_state)
        self._record(new_state, details)
        return new_state

    def _record(self, state: RuntimeState, details: dict[str, Any] | None) -> None:
        if self.ledger is None:
            return
        payload: dict[str, Any] = {"state": state.value}
        if details:
            payload.update(details)
        # Canonical event truth
        self.ledger.emit_event(EventType.STATE_TRANSITION, payload=payload)
        # Legacy mirror for compatibility
        self.ledger.append_jsonl("state_transitions.jsonl", payload)
