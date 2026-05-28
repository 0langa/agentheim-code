from __future__ import annotations

import warnings

from core.redaction import redact_text
from core.repo.scanner import RepoScanResult

warnings.warn(
    "build_context_pack is deprecated. Use AICtx via ContextOps instead.",
    DeprecationWarning,
    stacklevel=2,
)


def build_context_pack(scan: RepoScanResult) -> str:
    lines: list[str] = []
    lines.append(f"# Context Pack: {scan.repo_name}")
    lines.append("")
    lines.append("## Repo Summary")
    lines.append(f"- Repo: `{scan.repo_name}`")
    lines.append(f"- Languages: {', '.join(scan.languages) if scan.languages else 'none detected'}")
    lines.append(f"- Git repo: {'yes' if scan.git.is_git_repo else 'no'}")
    if scan.git.branch:
        lines.append(f"- Branch: `{scan.git.branch}`")
    lines.append(f"- Dirty: {'yes' if scan.git.dirty else 'no'}")
    lines.append("")
    lines.append("## Detected Commands")
    if scan.commands:
        for command in scan.commands:
            lines.append(
                f"- `{' '.join(command.command)}` [{command.risk_level}] — {command.reason}"
            )
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## Key Docs")
    if scan.docs:
        for doc in scan.docs:
            lines.append(f"### `{doc.path}`")
            lines.append("")
            lines.append(doc.excerpt)
            lines.append("")
    else:
        lines.append("- none")
    lines.append("## Instruction Files")
    if scan.instruction_files:
        for path in scan.instruction_files:
            lines.append(f"- `{path}`")
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## Manifests")
    for path in scan.manifests or ["none"]:
        lines.append(f"- `{path}`" if path != "none" else "- none")
    lines.append("")
    lines.append("## CI Files")
    for path in scan.ci_files or ["none"]:
        lines.append(f"- `{path}`" if path != "none" else "- none")
    lines.append("")
    lines.append("## Warnings")
    for warning in scan.warnings or ["none"]:
        lines.append(f"- {warning}")
    return redact_text("\n".join(lines).strip() + "\n")
