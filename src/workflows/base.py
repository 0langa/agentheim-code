from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from pydantic import BaseModel, Field

from core.ledger import RunLedger
from core.model_registry import ModelRegistry
from core.policy_engine import PolicyEngine
from core.schemas import ArtifactRef
from core.tool_protocol import ToolRegistry
from memory.tiers.working import WorkingMemory


class StepBudget(BaseModel):
    max_tokens: int | None = None
    max_time_seconds: int | None = None


class Step(BaseModel):
    model_config = {"frozen": False}

    id: str = Field(min_length=1)
    agent: str = Field(min_length=1)
    type: str = Field(min_length=1)
    depends_on: list[str] = Field(default_factory=list)
    condition: str | None = None
    max_iterations: int = 1
    timeout: int | None = None
    budget: StepBudget | None = None
    parallel_safe: bool = False
    workspace_isolation: bool = True


class StepContext(BaseModel):
    model_config = {"frozen": False, "arbitrary_types_allowed": True}

    run_id: str = Field(min_length=1)
    step_id: str = Field(min_length=1)
    repo_root: Path = Field(default_factory=lambda: Path("."))
    tools: ToolRegistry = Field(default_factory=ToolRegistry)
    policy: PolicyEngine | None = None
    ledger: RunLedger | None = None
    working_memory: WorkingMemory | None = None
    prior_results: dict[str, StepResult] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class StepResult(BaseModel):
    model_config = {"frozen": False}

    step_id: str = Field(min_length=1)
    success: bool
    output: str = ""
    artifacts: list[ArtifactRef] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


@dataclass
class AgentRole:
    id: str
    capabilities: list[str] = field(default_factory=list)


class ExecutionDAG:
    def __init__(self, steps: list[Step]) -> None:
        self.steps = {s.id: s for s in steps}
        self._validate()

    def _validate(self) -> None:
        for step in self.steps.values():
            for dep in step.depends_on:
                if dep not in self.steps:
                    raise ValueError(f"Step '{step.id}' depends on undefined step '{dep}'")
        self._check_cycles()

    def _check_cycles(self) -> None:
        visited: set[str] = set()
        rec_stack: set[str] = set()

        def visit(node: str) -> None:
            visited.add(node)
            rec_stack.add(node)
            for dep in self.steps[node].depends_on:
                if dep not in visited:
                    visit(dep)
                elif dep in rec_stack:
                    raise ValueError(f"Cycle detected involving step '{node}' → '{dep}'")
            rec_stack.remove(node)

        for node in self.steps:
            if node not in visited:
                visit(node)

    def topological_order(self) -> list[Step]:
        in_degree = dict.fromkeys(self.steps, 0)
        for step in self.steps.values():
            for _dep in step.depends_on:
                in_degree[step.id] += 1

        queue = [sid for sid, deg in in_degree.items() if deg == 0]
        order: list[str] = []
        while queue:
            sid = queue.pop(0)
            order.append(sid)
            for step in self.steps.values():
                if sid in step.depends_on:
                    in_degree[step.id] -= 1
                    if in_degree[step.id] == 0:
                        queue.append(step.id)

        return [self.steps[sid] for sid in order]

    def parallel_groups(self) -> list[list[Step]]:
        order = self.topological_order()
        groups: list[list[Step]] = []
        current: list[Step] = []
        seen: set[str] = set()

        for step in order:
            if all(dep in seen for dep in step.depends_on):
                current.append(step)
            else:
                if current:
                    groups.append(current)
                current = [step]
            seen.add(step.id)

        if current:
            groups.append(current)

        return groups


class Workflow(ABC):
    workflow_id: str = ""
    support_state: str = "experimental"
    required_agents: list[AgentRole] = []
    required_tools: list[str] = []
    dag: ExecutionDAG | None = None

    _ledger: RunLedger | None

    def __init__(
        self,
        model_registry: ModelRegistry,
        tool_registry: ToolRegistry,
        policy_engine: PolicyEngine,
        ledger: RunLedger | None,
    ) -> None:
        self._model_registry = model_registry
        self._tool_registry = tool_registry
        self._policy_engine = policy_engine
        self._ledger = ledger

    @abstractmethod
    def execute_step(self, step: Step, context: StepContext) -> StepResult: ...

    def verify(self, results: list[StepResult]) -> bool:
        return all(r.success for r in results)

    def on_step_complete(self, step: Step, result: StepResult) -> None:
        return None

    def on_run_complete(self, results: list[StepResult]) -> None:
        return None

    def build_context(self, repo_root: Path) -> dict[str, Any]:
        return {}

    def generate_report(self, results: list[StepResult]) -> str:
        lines = [f"# Workflow Report: {self.workflow_id}", ""]
        for r in results:
            status = "PASS" if r.success else "FAIL"
            lines.append(f"- **{r.step_id}**: {status}")
            if r.output:
                lines.append(f"  {r.output[:200]}")
        return "\n".join(lines)

    def run(self, repo_root: Path, metadata: dict[str, Any] | None = None) -> list[StepResult]:
        if self.dag is None:
            raise RuntimeError("Workflow DAG not defined")

        # Phase 7: delegate to the production WorkflowRunner
        from core.workflow_runner import WorkflowRunner

        runner = WorkflowRunner()
        return cast(list[StepResult], runner.run(self, repo_root, metadata))

    def _eval_condition(self, condition: str, prior: dict[str, StepResult]) -> bool:
        if condition.startswith("not "):
            return not prior.get(
                condition[4:], StepResult(step_id=condition[4:], success=True)
            ).success
        return prior.get(condition, StepResult(step_id=condition, success=True)).success

    @property
    def model_registry(self) -> ModelRegistry:
        return self._model_registry

    @property
    def tool_registry(self) -> ToolRegistry:
        return self._tool_registry

    @property
    def policy_engine(self) -> PolicyEngine:
        return self._policy_engine

    @property
    def ledger(self) -> RunLedger | None:
        return self._ledger

    @ledger.setter
    def ledger(self, value: RunLedger | None) -> None:
        self._ledger = value
