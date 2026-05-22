"""`context.lock.json` I/O helpers."""

from __future__ import annotations

import json
from pathlib import Path

from agentheim_code.vendor.aictx import __version__
from agentheim_code.vendor.aictx.models.context_lock import ContextLock, SourceFileEntry
from agentheim_code.vendor.aictx.models.inventory import RepositoryInventory
from agentheim_code.vendor.aictx.verify.hashes import sha256_text

LOCK_FILENAME = "context.lock.json"
SUPPORTED_SCHEMA_VERSIONS = {"1.0"}


def build_lockfile_from_inventory(inventory: RepositoryInventory) -> ContextLock:
    """Build a deterministic baseline lockfile from a repository inventory.

    This is a file-state baseline only. It does not represent generated AI context yet.
    """
    source_files = [
        SourceFileEntry(
            path=file.path,
            sha256=file.sha256,
            kind=file.kind,
            included_in_generation=False,
        )
        for file in inventory.files
        if not file.is_ignored
        and not file.is_binary
        and not file.is_generated
        and file.sha256 != "skipped"
        and file.path != f"docs/AIprojectcontext/{LOCK_FILENAME}"
    ]
    source_files.sort(key=lambda entry: entry.path)
    scanner_config_hash = sha256_text(
        "\n".join(
            [
                inventory.scanner_version,
                inventory.repo_root,
                str(len(source_files)),
            ]
        )
    )
    return ContextLock(
        tool_version=__version__,
        repo_head_commit=inventory.head_commit,
        model_provider="none",
        model_name="none",
        scanner_config_hash=scanner_config_hash,
        source_files=source_files,
    )


def load_lockfile(context_dir: Path) -> ContextLock | None:
    """Load the lockfile from *context_dir* if it exists."""
    path = context_dir / LOCK_FILENAME
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    return ContextLock(**data)


def write_lockfile(context_dir: Path, lock: ContextLock) -> None:
    """Write *lock* to *context_dir*/context.lock.json."""
    path = context_dir / LOCK_FILENAME
    with path.open("w", encoding="utf-8") as fh:
        json.dump(lock.model_dump(mode="json"), fh, indent=2)
