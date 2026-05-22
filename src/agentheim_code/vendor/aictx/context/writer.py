"""AI context scaffold writer."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agentheim_code.vendor.aictx import __version__
from agentheim_code.vendor.aictx.context.agents_md import generate_agents_md
from agentheim_code.vendor.aictx.io.files import safe_write
from agentheim_code.vendor.aictx.models.context_lock import (
    ChangeImpactMapEntry,
    ContextLock,
    GeneratedFileEntry,
    PublicDocsMapEntry,
    SectionEntry,
    SourceFileEntry,
)
from agentheim_code.vendor.aictx.models.inventory import RepositoryInventory
from agentheim_code.vendor.aictx.public_docs.mapper import build_public_docs_map_from_inventory
from agentheim_code.vendor.aictx.verify.hashes import sha256_file, sha256_text

GENERATED_CONTEXT_FILES = {
    "docs/AIprojectcontext/ai-index.md",
    "docs/AIprojectcontext/project-state.md",
    "docs/AIprojectcontext/code-map.md",
    "docs/AIprojectcontext/architecture.md",
    "docs/AIprojectcontext/workflows.md",
    "docs/AIprojectcontext/public-docs-map.md",
    "docs/AIprojectcontext/change-impact-map.md",
    "docs/AIprojectcontext/schema.md",
    "docs/AIprojectcontext/validation-report.md",
    "AGENTS.md",
}


def write_context_scaffold(
    repo_root: Path,
    out_dir: Path,
    inventory: RepositoryInventory,
    plan: dict[str, Any],
    fact_packs: list[dict[str, Any]],
    refresh_paths: set[str] | None = None,
) -> list[Path]:
    """Write compact AI-facing context files to *out_dir*."""
    generated: list[Path] = []
    selected_files = plan["selected_files"]
    reasons = plan["reason_per_selected_file"]
    fact_map = {pack["name"]: pack for pack in fact_packs}
    existing_agents_md = _read_existing_agents_md(repo_root)

    files_to_content = {
        "docs/AIprojectcontext/ai-index.md": _render_ai_index(),
        "docs/AIprojectcontext/project-state.md": _render_project_state(inventory, plan, fact_map),
        "docs/AIprojectcontext/code-map.md": _render_code_map(plan),
        "docs/AIprojectcontext/architecture.md": _render_architecture(fact_map),
        "docs/AIprojectcontext/workflows.md": _render_workflows(inventory, fact_map),
        "docs/AIprojectcontext/public-docs-map.md": _render_public_docs_map(inventory),
        "docs/AIprojectcontext/change-impact-map.md": _render_change_impact_map(
            selected_files, reasons
        ),
        "docs/AIprojectcontext/schema.md": _render_schema(),
        "docs/AIprojectcontext/validation-report.md": _render_validation_report(fact_packs),
        "AGENTS.md": generate_agents_md(repo_root.name, existing_agents_md),
    }

    for relative_name, content in files_to_content.items():
        if refresh_paths is not None and relative_name not in refresh_paths:
            existing = repo_root / relative_name
            if existing.exists():
                content = existing.read_text(encoding="utf-8")
        target = out_dir / relative_name
        safe_write(target, content)
        generated.append(target)
    return generated


def _read_existing_agents_md(repo_root: Path) -> str | None:
    path = repo_root / "AGENTS.md"
    if not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def build_context_lock(
    repo_root: Path,
    out_dir: Path,
    inventory: RepositoryInventory,
    plan: dict[str, Any],
    fact_packs: list[dict[str, Any]],
    generated_paths: list[Path],
    model_provider: str,
    model_name: str,
    existing_lock: ContextLock | None = None,
    changed_files: list[str] | None = None,
    preserve_existing_sections: bool = False,
) -> ContextLock:
    """Build a Phase 1 lockfile for generated context artifacts."""
    selected_set = set(plan["selected_files"])
    source_files = [
        SourceFileEntry(
            path=file.path,
            sha256=file.sha256,
            kind=file.kind,
            included_in_generation=file.path in selected_set,
        )
        for file in inventory.files
        if not file.is_ignored
        and not file.is_binary
        and not file.is_generated
        and file.sha256 != "skipped"
        and file.path != "docs/AIprojectcontext/context.lock.json"
    ]
    source_files.sort(key=lambda entry: entry.path)
    source_hashes_by_path = {entry.path: entry.sha256 for entry in source_files}

    new_sections: list[SectionEntry] = []
    for pack in fact_packs:
        for fact in pack["facts"]:
            source_hashes = []
            for source_path in fact["source_paths"]:
                source_hashes.append(source_hashes_by_path.get(str(source_path), "unknown"))
            new_sections.append(
                SectionEntry(
                    section_id=fact["id"],
                    generated_file=target_file_for_pack(pack["name"]),
                    heading=pack["name"],
                    source_paths=fact["source_paths"],
                    source_hashes=source_hashes,
                    fact_ids=[fact["id"]],
                    status="current",
                )
            )
    sections = _merge_changed_scope_sections(
        existing_lock=existing_lock,
        new_sections=new_sections,
        changed_files=set(changed_files or []),
        source_hashes_by_path=source_hashes_by_path,
        preserve_existing_sections=preserve_existing_sections,
    )

    public_docs_map = _build_public_docs_lock_entries(inventory=inventory)

    section_ids_by_source: dict[str, set[str]] = {}
    for section in sections:
        for source_path in section.source_paths:
            section_ids_by_source.setdefault(source_path, set()).add(section.section_id)
    public_docs_by_source: dict[str, set[str]] = {}
    for doc_entry in public_docs_map:
        for source_path in doc_entry.source_paths:
            public_docs_by_source.setdefault(source_path, set()).add(doc_entry.path)
    change_impact_map = [
        ChangeImpactMapEntry(
            source_glob=source.path,
            ai_context_sections=sorted(section_ids_by_source.get(source.path, set())),
            public_doc_paths=sorted(public_docs_by_source.get(source.path, set())),
            no_impact_reason=None
            if source.path in section_ids_by_source or source.path in public_docs_by_source
            else "No generated context or public-doc link.",
        )
        for source in source_files
    ]

    generated_files = [
        GeneratedFileEntry(
            path=path.relative_to(out_dir).as_posix(),
            sha256=sha256_file(path),
            generated_from_sections=[
                section.section_id
                for section in sections
                if section.generated_file == path.relative_to(out_dir).as_posix()
            ],
        )
        for path in sorted(generated_paths, key=lambda item: path_relative_to_out(item, out_dir))
    ]

    return ContextLock(
        tool_version=__version__,
        repo_head_commit=inventory.head_commit,
        model_provider=model_provider,
        model_name=model_name,
        scanner_config_hash=sha256_text("\n".join(sorted(plan["selected_files"]))),
        generated_files=generated_files,
        source_files=source_files,
        sections=sections,
        public_docs_map=public_docs_map,
        change_impact_map=change_impact_map,
    )


def _build_public_docs_lock_entries(inventory: RepositoryInventory) -> list[PublicDocsMapEntry]:
    """Build public-doc lock entries from current source hashes."""
    return [
        PublicDocsMapEntry(**entry.model_dump())
        for entry in build_public_docs_map_from_inventory(inventory).entries
    ]


def _merge_changed_scope_sections(
    existing_lock: ContextLock | None,
    new_sections: list[SectionEntry],
    changed_files: set[str],
    source_hashes_by_path: dict[str, str],
    preserve_existing_sections: bool,
) -> list[SectionEntry]:
    """Preserve unchanged lock sections during changed-scope refresh."""
    if existing_lock is None or not preserve_existing_sections:
        return sorted(new_sections, key=lambda entry: entry.section_id)
    if not changed_files:
        return sorted(existing_lock.sections, key=lambda entry: entry.section_id)

    new_ids = {section.section_id for section in new_sections}
    preserved: list[SectionEntry] = []
    for section in existing_lock.sections:
        if section.section_id in new_ids:
            continue
        if changed_files.intersection(section.source_paths):
            continue
        if not _section_sources_current(section, source_hashes_by_path):
            continue
        preserved.append(section)
    return sorted([*preserved, *new_sections], key=lambda entry: entry.section_id)


def _section_sources_current(
    section: SectionEntry,
    source_hashes_by_path: dict[str, str],
) -> bool:
    if len(section.source_paths) != len(section.source_hashes):
        return False
    for source_path, source_hash in zip(section.source_paths, section.source_hashes, strict=True):
        if source_hashes_by_path.get(source_path) != source_hash:
            return False
    return True


def _render_ai_index() -> str:
    return """# AI Index

- `project-state.md` — project identity, status, selected scope
- `code-map.md` — selected source and test files
- `architecture.md` — source-traced architecture facts
- `workflows.md` — build, test, and manifest workflow facts
- `public-docs-map.md` — mapped public docs
- `change-impact-map.md` — selected file to context mapping
- `validation-report.md` — fact-pack and validation summary
"""


def _render_project_state(
    inventory: RepositoryInventory,
    plan: dict[str, Any],
    fact_map: dict[str, dict[str, Any]],
) -> str:
    lines = [
        "# Project State",
        "",
        f"- repo_root: `{inventory.repo_root}`",
        f"- branch: `{inventory.branch}`",
        f"- head_commit: `{inventory.head_commit}`",
        f"- dirty_state: `{inventory.dirty_state}`",
        f"- project_type: `{inventory.project_classification.get('project_type', 'unknown')}`",
        f"- primary_language: `{inventory.project_classification.get('primary_language', 'unknown')}`",
        f"- selected_files: `{len(plan['selected_files'])}`",
        f"- estimated_token_cost: `{plan['estimated_token_cost']}`",
        "",
        "## Identity Facts",
    ]
    for fact in fact_map.get("project_identity", {}).get("facts", []):
        lines.append(f"- {fact['claim']} [source: {', '.join(fact['source_paths'])}]")
    return "\n".join(lines) + "\n"


def _render_code_map(plan: dict[str, Any]) -> str:
    lines = ["# Code Map", "", "## Selected Files"]
    reasons = plan["reason_per_selected_file"]
    for path in plan["selected_files"]:
        lines.append(f"- `{path}` — {reasons[path]}")
    return "\n".join(lines) + "\n"


def _render_architecture(fact_map: dict[str, dict[str, Any]]) -> str:
    lines = ["# Architecture", "", "## Architecture Facts"]
    for fact in fact_map.get("architecture", {}).get("facts", []):
        lines.append(f"- {fact['claim']} [source: {', '.join(fact['source_paths'])}]")
    if len(lines) == 3:
        lines.append("- unknown")
    return "\n".join(lines) + "\n"


def _render_workflows(inventory: RepositoryInventory, fact_map: dict[str, dict[str, Any]]) -> str:
    lines = ["# Workflows", "", "## Build and Test Signals"]
    lines.append(f"- build_systems: {', '.join(inventory.build_systems) or 'unknown'}")
    lines.append(f"- test_system: {inventory.project_classification.get('test_system', 'unknown')}")
    for fact in fact_map.get("workflow", {}).get("facts", []):
        lines.append(f"- {fact['claim']} [source: {', '.join(fact['source_paths'])}]")
    return "\n".join(lines) + "\n"


def _render_public_docs_map(inventory: RepositoryInventory) -> str:
    lines = ["# Public Docs Map", "", "## Docs"]
    for entry in inventory.docs:
        lines.append(f"- `{entry.path}` — markdown/doc source")
    return "\n".join(lines) + "\n"


def _render_change_impact_map(selected_files: list[str], reasons: dict[str, str]) -> str:
    lines = ["# Change Impact Map", "", "## Selected File Impact"]
    for path in selected_files:
        lines.append(f"- `{path}` -> ai:{reasons[path]}")
    return "\n".join(lines) + "\n"


def _render_schema() -> str:
    return """# Schema

- fact packs: project_identity, architecture, feature, workflow, docs, risk
- lockfile schema version: 1.0
- verification mode: deterministic hashes plus generated section/source linkage
"""


def _render_validation_report(fact_packs: list[dict[str, Any]]) -> str:
    lines = ["# Validation Report", "", "## Fact Packs"]
    for pack in fact_packs:
        lines.append(f"- `{pack['name']}` — facts: {len(pack['facts'])}")
    return "\n".join(lines) + "\n"


def path_relative_to_out(path: Path, out_dir: Path) -> str:
    """Return a deterministic output-relative path for generated files."""
    return path.relative_to(out_dir).as_posix()


def target_file_for_pack(pack_name: str) -> str:
    """Return generated context file for a fact pack name."""
    return {
        "project_identity": "docs/AIprojectcontext/project-state.md",
        "architecture": "docs/AIprojectcontext/architecture.md",
        "feature": "docs/AIprojectcontext/code-map.md",
        "workflow": "docs/AIprojectcontext/workflows.md",
        "docs": "docs/AIprojectcontext/public-docs-map.md",
        "risk": "docs/AIprojectcontext/validation-report.md",
    }.get(pack_name, "docs/AIprojectcontext/validation-report.md")
