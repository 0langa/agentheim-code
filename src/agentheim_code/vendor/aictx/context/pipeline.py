"""Local Phase 1 context generation pipeline."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

from agentheim_code.vendor.aictx.config import AictxConfig
from agentheim_code.vendor.aictx.context.fact_extractor import extract_facts
from agentheim_code.vendor.aictx.context.lockfile import load_lockfile, write_lockfile
from agentheim_code.vendor.aictx.context.planner import plan_context
from agentheim_code.vendor.aictx.context.writer import (
    GENERATED_CONTEXT_FILES,
    build_context_lock,
    target_file_for_pack,
    write_context_scaffold,
)
from agentheim_code.vendor.aictx.errors import SafetyError
from agentheim_code.vendor.aictx.io.files import safe_write
from agentheim_code.vendor.aictx.io.patches import make_unified_diff
from agentheim_code.vendor.aictx.llm.transfer import prepare_model_transfer
from agentheim_code.vendor.aictx.models.inventory import RepositoryInventory
from agentheim_code.vendor.aictx.models.run_report import ContextEntropyMetrics, RunReport, TimingMetrics
from agentheim_code.vendor.aictx.scan.scanner import scan_repository
from agentheim_code.vendor.aictx.verify.verifier import determine_changed_source_paths


def run_local_context_pipeline(
    repo_root: Path,
    run_id: str,
    config: AictxConfig,
    scope: Literal["full", "changed"],
    write_mode: Literal["patch", "apply"],
    provider: Any,
    allow_ai: bool = False,
    allow_dirty: bool = False,
) -> RunReport:
    """Run the local Phase 1 context generation pipeline."""
    started_at = datetime.now(UTC)
    total_started = time.perf_counter()
    scan_started = time.perf_counter()
    inventory = scan_repository(repo_root)
    scan_duration_ms = (time.perf_counter() - scan_started) * 1000
    existing_context_dir = repo_root / config.project.context_dir
    existing_agents_md = repo_root / config.project.agents_file
    existing_lock = load_lockfile(existing_context_dir)
    changed_files = determine_changed_source_paths(inventory, existing_lock)

    plan_started = time.perf_counter()
    plan = plan_context(
        inventory=inventory,
        existing_context_dir=existing_context_dir if existing_context_dir.exists() else None,
        existing_agents_md=existing_agents_md if existing_agents_md.exists() else None,
        scope=scope,
        config=config,
        existing_lock=existing_lock,
        changed_files=changed_files,
    )
    plan_duration_ms = (time.perf_counter() - plan_started) * 1000
    typed_plan = cast(dict[str, Any], plan)
    typed_plan["changed_files"] = changed_files if scope == "changed" else []
    transfer_plan = prepare_model_transfer(
        repo_root=repo_root,
        inventory=inventory,
        selected_files=cast(list[str], typed_plan["selected_files"]),
        reason_per_selected_file=cast(dict[str, str], typed_plan["reason_per_selected_file"]),
        config=config,
        allow_ai=allow_ai,
    )
    typed_plan["estimated_token_cost"] = transfer_plan.estimated_input_tokens
    typed_plan["model_transfer"] = transfer_plan.to_dict()
    _ensure_apply_dirty_state_allowed(
        inventory=inventory,
        write_mode=write_mode,
        config=config,
        allow_dirty=allow_dirty,
        selected_files=cast(list[str], typed_plan["selected_files"]),
    )

    _print_transfer_summary(transfer_plan)
    runs_dir = repo_root / ".ai-team" / "runs" / run_id
    out_dir = runs_dir / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_write(
        runs_dir / "provider-metadata.json",
        _json_dump(
            {
                "run_id": run_id,
                "provider": provider.metadata(),
                "model_transfer": transfer_plan.to_dict(),
            }
        ),
    )
    generation_started = time.perf_counter()
    fact_packs = extract_facts(
        repo_root=repo_root, plan=typed_plan, provider=provider, run_id=run_id
    )
    generation_duration_ms = (time.perf_counter() - generation_started) * 1000

    _write_run_artifacts(
        runs_dir=runs_dir,
        inventory=inventory.model_dump(mode="json"),
        plan=typed_plan,
        fact_packs=fact_packs,
    )

    staged_context_dir = out_dir / config.project.context_dir
    generated_paths = write_context_scaffold(
        repo_root=repo_root,
        out_dir=out_dir,
        inventory=inventory,
        plan=typed_plan,
        fact_packs=fact_packs,
        refresh_paths=_changed_scope_refresh_paths(
            scope=scope,
            existing_lock_present=existing_lock is not None,
            changed_files=changed_files,
            fact_packs=fact_packs,
            selected_files=cast(list[str], typed_plan["selected_files"]),
            inventory=inventory,
        ),
    )
    lock = build_context_lock(
        repo_root=repo_root,
        out_dir=out_dir,
        inventory=inventory,
        plan=typed_plan,
        fact_packs=fact_packs,
        generated_paths=generated_paths,
        model_provider=config.llm.provider,
        model_name=config.llm.model,
        existing_lock=existing_lock,
        changed_files=changed_files,
        preserve_existing_sections=scope == "changed",
    )
    write_lockfile(staged_context_dir, lock)
    generated_paths = [*generated_paths, staged_context_dir / "context.lock.json"]

    patch_text = _build_patch(repo_root=repo_root, out_dir=out_dir)
    patch_path = runs_dir / "aictx.patch"
    safe_write(patch_path, patch_text)
    patch_size_bytes = len(patch_text.encode("utf-8"))

    if write_mode == "apply":
        _apply_out_dir(repo_root=repo_root, out_dir=out_dir)

    verify_started = time.perf_counter()
    generated_context_dir = out_dir / config.project.context_dir
    entropy = _compute_context_entropy(generated_context_dir)
    verify_duration_ms = (time.perf_counter() - verify_started) * 1000
    completed_at = datetime.now(UTC)

    report = RunReport(
        run_id=run_id,
        project_path=str(repo_root),
        mode="setup-context",
        scope=scope,
        execution="local",
        write_mode=write_mode,
        started_at=started_at,
        completed_at=completed_at,
        status="success",
        files_scanned=len([f for f in inventory.files if not f.is_ignored]),
        files_selected=len(cast(list[str], typed_plan["selected_files"])),
        tokens_estimated_input=transfer_plan.estimated_input_tokens,
        tokens_estimated_output=transfer_plan.estimated_output_tokens,
        model_calls=len(fact_packs),
        generated_files=[path.relative_to(out_dir).as_posix() for path in generated_paths],
        selected_files=cast(list[str], typed_plan["selected_files"]),
        warnings=[
            *cast(list[str], typed_plan.get("warnings", [])),
            *([entropy.warning] if entropy.warning else []),
            *(
                [f"changed scope detected {len(changed_files)} changed source files"]
                if scope == "changed"
                else []
            ),
        ],
        output_dir=str(out_dir),
        patch_path=str(patch_path),
        patch_size_bytes=patch_size_bytes,
        timing=TimingMetrics(
            scan_duration_ms=scan_duration_ms,
            plan_duration_ms=plan_duration_ms,
            generation_duration_ms=generation_duration_ms,
            verify_duration_ms=verify_duration_ms,
            total_duration_ms=(time.perf_counter() - total_started) * 1000,
        ),
        entropy=entropy,
    )
    safe_write(runs_dir / "run-report.json", report.model_dump_json(indent=2) + "\n")
    return report


def _build_patch(repo_root: Path, out_dir: Path) -> str:
    patches: list[str] = []
    for generated_file in sorted(out_dir.rglob("*")):
        if not generated_file.is_file():
            continue
        relative = generated_file.relative_to(out_dir)
        repo_target = repo_root / relative
        original = repo_target.read_text(encoding="utf-8") if repo_target.exists() else ""
        updated = generated_file.read_text(encoding="utf-8")
        if original == updated:
            continue
        from_name = f"a/{relative.as_posix()}" if repo_target.exists() else "/dev/null"
        to_name = f"b/{relative.as_posix()}"
        patches.append(make_unified_diff(original, updated, from_name, to_name))
    return "".join(patches)


def _apply_out_dir(repo_root: Path, out_dir: Path) -> None:
    for generated_file in out_dir.rglob("*"):
        if not generated_file.is_file():
            continue
        relative = generated_file.relative_to(out_dir)
        target = repo_root / relative
        safe_write(target, generated_file.read_text(encoding="utf-8"))


def _ensure_apply_dirty_state_allowed(
    inventory: RepositoryInventory,
    write_mode: Literal["patch", "apply"],
    config: AictxConfig,
    allow_dirty: bool,
    selected_files: list[str],
) -> None:
    if write_mode != "apply" or not inventory.dirty_state:
        return
    if config.execution.allow_dirty or allow_dirty:
        return
    dirty_paths = _dirty_paths(inventory)
    allowed_paths = set(selected_files)
    allowed_paths.update(_lock_refreshable_paths(inventory))
    allowed_paths.update(GENERATED_CONTEXT_FILES)
    allowed_paths.add("docs/AIprojectcontext/context.lock.json")
    disallowed = sorted(
        path for path in dirty_paths if path not in allowed_paths and not path.startswith(".aictx/")
    )
    if disallowed:
        preview = ", ".join(disallowed[:5])
        raise SafetyError(
            "Refusing --write apply with dirty paths outside planned context refresh: "
            f"{preview}. Use --allow-dirty to override."
        )


def _dirty_paths(inventory: RepositoryInventory) -> set[str]:
    status = inventory.git_status
    paths = set(status.modified_files)
    paths.update(status.deleted_files)
    paths.update(status.untracked_files)
    for item in status.renamed_files:
        paths.add(str(item["from"]))
        paths.add(str(item["to"]))
    return paths


def _lock_refreshable_paths(inventory: RepositoryInventory) -> set[str]:
    return {
        file.path
        for file in inventory.files
        if file.kind in {"source", "doc", "manifest", "test"}
        and not file.is_ignored
        and not file.is_binary
        and not file.is_generated
        and file.sha256 != "skipped"
    }


def _changed_scope_refresh_paths(
    scope: Literal["full", "changed"],
    existing_lock_present: bool,
    changed_files: list[str],
    fact_packs: list[dict[str, Any]],
    selected_files: list[str],
    inventory: RepositoryInventory,
) -> set[str] | None:
    if scope != "changed" or not existing_lock_present:
        return None

    refresh = {
        "docs/AIprojectcontext/project-state.md",
        "docs/AIprojectcontext/code-map.md",
        "docs/AIprojectcontext/change-impact-map.md",
        "docs/AIprojectcontext/validation-report.md",
    }
    selected_entries = {
        entry.path: entry for entry in inventory.files if entry.path in set(selected_files)
    }
    changed_set = set(changed_files)
    for pack in fact_packs:
        pack_name = str(pack["name"])
        target = target_file_for_pack(pack_name)
        if target == "docs/AIprojectcontext/public-docs-map.md" and not any(
            selected_entries[path].is_doc for path in selected_entries if path in changed_set
        ):
            continue
        refresh.add(target)
    return refresh


def _compute_context_entropy(context_dir: Path) -> ContextEntropyMetrics:
    if not context_dir.exists():
        return ContextEntropyMetrics()

    files = sorted(path for path in context_dir.rglob("*.md") if path.is_file())
    total_bytes = 0
    total_sections = 0
    paragraph_counts: dict[str, int] = {}
    redundant_sections = 0
    unused_shards = 0

    for path in files:
        text = path.read_text(encoding="utf-8")
        total_bytes += len(text.encode("utf-8"))
        sections = [line.strip() for line in text.splitlines() if line.startswith("#")]
        total_sections += len(sections)
        if text.strip() == "":
            unused_shards += 1
        paragraphs = {" ".join(chunk.split()) for chunk in text.split("\n\n") if chunk.strip()}
        for paragraph in paragraphs:
            paragraph_counts[paragraph] = paragraph_counts.get(paragraph, 0) + 1
        redundant_sections += max(0, len(sections) - len(set(sections)))

    duplicate_facts = sum(count - 1 for count in paragraph_counts.values() if count > 1)
    denom = max(total_sections + len(paragraph_counts), 1)
    redundancy_ratio = round((duplicate_facts + redundant_sections) / denom, 4)
    warning = None
    if redundancy_ratio >= 0.2 or unused_shards > 0:
        warning = (
            "context entropy elevated"
            f" (redundancy_ratio={redundancy_ratio}, unused_shards={unused_shards})"
        )

    return ContextEntropyMetrics(
        total_bytes=total_bytes,
        total_sections=total_sections,
        duplicate_facts=duplicate_facts,
        redundant_sections=redundant_sections,
        unused_shards=unused_shards,
        estimated_redundancy_ratio=redundancy_ratio,
        warning=warning,
    )


def _write_run_artifacts(
    runs_dir: Path,
    inventory: dict[str, Any],
    plan: dict[str, Any],
    fact_packs: list[dict[str, Any]],
) -> None:
    safe_write(runs_dir / "inventory.json", _json_dump(inventory))
    safe_write(runs_dir / "context-plan.json", _json_dump(plan))
    facts_dir = runs_dir / "facts"
    pack_name_map = {
        "project_identity": "project_identity",
        "architecture": "architecture",
        "feature": "feature",
        "workflow": "workflow",
        "docs": "docs",
        "risk": "risk",
    }
    seen_pack_names: set[str] = set()
    for pack in fact_packs:
        pack_name = pack_name_map.get(str(pack["name"]), str(pack["name"]))
        seen_pack_names.add(pack_name)
        safe_write(facts_dir / f"{pack_name}_facts.json", _json_dump(pack))
    for expected_pack_name in pack_name_map.values():
        if expected_pack_name in seen_pack_names:
            continue
        safe_write(
            facts_dir / f"{expected_pack_name}_facts.json",
            _json_dump(
                {
                    "name": expected_pack_name,
                    "facts": [],
                    "summary": "No deterministic facts extracted.",
                    "estimated_output_tokens": 0,
                }
            ),
        )
    safe_write(
        runs_dir / "coverage-report.json", _json_dump({"status": "deterministic", "missing": []})
    )
    safe_write(
        runs_dir / "contradictions.json", _json_dump({"status": "none", "contradictions": []})
    )


def _json_dump(payload: Any) -> str:
    import json

    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _print_transfer_summary(transfer_plan: Any) -> None:
    from rich.console import Console

    console = Console()
    console.print("[bold blue]transfer plan[/bold blue]")
    console.print(f"provider: {transfer_plan.provider}, model: {transfer_plan.model}")
    console.print(f"files: {len(transfer_plan.selected_files)}")
    console.print(f"estimated input tokens: {transfer_plan.estimated_input_tokens}")
    console.print(f"estimated output tokens: {transfer_plan.estimated_output_tokens}")
    console.print(f"max input: {transfer_plan.max_input_tokens_per_run}")
    console.print(f"max output: {transfer_plan.max_output_tokens_per_run}")
