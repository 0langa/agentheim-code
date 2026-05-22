"""Strict verifier implementation."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from agentheim_code.vendor.aictx.context.lockfile import SUPPORTED_SCHEMA_VERSIONS, load_lockfile
from agentheim_code.vendor.aictx.models.context_lock import ContextLock
from agentheim_code.vendor.aictx.models.inventory import RepositoryInventory
from agentheim_code.vendor.aictx.scan.ignore import IgnoreMatcher
from agentheim_code.vendor.aictx.verify.hashes import sha256_file

VerificationResult = Literal[
    "PASS",
    "FAIL_STALE_AI_CONTEXT",
    "FAIL_PUBLIC_DOCS_IMPACT",
    "FAIL_LOCK_MISMATCH",
    "FAIL_MISSING_SOURCE",
    "FAIL_UNSUPPORTED_SCHEMA",
]

REQUIRED_GENERATED_CONTEXT_FILES = {
    "AGENTS.md",
    "docs/AIprojectcontext/ai-index.md",
    "docs/AIprojectcontext/project-state.md",
    "docs/AIprojectcontext/code-map.md",
    "docs/AIprojectcontext/architecture.md",
    "docs/AIprojectcontext/workflows.md",
    "docs/AIprojectcontext/public-docs-map.md",
    "docs/AIprojectcontext/change-impact-map.md",
    "docs/AIprojectcontext/schema.md",
}


class VerificationReport(BaseModel):
    """Detailed verification result for CLI and automation."""

    result: VerificationResult
    strict: bool = False
    lock_path: str = "docs/AIprojectcontext/context.lock.json"
    missing_sources: list[str] = Field(default_factory=list)
    stale_sources: list[str] = Field(default_factory=list)
    missing_generated: list[str] = Field(default_factory=list)
    generated_mismatches: list[str] = Field(default_factory=list)
    section_errors: list[str] = Field(default_factory=list)
    public_docs_impacts: dict[str, list[str]] = Field(default_factory=dict)
    next_command: str | None = None

    def to_machine_dict(self) -> dict[str, object]:
        """Return stable machine-readable schema for CLI automation."""
        errors: list[str] = []
        errors.extend(f"missing source: {path}" for path in self.missing_sources)
        errors.extend(f"stale source: {path}" for path in self.stale_sources)
        errors.extend(f"missing generated: {path}" for path in self.missing_generated)
        errors.extend(f"generated mismatch: {path}" for path in self.generated_mismatches)
        errors.extend(self.section_errors)
        warnings = ["public docs impacted"] if self.public_docs_impacts else []
        return {
            "status": self.result,
            "stale_sections": self.section_errors,
            "docs_impacts": self.public_docs_impacts,
            "missing_sources": self.missing_sources,
            "warnings": warnings,
            "errors": errors,
            "next_command": self.next_command,
        }


def verify(repo_root: Path, strict: bool = False) -> VerificationResult:
    """Run verification against the repository."""
    return verify_detailed(repo_root, strict=strict).result


def verify_detailed(repo_root: Path, strict: bool = False) -> VerificationReport:
    """Run verification and return structured details."""
    context_dir = repo_root / "docs" / "AIprojectcontext"
    lock = load_lockfile(context_dir)
    if lock is None:
        return VerificationReport(
            result="FAIL_LOCK_MISMATCH",
            strict=strict,
            next_command="aictx init --project .",
        )

    if lock.schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        return VerificationReport(result="FAIL_UNSUPPORTED_SCHEMA", strict=strict)

    source_hashes_by_path = {
        source_file.path: source_file.sha256 for source_file in lock.source_files
    }
    missing_sources: list[str] = []
    stale_sources: list[str] = []
    for source_file in lock.source_files:
        path = repo_root / source_file.path
        if not path.exists():
            missing_sources.append(source_file.path)
        elif sha256_file(path) != source_file.sha256:
            stale_sources.append(source_file.path)

    generated_paths: set[str] = set()
    matcher = IgnoreMatcher(repo_root)
    missing_generated: list[str] = []
    generated_mismatches: list[str] = []
    for generated_file in lock.generated_files:
        generated_paths.add(generated_file.path)
        if matcher.is_ignored(generated_file.path):
            continue
        path = repo_root / generated_file.path
        if not path.exists():
            missing_generated.append(generated_file.path)
        elif sha256_file(path) != generated_file.sha256:
            generated_mismatches.append(generated_file.path)

    section_errors: list[str] = []
    if strict:
        section_errors = _verify_strict_structure(
            repo_root, lock, source_hashes_by_path, generated_paths
        )

    public_docs_impacts = _detect_public_docs_impacts(repo_root, lock, source_hashes_by_path)

    result: VerificationResult = "PASS"
    next_command: str | None = None
    if missing_sources:
        result = "FAIL_MISSING_SOURCE"
        next_command = "aictx run --project . --mode setup-context --scope changed --write patch"
    elif stale_sources:
        result = "FAIL_STALE_AI_CONTEXT"
        next_command = "aictx run --project . --mode setup-context --scope changed --write patch"
    elif missing_generated or generated_mismatches or section_errors:
        result = "FAIL_LOCK_MISMATCH"
        next_command = "aictx run --project . --mode setup-context --scope full --write patch"
    elif public_docs_impacts:
        result = "FAIL_PUBLIC_DOCS_IMPACT"
        next_command = "aictx public-docs update --project . --scope changed --write patch"

    return VerificationReport(
        result=result,
        strict=strict,
        missing_sources=missing_sources,
        stale_sources=stale_sources,
        missing_generated=missing_generated,
        generated_mismatches=generated_mismatches,
        section_errors=section_errors,
        public_docs_impacts=public_docs_impacts,
        next_command=next_command,
    )


def _verify_strict_structure(
    repo_root: Path,
    lock: ContextLock,
    source_hashes_by_path: dict[str, str],
    generated_paths: set[str],
) -> list[str]:
    """Verify deterministic lock structure beyond raw file hashes."""
    errors: list[str] = []
    if lock.generated_files:
        missing_generated = REQUIRED_GENERATED_CONTEXT_FILES - generated_paths
        errors.extend(
            f"missing generated file in lock: {path}" for path in sorted(missing_generated)
        )

    section_ids: set[str] = set()
    for section in lock.sections:
        if section.section_id in section_ids:
            errors.append(f"duplicate section id: {section.section_id}")
        section_ids.add(section.section_id)

        if section.generated_file not in generated_paths:
            errors.append(f"section target not generated: {section.section_id}")
        if len(section.source_paths) != len(section.source_hashes):
            errors.append(f"section source/hash length mismatch: {section.section_id}")
            continue
        for source_path, source_hash in zip(
            section.source_paths, section.source_hashes, strict=True
        ):
            if source_hashes_by_path.get(source_path) != source_hash:
                errors.append(f"section source hash mismatch: {section.section_id}:{source_path}")

    if "AGENTS.md" in generated_paths:
        agents_path = repo_root / "AGENTS.md"
        try:
            agents_text = agents_path.read_text(encoding="utf-8")
        except OSError:
            errors.append("generated AGENTS.md unreadable")
        else:
            if "docs/AIprojectcontext/ai-index.md" not in agents_text:
                errors.append("generated AGENTS.md missing ai-index link")

    return errors


def _detect_public_docs_impacts(
    repo_root: Path,
    lock: ContextLock,
    source_hashes_by_path: dict[str, str],
) -> dict[str, list[str]]:
    impacts: dict[str, list[str]] = {}
    for entry in lock.public_docs_map:
        impacted_sources: list[str] = []
        for source_path, recorded_hash in zip(
            entry.source_paths, entry.last_verified_source_hashes, strict=False
        ):
            current_hash = source_hashes_by_path.get(source_path)
            path = repo_root / source_path
            if path.exists():
                current_hash = sha256_file(path)
            if current_hash != recorded_hash:
                impacted_sources.append(source_path)
        if impacted_sources:
            impacts[entry.path] = impacted_sources
    return impacts


# Runtime/build artifact prefixes and exact names excluded from changed-source detection.
# Must stay in sync with agentheim_code.vendor.aictx.llm.transfer.RUNTIME_BLOCKED_PREFIXES
# and agentheim_code.vendor.aictx.scan.ignore.BUILTIN_HARD_EXCLUDES.
_RUNTIME_BLOCKED_PREFIXES = (
    ".git/",
    ".aictx/",
    ".ai-team/",
    ".pytest_cache/",
    "build/",
    "dist/",
    "node_modules/",
)
_RUNTIME_BLOCKED_NAMES = frozenset({".coverage", "agentheim.egg-info"})


def _is_runtime_artifact(path: str) -> bool:
    if path in _RUNTIME_BLOCKED_NAMES:
        return True
    return any(path.startswith(prefix) or path.startswith(prefix.rstrip("/")) for prefix in _RUNTIME_BLOCKED_PREFIXES)


def determine_changed_source_paths(
    inventory: RepositoryInventory, lock: ContextLock | None
) -> list[str]:
    """Return source paths that differ from lockfile source state."""
    current = {
        file.path: file.sha256
        for file in inventory.files
        if not file.is_ignored
        and not file.is_binary
        and not file.is_generated
        and file.sha256 != "skipped"
        and file.path != "docs/AIprojectcontext/context.lock.json"
        and not _is_runtime_artifact(file.path)
    }
    if lock is None:
        return sorted(current)

    locked = {entry.path: entry.sha256 for entry in lock.source_files}
    changed = [
        path
        for path, current_hash in current.items()
        if locked.get(path) is None or locked[path] != current_hash
    ]
    changed.extend(path for path in locked if path not in current)
    return sorted(set(changed))
