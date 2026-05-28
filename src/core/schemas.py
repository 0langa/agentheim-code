from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class WorkflowStepStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class AgentMessage(BaseModel):
    model_config = ConfigDict(frozen=True)

    actor: str = Field(min_length=1)
    content: str = Field(min_length=1)
    metadata: dict[str, str] = Field(default_factory=dict)


class ToolCall(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1)
    arguments: dict[str, object] = Field(default_factory=dict)
    actor: str = Field(min_length=1)
    workflow_step_id: str = Field(min_length=1)


class ToolResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    tool_name: str = Field(min_length=1)
    success: bool
    output: str = ""
    error: str | None = None
    artifact_ids: list[str] = Field(default_factory=list)


class ArtifactRef(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    path: str = Field(min_length=1)
    summary: str = ""


class PolicyDecision(BaseModel):
    model_config = ConfigDict(frozen=True)

    allowed: bool
    policy_name: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class CapabilityDescriptor(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    properties: dict[str, str] = Field(default_factory=dict)


class WorkflowStep(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    actor: str = Field(min_length=1)
    status: WorkflowStepStatus = WorkflowStepStatus.PENDING
    details: str = ""
    artifacts: list[ArtifactRef] = Field(default_factory=list)


class WorkflowRun(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str = Field(min_length=1)
    workflow_id: str = Field(min_length=1)
    status: WorkflowStepStatus
    steps: list[WorkflowStep] = Field(default_factory=list)
    messages: list[AgentMessage] = Field(default_factory=list)
