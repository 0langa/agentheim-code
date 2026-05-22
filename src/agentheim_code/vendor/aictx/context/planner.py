"""Context planning stage."""

from __future__ import annotations

from pathlib import Path

from agentheim_code.vendor.aictx.config import AictxConfig
from agentheim_code.vendor.aictx.models.context_lock import ContextLock
from agentheim_code.vendor.aictx.models.inventory import RepositoryInventory


def plan_context(
    inventory: RepositoryInventory,
    existing_context_dir: Path | None = None,
    existing_agents_md: Path | None = None,
    scope: str = "full",
    config: AictxConfig | None = None,
    existing_lock: ContextLock | None = None,
    changed_files: list[str] | None = None,
) -> dict[str, object]:
    """Plan which files to include in the context generation."""
    selected_entries = []
    reasons: dict[str, str] = {}
    warnings: list[str] = []
    changed_set = set(changed_files or [])
    impacted_paths = _determine_impacted_paths(
        inventory=inventory,
        scope=scope,
        existing_lock=existing_lock,
        changed_files=changed_files or [],
    )

    for entry in sorted(inventory.manifests, key=lambda item: item.path):
        if entry.is_generated:
            continue
        if scope == "changed" and entry.path not in impacted_paths:
            continue
        selected_entries.append(entry)
        reasons[entry.path] = _reason_for_entry("manifest", entry.path, changed_set)

    important_docs = {"README.md", "CHANGELOG.md", "ROADMAP.md", "AGENTS.md"}
    for entry in sorted(inventory.docs, key=lambda item: item.path):
        if entry.is_generated:
            continue
        if (
            entry.path in important_docs or entry.path.startswith("docs/")
        ) and entry.path not in reasons:
            if scope == "changed" and entry.path not in impacted_paths:
                continue
            selected_entries.append(entry)
            reasons[entry.path] = _reason_for_entry("doc", entry.path, changed_set)

    for entry in sorted(inventory.files, key=lambda item: item.path):
        if entry.is_ignored or entry.is_binary or entry.is_generated:
            continue
        if scope == "changed" and entry.path not in impacted_paths:
            continue
        if entry.is_source and entry.path not in reasons:
            selected_entries.append(entry)
            reasons[entry.path] = _reason_for_entry("source", entry.path, changed_set)
        elif entry.is_test and entry.path not in reasons:
            selected_entries.append(entry)
            reasons[entry.path] = _reason_for_entry("test", entry.path, changed_set)

    if existing_context_dir and existing_context_dir.exists():
        for path in sorted(existing_context_dir.glob("*.md")):
            rel = path.relative_to(inventory.repo_root).as_posix()
            reasons[rel] = "existing_context"
    if existing_agents_md and existing_agents_md.exists():
        rel = existing_agents_md.relative_to(inventory.repo_root).as_posix()
        reasons[rel] = "existing_agents"

    selected_entries = sorted(selected_entries, key=lambda item: item.path)
    selected_files = [entry.path for entry in selected_entries]
    if config and len(selected_files) > config.limits.max_files_per_run:
        warnings.append("selection exceeds configured max_files_per_run")

    estimated_token_cost = sum(max(entry.size_bytes // 4, 1) for entry in selected_entries)

    return {
        "scope": scope,
        "critical_source_files": [entry.path for entry in selected_entries if entry.is_source],
        "critical_doc_files": [entry.path for entry in selected_entries if entry.is_doc],
        "manifest_files": [entry.path for entry in selected_entries if entry.is_manifest],
        "build_files": [entry.path for entry in selected_entries if entry.is_manifest],
        "test_files": [entry.path for entry in selected_entries if entry.is_test],
        "files_excluded_from_llm": [
            entry.path
            for entry in inventory.files
            if entry.is_ignored or entry.is_binary or entry.is_generated
        ],
        "reason_per_selected_file": reasons,
        "estimated_token_cost": estimated_token_cost,
        "selected_files": selected_files,
        "warnings": warnings,
    }


def _determine_impacted_paths(
    inventory: RepositoryInventory,
    scope: str,
    existing_lock: ContextLock | None,
    changed_files: list[str],
) -> set[str]:
    if scope != "changed":
        return {
            entry.path
            for entry in inventory.files
            if not entry.is_ignored and not entry.is_generated
        }

    changed_set = set(changed_files)
    if existing_lock is None:
        return changed_set

    impacted = set(changed_set)
    impacted.update(_docs_for_changed(existing_lock, changed_set))
    impacted.update(_sources_for_changed_sections(existing_lock, changed_set))
    impacted.update(_manifests_for_changed(inventory))
    return impacted


def _docs_for_changed(existing_lock: ContextLock, changed_set: set[str]) -> set[str]:
    impacted: set[str] = set()
    for entry in existing_lock.change_impact_map:
        if entry.source_glob in changed_set:
            impacted.update(entry.public_doc_paths)
    return impacted


def _sources_for_changed_sections(existing_lock: ContextLock, changed_set: set[str]) -> set[str]:
    impacted_section_ids: set[str] = set()
    for entry in existing_lock.change_impact_map:
        if entry.source_glob in changed_set:
            impacted_section_ids.update(entry.ai_context_sections)

    impacted_paths: set[str] = set()
    for section in existing_lock.sections:
        if section.section_id in impacted_section_ids:
            impacted_paths.update(section.source_paths)
    return impacted_paths


def _manifests_for_changed(inventory: RepositoryInventory) -> set[str]:
    return {entry.path for entry in inventory.manifests if not entry.is_generated}


def _reason_for_entry(base_reason: str, path: str, changed_set: set[str]) -> str:
    if path in changed_set:
        return f"{base_reason}:changed"
    return base_reason
