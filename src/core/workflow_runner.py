"""Generic DAG workflow execution engine.

Replaces the sequential for-loop in `Workflow.run()` with a production runner
that supports: topological order, parallel groups, retry, budget enforcement,
workspace isolation, structured event emission, and graceful error handling.
"""

from __future__ import annotations

import concurrent.futures
import logging
from pathlib import Path
from typing import Any

from core.error_classification import classify_error, should_halt
from core.events import EventType
from core.replay_engine import ReplayEngine
from core.retry_engine import RetryEngine, RetryExhaustedError
from core.run_summary import write_diagnostics_bundle
from core.step_budget import BudgetExceededError, BudgetLimits, StepBudgetEnforcer
from memory.tiers.working import WorkingMemory
from workflows.base import Step, StepContext, StepResult, Workflow

logger = logging.getLogger("core.workflow_runner")


class WorkflowRunner:
    """Production workflow execution engine.

    Usage::

        runner = WorkflowRunner()
        results = runner.run(workflow, repo_root=Path("."), metadata={"topic": "AI"})
    """

    def __init__(
        self,
        *,
        max_workers: int = 5,
        default_budget: BudgetLimits | None = None,
    ) -> None:
        self.max_workers = max_workers
        self.default_budget = default_budget or BudgetLimits(
            max_tokens=1_000_000,
            max_time_seconds=600,
            max_tool_calls=100,
            max_agent_invocations=50,
        )

    def run(
        self,
        workflow: Workflow,
        repo_root: Path,
        metadata: dict[str, Any] | None = None,
        *,
        resume_from: str | None = None,
        stale_context_check: bool = False,
    ) -> list[StepResult]:
        """Execute *workflow* against *repo_root*.

        Args:
            workflow: The workflow to run.
            repo_root: Repository root path.
            metadata: Optional metadata dict.
            resume_from: Optional run_id to resume from.  When provided, the
                existing ledger is replayed to reconstruct ``prior`` results,
                and only remaining steps are executed.

        Returns:
            List of StepResult in DAG topological order.
        """
        if workflow.dag is None:
            raise RuntimeError("Workflow DAG not defined")

        dag = workflow.dag
        ledger = workflow.ledger
        run_id = ledger.run_dir.name if ledger else "unknown"

        # Resume mode: replay existing ledger to reconstruct prior results
        prior: dict[str, StepResult] = {}
        if resume_from and ledger is not None:
            replay = ReplayEngine()
            state = replay.replay(ledger.read_ledger())
            prior = dict(state.prior_results)
            ledger.emit_event(
                EventType.RUN_RESUMED,
                payload={
                    "run_id": resume_from,
                    "completed_steps": sorted(state.completed_steps),
                    "failed_steps": sorted(state.failed_steps),
                    "skipped_steps": sorted(state.skipped_steps),
                    "checkpoint_sequence": state.checkpoint_sequence,
                },
            )

        # Emit run start
        if ledger is not None:
            ledger.emit_event(
                EventType.RUN_INITIATED,
                payload={
                    "workflow_id": workflow.workflow_id,
                    "repo_root": str(repo_root),
                    "metadata": metadata or {},
                },
            )

        # Working memory (ephemeral, flushed at end)
        working_mem = WorkingMemory(ledger=ledger)

        # Budget enforcer for the entire run
        budget = self.default_budget
        enforcer = StepBudgetEnforcer(limits=budget, ledger=ledger, run_id=run_id)

        # Retry engine
        retry_engine = RetryEngine(ledger=ledger)

        # Results accumulator
        results: list[StepResult] = []
        # ``prior`` may already contain resumed results

        # Agentheim Code is standalone and does not bundle the legacy context
        # indexing subsystem. Keep this preflight fail-closed instead of
        # importing optional indexing machinery.
        self._context_stale: bool = False
        if stale_context_check and ledger is not None:
            ledger.emit_event(
                EventType.CONTEXT_STALE_DETECTED,
                payload={
                    "is_stale": False,
                    "next_command": None,
                    "stale_sources": [],
                    "missing_sources": [],
                    "missing_generated": [],
                    "generated_mismatches": [],
                    "check_skipped": (
                        "Agentheim Code standalone runtime does not bundle legacy context indexing."
                    ),
                },
            )

        try:
            # Execute DAG
            groups = dag.parallel_groups()
            for group_idx, group in enumerate(groups):
                # In resume mode, skip steps that already succeeded or were skipped.
                # Failed steps are re-executed so they can potentially recover.
                if resume_from:
                    group = [s for s in group if s.id not in prior or not prior[s.id].success]
                    if not group:
                        continue

                if ledger is not None:
                    ledger.emit_event(
                        EventType.PHASE_TRANSITION,
                        payload={
                            "group_index": group_idx,
                            "group_size": len(group),
                            "step_ids": [s.id for s in group],
                        },
                    )

                # Determine if this group can run in parallel
                parallel_safe = all(s.parallel_safe for s in group)

                if parallel_safe and len(group) > 1:
                    group_results = self._run_parallel_group(
                        workflow=workflow,
                        steps=group,
                        repo_root=repo_root,
                        prior=prior,
                        enforcer=enforcer,
                        retry_engine=retry_engine,
                        metadata=metadata or {},
                        working_mem=working_mem,
                    )
                else:
                    group_results = self._run_sequential_group(
                        workflow=workflow,
                        steps=group,
                        repo_root=repo_root,
                        prior=prior,
                        enforcer=enforcer,
                        retry_engine=retry_engine,
                        metadata=metadata or {},
                        working_mem=working_mem,
                    )

                for result in group_results:
                    results.append(result)
                    prior[result.step_id] = result

                # Auto-checkpoint after each successful group
                if ledger is not None and all(r.success for r in group_results):
                    ledger.save_checkpoint(
                        {"completed_steps": sorted(prior.keys())},
                        ledger._sequence,
                    )

                # Halt if any step in this group failed
                failed = [r for r in group_results if not r.success]
                if failed:
                    first_fail = failed[0]
                    if ledger is not None:
                        ledger.emit_event(
                            EventType.RUN_FAILED,
                            payload={
                                "failed_step": first_fail.step_id,
                                "reason": first_fail.metadata.get("error", "step failed"),
                            },
                        )
                        try:
                            write_diagnostics_bundle(ledger.run_dir, run_id)
                        except Exception as _exc:
                            logger.warning(
                                "Failed to write diagnostics bundle for run_id=%s: %s", run_id, _exc
                            )
                    workflow.on_run_complete(results)
                    return results

            # Success path
            if ledger is not None:
                ledger.emit_event(
                    EventType.RUN_COMPLETED,
                    payload={
                        "step_count": len(results),
                        "success_count": sum(1 for r in results if r.success),
                    },
                )
            workflow.on_run_complete(results)
            return results

        except Exception as exc:
            if ledger is not None:
                ledger.emit_event(
                    EventType.RUN_FAILED,
                    payload={
                        "reason": str(exc),
                        "error_type": type(exc).__name__,
                    },
                )
                try:
                    write_diagnostics_bundle(ledger.run_dir, run_id)
                except Exception as _exc:
                    logger.warning(
                        "Failed to write diagnostics bundle for run_id=%s: %s", run_id, _exc
                    )
            workflow.on_run_complete(results)
            raise
        finally:
            working_mem.flush()

    # ------------------------------------------------------------------
    # Group execution
    # ------------------------------------------------------------------

    def _run_sequential_group(
        self,
        workflow: Workflow,
        steps: list[Step],
        repo_root: Path,
        prior: dict[str, StepResult],
        enforcer: StepBudgetEnforcer,
        retry_engine: RetryEngine,
        metadata: dict[str, Any],
        working_mem: WorkingMemory,
    ) -> list[StepResult]:
        """Run steps one at a time."""
        results: list[StepResult] = []
        for step in steps:
            result = self._run_step(
                workflow=workflow,
                step=step,
                repo_root=repo_root,
                prior=prior,
                enforcer=enforcer,
                retry_engine=retry_engine,
                metadata=metadata,
                working_mem=working_mem,
            )
            results.append(result)
            prior[result.step_id] = result
            if not result.success:
                break
        return results

    def _run_parallel_group(
        self,
        workflow: Workflow,
        steps: list[Step],
        repo_root: Path,
        prior: dict[str, StepResult],
        enforcer: StepBudgetEnforcer,
        retry_engine: RetryEngine,
        metadata: dict[str, Any],
        working_mem: WorkingMemory,
    ) -> list[StepResult]:
        """Run steps concurrently using a thread pool.

        Each step gets a snapshot of *prior* so there are no race conditions.
        """
        results_map: dict[str, StepResult] = {}
        prior_snapshot = dict(prior)

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            futures = {
                pool.submit(
                    self._run_step,
                    workflow=workflow,
                    step=step,
                    repo_root=repo_root,
                    prior=prior_snapshot,
                    enforcer=enforcer,
                    retry_engine=retry_engine,
                    metadata=metadata,
                    working_mem=working_mem,
                ): step
                for step in steps
            }

            for future in concurrent.futures.as_completed(futures):
                step = futures[future]
                try:
                    result = future.result()
                except Exception as exc:
                    result = StepResult(
                        step_id=step.id,
                        success=False,
                        output="",
                        metadata={"error": str(exc), "error_type": type(exc).__name__},
                    )
                results_map[step.id] = result

        # Return in step order (not completion order)
        return [results_map[s.id] for s in steps]

    # ------------------------------------------------------------------
    # Single step
    # ------------------------------------------------------------------

    def _run_step(
        self,
        workflow: Workflow,
        step: Step,
        repo_root: Path,
        prior: dict[str, Any],
        enforcer: StepBudgetEnforcer,
        retry_engine: RetryEngine,
        metadata: dict[str, Any],
        working_mem: WorkingMemory,
    ) -> StepResult:
        """Execute a single step with budget check, retry, and workspace isolation."""
        ledger = workflow.ledger
        run_id = ledger.run_dir.name if ledger else "unknown"

        # Condition check
        if step.condition and not self._eval_condition(step.condition, prior):
            if ledger is not None:
                ledger.emit_event(
                    EventType.STATE_TRANSITION,
                    step_id=step.id,
                    payload={"from": "pending", "to": "skipped", "reason": "condition"},
                )
            return StepResult(step_id=step.id, success=True, output="Skipped by condition")

        # Budget check before step
        try:
            enforcer.check_budget(operation=f"step:{step.id}", step_id=step.id)
        except BudgetExceededError as exc:
            return StepResult(
                step_id=step.id,
                success=False,
                output=f"Budget exceeded: {exc}",
                metadata={"halt_reason": "budget", "error": str(exc)},
            )

        # Workspace isolation
        workspace = repo_root
        if step.workspace_isolation and ledger is not None:
            ws_path = ledger.run_dir / "workspaces" / step.id
            ws_path.mkdir(parents=True, exist_ok=True)
            workspace = ws_path

        # Build context
        context = StepContext(
            run_id=run_id,
            step_id=step.id,
            repo_root=workspace,
            tools=workflow.tool_registry,
            policy=workflow.policy_engine,
            ledger=ledger,
            working_memory=working_mem,
            prior_results=prior,
            metadata={**metadata, "original_repo_root": str(repo_root)},
        )

        # Emit agent invocation event
        if ledger is not None:
            ledger.emit_event(
                EventType.AGENT_INVOKED,
                step_id=step.id,
                agent_id=step.agent,
                payload={"step_type": step.type, "parallel_safe": step.parallel_safe},
            )

        # Execute with retry
        max_retries = max(0, step.max_iterations - 1)

        def _execute() -> StepResult:
            return workflow.execute_step(step, context)

        try:
            if max_retries > 0:
                result = retry_engine.execute(
                    _execute,
                    max_retries=max_retries,
                    step_id=step.id,
                    run_id=run_id,
                )
            else:
                result = _execute()

            # Record agent invocation consumption
            enforcer.record_agent_invocation(step_id=step.id)

        except RetryExhaustedError as exc:
            result = StepResult(
                step_id=step.id,
                success=False,
                output="",
                metadata={"error": str(exc), "error_type": type(exc.last_exception).__name__},
            )
        except Exception as exc:
            category = classify_error(exc)
            if should_halt(category):
                raise
            result = StepResult(
                step_id=step.id,
                success=False,
                output="",
                metadata={
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "category": category.value,
                },
            )

        # Emit state transition
        if ledger is not None:
            ledger.emit_event(
                EventType.STATE_TRANSITION,
                step_id=step.id,
                payload={
                    "from": "running",
                    "to": "completed" if result.success else "failed",
                    "output_preview": result.output[:200] if result.output else "",
                },
            )

        workflow.on_step_complete(step, result)
        return result

    # ------------------------------------------------------------------
    # Condition evaluation
    # ------------------------------------------------------------------

    def _eval_condition(self, condition: str, prior: dict[str, StepResult]) -> bool:
        """Evaluate a step condition against prior results.

        Supports:
        - "step_id" → True if that step succeeded
        - "not step_id" → True if that step failed or is absent
        - "context_fresh" → True if context is not stale (requires stale_context_check)
        - "context_stale" → True if context is stale (requires stale_context_check)
        """
        if condition == "context_fresh":
            return not getattr(self, "_context_stale", False)
        if condition == "context_stale":
            return getattr(self, "_context_stale", False)
        if condition.startswith("not "):
            target = condition[4:]
            prev = prior.get(target, StepResult(step_id=target, success=True))
            return not prev.success
        prev = prior.get(condition, StepResult(step_id=condition, success=True))
        return prev.success
