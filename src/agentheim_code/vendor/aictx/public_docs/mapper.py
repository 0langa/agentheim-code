"""Public docs map generation."""

from __future__ import annotations

from pathlib import Path

from agentheim_code.vendor.aictx.models.docs_map import DocsMap, DocsMapEntry
from agentheim_code.vendor.aictx.models.inventory import FileEntry, RepositoryInventory
from agentheim_code.vendor.aictx.scan.scanner import scan_repository


def build_public_docs_map(repo_root: Path) -> DocsMap:
    """Scan *repo_root* and build a compact public docs map."""
    return build_public_docs_map_from_inventory(scan_repository(repo_root))


def build_public_docs_map_from_inventory(inventory: RepositoryInventory) -> DocsMap:
    """Build a conservative source-to-public-doc map from inventory."""
    source_entries = sorted(
        [
            entry
            for entry in inventory.files
            if (entry.is_source or entry.is_manifest)
            and not entry.is_ignored
            and not entry.is_binary
            and not entry.is_generated
            and entry.sha256 != "skipped"
        ],
        key=lambda entry: entry.path,
    )
    entries = [
        _entry_for_doc(doc_entry, source_entries)
        for doc_entry in inventory.docs
        if _is_public_doc(doc_entry)
    ]
    return DocsMap(entries=sorted(entries, key=lambda entry: entry.path))


def _is_public_doc(entry: FileEntry) -> bool:
    if entry.is_generated or entry.is_ignored or entry.is_binary:
        return False
    if entry.path == "AGENTS.md":
        return False
    if entry.path.startswith("docs/AIprojectcontext/"):
        return False
    return entry.path == "README.md" or entry.path.startswith(("docs/", "documentation/"))


def _entry_for_doc(doc_entry: FileEntry, source_entries: list[FileEntry]) -> DocsMapEntry:
    relevant_sources = _sources_for_public_doc(doc_entry.path, source_entries)
    return DocsMapEntry(
        path=doc_entry.path,
        purpose="public project documentation",
        audience="repository users and maintainers",
        described_features=[],
        source_paths=[entry.path for entry in relevant_sources],
        last_verified_source_hashes=[entry.sha256 for entry in relevant_sources],
        stale_risk="medium" if relevant_sources else "low",
    )


def _sources_for_public_doc(doc_path: str, source_entries: list[FileEntry]) -> list[FileEntry]:
    if doc_path == "README.md":
        preferred = [
            entry
            for entry in source_entries
            if entry.path in {"src/aictx/cli.py", "src/main.py", "main.py"}
        ]
        return preferred or source_entries[:1]

    doc_name = Path(doc_path).name.casefold()
    groups: list[tuple[str, tuple[str, ...]]] = [
        ("architecture", ("context/", "scan/", "verify/", "public_docs/", "io/", "git/")),
        ("codemap", ("src/aictx/", "tests/")),
        ("documentation", ("src/aictx/cli.py", "src/aictx/config.py", "pyproject.toml")),
        (
            "changelog",
            (
                "src/aictx/cli.py",
                "src/aictx/context/pipeline.py",
                "src/aictx/verify/verifier.py",
                "src/aictx/public_docs/",
                "src/aictx/oci/doctor.py",
            ),
        ),
    ]
    for key, prefixes in groups:
        if key in doc_name:
            matched = [
                entry for entry in source_entries if _matches_any_prefix(entry.path, prefixes)
            ]
            if matched:
                return matched

    fallback = [
        entry
        for entry in source_entries
        if entry.path in {"src/aictx/cli.py", "src/main.py", "main.py", "pyproject.toml"}
    ]
    return fallback or source_entries[:1]


def _matches_any_prefix(path: str, prefixes: tuple[str, ...]) -> bool:
    return any(path == prefix or path.startswith(prefix) for prefix in prefixes)
