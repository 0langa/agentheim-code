from __future__ import annotations

import base64
import shlex
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TrustMode(StrEnum):
    READ_ONLY = "read_only"
    ASK = "ask"
    WORKSPACE = "workspace"


class SessionStatus(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ActivityKind(StrEnum):
    THINKING = "thinking"
    SCANNING = "scanning"
    EDITING = "editing"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    BLOCKED = "blocked"


class CoderMode(StrEnum):
    ASK = "ask"
    PLAN = "plan"
    CODE = "code"
    REVIEW = "review"
    FIX = "fix"
    DOCS = "docs"
    TEST = "test"


class CoderMessage(BaseModel):
    model_config = ConfigDict(frozen=True)

    role: Literal["user", "assistant", "system"]
    content: str
    created_at: str


class CoderAction(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: Literal["list_files", "read_file", "write_file", "run_command"]
    summary: str = ""
    path: str | None = None
    content: str | None = None
    content_lines: list[str] = Field(default_factory=list)
    content_base64: str | None = None
    command: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _join_content_lines(cls, data: object) -> object:
        if isinstance(data, dict):
            data = dict(data)
            if "kind" not in data and "type" in data:
                data["kind"] = data["type"]
            if "path" not in data:
                data["path"] = data.get("file_path") or data.get("filename")
            if isinstance(data.get("command"), str):
                data["command"] = shlex.split(str(data["command"]), posix=False)
        if isinstance(data, dict) and not data.get("content") and data.get("content_base64"):
            data = dict(data)
            data["content"] = base64.b64decode(str(data["content_base64"])).decode("utf-8")
        if (
            isinstance(data, dict)
            and not data.get("content")
            and isinstance(data.get("content_lines"), list)
        ):
            data = dict(data)
            data["content"] = "\n".join(str(line) for line in data["content_lines"])
        return data


class CoderTurnPlan(BaseModel):
    model_config = ConfigDict(frozen=True)

    assistant_message: str
    summary: str
    actions: list[CoderAction] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)


class CoderActivity(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: ActivityKind
    message: str
    created_at: str
    details: dict[str, str] = Field(default_factory=dict)


class PendingApproval(BaseModel):
    model_config = ConfigDict(frozen=True)

    request_id: str
    tool_id: str
    params: dict[str, object] = Field(default_factory=dict)
    risk_level: str
    reason: str
    action_index: int
    status: Literal["pending", "granted", "denied"] = "pending"


class CoderApproval(BaseModel):
    model_config = ConfigDict(frozen=True)

    request_id: str
    tool_id: str
    risk_level: str
    reason: str
    status: str


class CoderEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    event_id: str
    kind: str
    message: str
    created_at: str
    details: dict[str, str] = Field(default_factory=dict)


class CoderDiff(BaseModel):
    model_config = ConfigDict(frozen=True)

    path: str
    before: str
    after: str
    status: Literal["planned", "applied"] = "applied"
    created_at: str


class CoderCommandResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    command: list[str] = Field(default_factory=list)
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    created_at: str


class CoderModelSelection(BaseModel):
    model_config = ConfigDict(frozen=True)

    profile: str = "auto"
    provider: str = "auto"
    model: str = "auto"
    role: str = "planner"
    actual_profile: str | None = None
    actual_provider: str | None = None
    actual_model: str | None = None


class CoderSession(BaseModel):
    session_id: str
    workspace_root: str
    trust_mode: TrustMode
    mode: CoderMode = CoderMode.CODE
    model_selection: CoderModelSelection = Field(default_factory=CoderModelSelection)
    status: SessionStatus = SessionStatus.IDLE
    created_at: str
    updated_at: str
    transcript: list[CoderMessage] = Field(default_factory=list)
    activities: list[CoderActivity] = Field(default_factory=list)
    changed_files: list[str] = Field(default_factory=list)
    pending_approval: PendingApproval | None = None
    current_user_prompt: str | None = None
    current_assistant_message: str | None = None
    current_summary: str = ""
    planned_actions: list[CoderAction] = Field(default_factory=list)
    next_action_index: int = 0
    git_available: bool = False
    queued_prompts: list[str] = Field(default_factory=list)


class CoderSessionView(BaseModel):
    model_config = ConfigDict(frozen=True)

    session: CoderSession
    events: list[CoderEvent] = Field(default_factory=list)
    approvals: list[CoderApproval] = Field(default_factory=list)
    diffs: list[CoderDiff] = Field(default_factory=list)
    command_results: list[CoderCommandResult] = Field(default_factory=list)
    artifacts: list[str] = Field(default_factory=list)
    queued_prompts: list[str] = Field(default_factory=list)
    available_commands: list[str] = Field(default_factory=list)
