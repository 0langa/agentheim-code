from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import AliasChoices, BaseModel, BeforeValidator, ConfigDict, Field

from config.config import ModelRole


class TaskType(StrEnum):
    INSPECT = "inspect"
    EDIT = "edit"
    TEST = "test"
    DOCS = "docs"
    CLEANUP = "cleanup"


class UserTask(BaseModel):
    model_config = ConfigDict(frozen=True)

    request: str = Field(min_length=1)


class RepoSnapshotRef(BaseModel):
    model_config = ConfigDict(frozen=True)

    repo_root: str = Field(min_length=1)
    snapshot_path: str | None = None


class ContextPackRef(BaseModel):
    model_config = ConfigDict(frozen=True)

    repo_root: str = Field(min_length=1)
    context_pack_path: str | None = None
    excerpt: str = Field(min_length=1)


class AcceptanceCriterion(BaseModel):
    model_config = ConfigDict(frozen=True)

    description: str = Field(min_length=1)
    measurable: bool = True


class RiskAssessment(BaseModel):
    model_config = ConfigDict(frozen=True)

    risk: str = Field(min_length=1)
    impact: str = Field(min_length=1)
    mitigation: str = Field(min_length=1)


class WorkOrder(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    relevant_files: list[str] = Field(default_factory=list)
    required_context_excerpts: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    forbidden_changes: list[str] = Field(default_factory=list)
    acceptance_criteria: list[AcceptanceCriterion] = Field(default_factory=list)
    expected_commands: list[list[str]] = Field(default_factory=list)
    max_edit_scope: str = Field(default="")


class TaskNode(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    type: TaskType
    title: str = Field(min_length=1)
    dependencies: list[str] = Field(default_factory=list)
    acceptance_criteria: list[AcceptanceCriterion] = Field(default_factory=list)
    max_edit_scope: str = Field(default="")
    expected_verifier_commands: list[list[str]] = Field(default_factory=list)
    work_order: WorkOrder


class TaskGraph(BaseModel):
    model_config = ConfigDict(frozen=True)

    ordered_tasks: list[TaskNode] = Field(min_length=1)
    dependencies: list[dict[str, str]] = Field(default_factory=list)


class AgentMessage(BaseModel):
    model_config = ConfigDict(frozen=True)

    role: ModelRole
    content: str = Field(min_length=1)


class AgentResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    role: ModelRole
    success: bool
    raw_output: str = Field(min_length=1)
    parsed_output: dict | None = None
    error: str | None = None


class FileChange(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    path: str = Field(
        min_length=1,
        validation_alias=AliasChoices(
            "path", "filePath", "FilePath", "file_path", "file", "filename"
        ),
    )
    change_type: str = Field(
        default="modify",
        validation_alias=AliasChoices("change_type", "changeType", "ChangeType", "PatchType"),
    )
    summary: str = Field(default="Apply bounded file update")
    patch: str = Field(default="", validation_alias=AliasChoices("patch", "Patch"))
    after_text: str = Field(default="", validation_alias=AliasChoices("after_text", "afterText"))


class TestSuggestion(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    command: list[str] = Field(min_length=1)
    reason: str = Field(min_length=1)
    relevance: str = Field(min_length=1)


class PatchPlan(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    summary: str = Field(default="Apply bounded work order changes")
    file_changes: list[FileChange] = Field(
        default_factory=list,
        validation_alias=AliasChoices(
            "file_changes",
            "fileChanges",
            "FileChanges",
            "patchPlan",
            "patch_plan",
            "patches",
            "changes",
        ),
    )
    test_suggestions: list[TestSuggestion] = Field(
        default_factory=list, validation_alias=AliasChoices("test_suggestions", "testSuggestions")
    )
    notes: list[str] = Field(default_factory=list)


def _ensure_list(value: object) -> list[str]:
    """Normalize str → [str] or None → []."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)]


def _ensure_list_of_lists(value: object) -> list[list[str]]:
    """Normalize mixed shapes into list[list[str]]."""
    if value is None:
        return []
    if isinstance(value, str):
        return [[value]]
    if isinstance(value, list):
        out: list[list[str]] = []
        for item in value:
            if isinstance(item, list):
                out.append([str(v) for v in item])
            else:
                out.append([str(item)])
        return out
    return [[str(value)]]


class VerificationReport(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    work_order_id: str = Field(
        min_length=1, validation_alias=AliasChoices("work_order_id", "workOrderId")
    )
    status: str = Field(min_length=1)
    commands_run: Annotated[list[list[str]], BeforeValidator(_ensure_list_of_lists)] = Field(
        default_factory=list, validation_alias=AliasChoices("commands_run", "commandsRun")
    )
    passed_checks: Annotated[list[str], BeforeValidator(_ensure_list)] = Field(
        default_factory=list, validation_alias=AliasChoices("passed_checks", "passedChecks")
    )
    failed_checks: Annotated[list[str], BeforeValidator(_ensure_list)] = Field(
        default_factory=list, validation_alias=AliasChoices("failed_checks", "failedChecks")
    )
    diff_findings: Annotated[list[str], BeforeValidator(_ensure_list)] = Field(
        default_factory=list, validation_alias=AliasChoices("diff_findings", "diffFindings")
    )
    missing_tests: Annotated[list[str], BeforeValidator(_ensure_list)] = Field(
        default_factory=list, validation_alias=AliasChoices("missing_tests", "missingTests")
    )
    regressions: Annotated[list[str], BeforeValidator(_ensure_list)] = Field(default_factory=list)
    security_concerns: Annotated[list[str], BeforeValidator(_ensure_list)] = Field(
        default_factory=list, validation_alias=AliasChoices("security_concerns", "securityConcerns")
    )
    performance_concerns: Annotated[list[str], BeforeValidator(_ensure_list)] = Field(
        default_factory=list,
        validation_alias=AliasChoices("performance_concerns", "performanceConcerns"),
    )
    fix_requests: Annotated[list[str], BeforeValidator(_ensure_list)] = Field(
        default_factory=list, validation_alias=AliasChoices("fix_requests", "fixRequests")
    )
    final_summary: str = Field(
        default="", validation_alias=AliasChoices("final_summary", "finalSummary")
    )


class ImplementationPlan(BaseModel):
    model_config = ConfigDict(frozen=True)

    summary: str = Field(min_length=1)
    assumptions: list[str] = Field(default_factory=list)
    non_goals: list[str] = Field(default_factory=list)
    detected_repo_type: str = Field(min_length=1)
    risks: list[RiskAssessment] = Field(default_factory=list)
    task_graph: TaskGraph
    verification_strategy: list[str] = Field(default_factory=list)
    estimated_commands: list[list[str]] = Field(default_factory=list)
    files_likely_to_change: list[str] = Field(default_factory=list)
    stop_conditions: list[str] = Field(default_factory=list)
