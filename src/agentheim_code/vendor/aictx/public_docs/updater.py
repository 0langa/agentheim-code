"""Public docs update mode implementation."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from agentheim_code.vendor.aictx.context.lockfile import load_lockfile
from agentheim_code.vendor.aictx.errors import VerificationError
from agentheim_code.vendor.aictx.io.files import safe_write
from agentheim_code.vendor.aictx.public_docs.mapper import build_public_docs_map_from_inventory
from agentheim_code.vendor.aictx.public_docs.patcher import generate_doc_patch
from agentheim_code.vendor.aictx.scan.scanner import scan_repository
from agentheim_code.vendor.aictx.verify.verifier import determine_changed_source_paths

PUBLIC_DOCS_REVIEW_PATH = "docs/AIprojectcontext/public-docs-review.md"


def update_public_docs(
    repo_root: Path,
    scope: Literal["changed", "full"] = "changed",
    write_mode: Literal["patch", "apply"] = "patch",
) -> Path | None:
    """Generate patches for impacted public docs."""
    context_dir = repo_root / "docs" / "AIprojectcontext"
    lock = load_lockfile(context_dir)
    if lock is None:
        raise VerificationError("Cannot update public docs without context.lock.json.")

    inventory = scan_repository(repo_root)
    changed_paths = determine_changed_source_paths(inventory, lock)
    docs_map = build_public_docs_map_from_inventory(inventory)
    changed_set = set(changed_paths)
    impacted_entries = [
        entry
        for entry in docs_map.entries
        if scope == "full" or changed_set.intersection(entry.source_paths)
    ]

    if not impacted_entries:
        return None

    run_id = datetime.now(UTC).strftime("%Y-%m-%dT%H%M%SZ-public-docs")
    runs_dir = repo_root / ".ai-team" / "runs" / run_id
    out_path = runs_dir / "out" / PUBLIC_DOCS_REVIEW_PATH
    review = _render_review(
        scope=scope,
        changed_paths=changed_paths,
        impacted_docs={entry.path: entry.source_paths for entry in impacted_entries},
    )
    safe_write(out_path, review)
    safe_write(
        runs_dir / "public-docs-impact.json",
        json.dumps(
            {
                "scope": scope,
                "changed_paths": changed_paths,
                "impacted_docs": {entry.path: entry.source_paths for entry in impacted_entries},
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )

    target = repo_root / PUBLIC_DOCS_REVIEW_PATH
    patch_text = generate_doc_patch(target, review, PUBLIC_DOCS_REVIEW_PATH)
    patch_path = runs_dir / "public-docs.patch"
    safe_write(patch_path, patch_text)

    if write_mode == "apply":
        safe_write(target, review)

    return patch_path


def _render_review(
    scope: str,
    changed_paths: list[str],
    impacted_docs: dict[str, list[str]],
) -> str:
    lines = [
        "# Public Docs Update Review",
        "",
        f"- scope: `{scope}`",
        f"- changed files: `{len(changed_paths)}`",
        f"- impacted public docs: `{len(impacted_docs)}`",
        "",
        "## Changed Sources",
        "",
    ]
    if changed_paths:
        lines.extend(f"- `{path}`" for path in changed_paths)
    else:
        lines.append("- none")
    lines.extend(["", "## Impacted Docs", ""])
    for doc_path, source_paths in sorted(impacted_docs.items()):
        lines.append(f"### `{doc_path}`")
        lines.append("")
        for source_path in sorted(source_paths):
            marker = "changed" if source_path in changed_paths else "mapped"
            lines.append(f"- `{source_path}` ({marker})")
        lines.append("")
    lines.extend(
        [
            "## Required Action",
            "",
            "- Review impacted public docs manually.",
            "- Update public docs only from source facts.",
            "- Run `aictx verify --strict` after edits.",
            "",
        ]
    )
    return "\n".join(lines)
