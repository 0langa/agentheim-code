from __future__ import annotations

from typing import Any

from workflows.base import AgentRole, ExecutionDAG, Step, StepContext, StepResult, Workflow


class CoderWorkflow(Workflow):
    workflow_id = "coder"
    support_state = "stable_candidate"
    required_agents = [
        AgentRole(id="planner", capabilities=["text", "json"]),
        AgentRole(id="executor", capabilities=["text", "json"]),
        AgentRole(id="verifier", capabilities=["text", "json"]),
    ]
    required_tools = ["filesystem", "shell.execute"]

    def __init__(
        self, model_registry: Any, tool_registry: Any, policy_engine: Any, ledger: Any
    ) -> None:
        super().__init__(model_registry, tool_registry, policy_engine, ledger)
        self.dag = ExecutionDAG(
            steps=[
                Step(id="session", agent="planner", type="chat"),
            ]
        )

    def execute_step(self, step: Step, context: StepContext) -> StepResult:
        return StepResult(
            step_id=step.id,
            success=True,
            output="Coder sessions execute through the coder runtime.",
        )
