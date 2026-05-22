"""Fact extraction from selected repository files."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from agentheim_code.vendor.aictx.llm.base import ChatRequest, ModelProvider


class FactPack:
    """Collection of structured facts for a context pass."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.facts: list[dict[str, object]] = []

    def add_fact(
        self,
        claim: str,
        confidence: float,
        source_paths: list[str],
        source_spans: list[str] | None = None,
        derived_from: list[str] | None = None,
        needs_source: bool = False,
    ) -> None:
        fact_id_seed = "|".join([self.name, claim, *sorted(source_paths)])
        self.facts.append(
            {
                "id": f"{self.name}-{hashlib.sha1(fact_id_seed.encode('utf-8')).hexdigest()[:12]}",
                "claim": claim,
                "confidence": confidence,
                "source_paths": source_paths,
                "source_spans": source_spans or [],
                "derived_from": derived_from or [],
                "needs_source": needs_source,
            }
        )


def _relative_source_path(repo_root: Path, path: Path) -> str:
    try:
        return path.relative_to(repo_root).as_posix()
    except ValueError:
        return path.as_posix()


def _extract_fact_packs(repo_root: Path, file_paths: list[Path]) -> list[FactPack]:
    """Extract structured facts from *file_paths*."""
    packs: dict[str, FactPack] = {
        "project_identity": FactPack("project_identity"),
        "architecture": FactPack("architecture"),
        "feature": FactPack("feature"),
        "workflow": FactPack("workflow"),
        "docs": FactPack("docs"),
        "risk": FactPack("risk"),
    }
    for path in sorted(file_paths):
        rel = _relative_source_path(repo_root, path)
        suffix = path.suffix.lower()
        source_span = [f"{rel}:1"]
        if path.name == "README.md":
            packs["project_identity"].add_fact(
                claim=f"Repository includes root README at {rel}",
                confidence=1.0,
                source_paths=[rel],
                source_spans=source_span,
            )
        if suffix in {".py", ".cs", ".rs", ".go", ".ts", ".js"}:
            status = "stubbed" if _looks_stubbed(path) else "implemented"
            packs["architecture"].add_fact(
                claim=f"{status.title()} source file present: {rel}",
                confidence=0.9,
                source_paths=[rel],
                source_spans=source_span,
            )
            packs["feature"].add_fact(
                claim=f"{status.title()} implementation file selected for context: {rel}",
                confidence=0.8,
                source_paths=[rel],
                source_spans=source_span,
                needs_source=status != "implemented",
            )
        if "test" in path.name.lower() or "tests/" in rel:
            packs["workflow"].add_fact(
                claim=f"Test coverage artifact present: {rel}",
                confidence=0.9,
                source_paths=[rel],
                source_spans=source_span,
            )
        if suffix == ".md" and rel != "README.md":
            packs["docs"].add_fact(
                claim=f"Documentation file selected: {rel}",
                confidence=0.9,
                source_paths=[rel],
                source_spans=source_span,
            )
        if suffix in {".yml", ".yaml", ".toml", ".json"}:
            packs["workflow"].add_fact(
                claim=f"Configuration or workflow manifest selected: {rel}",
                confidence=0.85,
                source_paths=[rel],
                source_spans=source_span,
            )

    return [pack for pack in packs.values() if pack.facts]


def _looks_stubbed(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    lowered = text.casefold()
    return "notimplementederror" in lowered or "stubbed" in lowered or "todo" in lowered


def extract_facts(
    repo_root: Path,
    plan: dict[str, Any],
    provider: ModelProvider,
    run_id: str,
) -> list[dict[str, object]]:
    """Extract deterministic structured facts for the selected plan."""
    selected = [repo_root / path for path in plan["selected_files"]]
    packs = _extract_fact_packs(repo_root, selected)
    output: list[dict[str, object]] = []
    for pack in packs:
        response = provider.chat(
            ChatRequest(
                system_prompt="Summarize repository facts deterministically.",
                messages=[{"role": "user", "content": pack.name}],
                run_id=run_id,
                purpose=f"fact-pack:{pack.name}",
            )
        )
        output.append(
            {
                "name": pack.name,
                "facts": pack.facts,
                "summary": response.content,
                "estimated_output_tokens": response.output_tokens,
            }
        )
    return output
