"""Schema-managed artifact directory for Agentheim Code runs.

Defines the canonical set of per-run artifacts, validates completeness,
and produces generic artifacts that are not workflow-specific.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.redaction import redact_dict


@dataclass(frozen=True)
class ArtifactSpec:
    """Specification for a required run artifact."""

    name: str
    required: bool = True
    validator: Callable[[Path], tuple[bool, str]] | None = None


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _is_valid_json(path: Path) -> tuple[bool, str]:
    try:
        json.loads(path.read_text(encoding="utf-8"))
        return True, ""
    except (json.JSONDecodeError, FileNotFoundError) as exc:
        return False, str(exc)


def _is_valid_jsonl(path: Path) -> tuple[bool, str]:
    if not path.exists():
        return False, "file not found"
    lines = path.read_text(encoding="utf-8").strip().split("\n")
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            json.loads(line)
        except json.JSONDecodeError as exc:
            return False, f"line {i + 1}: {exc}"
    return True, ""


# Canonical artifact set for a complete Agentheim Code run
RUN_ARTIFACTS: list[ArtifactSpec] = [
    ArtifactSpec("run.json", required=True, validator=_is_valid_json),
    ArtifactSpec("config.redacted.json", required=True, validator=_is_valid_json),
    ArtifactSpec("plan.md", required=False),
    ArtifactSpec("context_bundle.md", required=True),
    ArtifactSpec("context_manifest.json", required=True, validator=_is_valid_json),
    ArtifactSpec("ledger.jsonl", required=True, validator=_is_valid_jsonl),
    ArtifactSpec("ledger.index", required=True, validator=_is_valid_json),
    ArtifactSpec("ledger.hash", required=True),
    ArtifactSpec("timeline.jsonl", required=False, validator=_is_valid_jsonl),
    ArtifactSpec("tool_calls.jsonl", required=False, validator=_is_valid_jsonl),
    ArtifactSpec("policy_decisions.jsonl", required=False, validator=_is_valid_jsonl),
    ArtifactSpec("patch.diff", required=False),
    ArtifactSpec("verification.json", required=False, validator=_is_valid_json),
    ArtifactSpec("final_report.md", required=False),
    ArtifactSpec("checkpoints", required=True),  # directory
    ArtifactSpec("oci_snapshot.zip", required=False),
    ArtifactSpec("oci_bundle.zip", required=False),
]


class ArtifactStore:
    """Manage per-run artifact directory with schema validation."""

    def __init__(self, run_dir: Path) -> None:
        self.run_dir = run_dir

    @classmethod
    def create_run(
        cls,
        run_dir: Path,
        *,
        workflow_id: str = "",
        preset_id: str = "",
        config: dict[str, Any] | None = None,
    ) -> ArtifactStore:
        """Initialize a run directory with all generic artifacts.

        Returns:
            ArtifactStore bound to the run directory.
        """
        run_dir.mkdir(parents=True, exist_ok=True)
        store = cls(run_dir)
        store._produce_run_json(workflow_id, preset_id)
        store._produce_config_redacted(config or {})
        return store

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate_completeness(self) -> list[str]:
        """Return a list of missing or invalid required artifacts."""
        missing: list[str] = []
        for spec in RUN_ARTIFACTS:
            if not spec.required:
                continue
            path = self.run_dir / spec.name
            if spec.name == "checkpoints":
                if not path.is_dir():
                    missing.append(f"{spec.name} (missing directory)")
                continue
            if not path.exists():
                missing.append(f"{spec.name} (missing)")
                continue
            if spec.validator is not None:
                valid, reason = spec.validator(path)
                if not valid:
                    missing.append(f"{spec.name} (invalid: {reason})")
        return missing

    def is_complete(self) -> bool:
        """True if all required artifacts exist and are valid."""
        return len(self.validate_completeness()) == 0

    def list_artifacts(self) -> dict[str, bool]:
        """Map artifact name → exists."""
        return {spec.name: (self.run_dir / spec.name).exists() for spec in RUN_ARTIFACTS}

    # ------------------------------------------------------------------
    # Producers
    # ------------------------------------------------------------------

    def _produce_run_json(self, workflow_id: str, preset_id: str) -> Path:
        payload = {
            "run_id": self.run_dir.name,
            "workflow_id": workflow_id,
            "preset_id": preset_id,
            "created_at": datetime.now(UTC).isoformat(),
            "status": "initiated",
            "artifacts_expected": len(RUN_ARTIFACTS),
            "artifacts_required": sum(1 for s in RUN_ARTIFACTS if s.required),
        }
        path = self.run_dir / "run.json"
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return path

    def _produce_config_redacted(self, config: dict[str, Any]) -> Path:
        redacted = redact_dict(config)
        path = self.run_dir / "config.redacted.json"
        path.write_text(json.dumps(redacted, indent=2, sort_keys=True), encoding="utf-8")
        return path

    def produce_context_artifacts(
        self, bundle_md: str, manifest: dict[str, Any]
    ) -> tuple[Path, Path]:
        """Write context_bundle.md and context_manifest.json."""
        bundle_path = self.run_dir / "context_bundle.md"
        bundle_path.write_text(bundle_md, encoding="utf-8")

        manifest_path = self.run_dir / "context_manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return bundle_path, manifest_path

    def produce_plan(self, plan_md: str) -> Path:
        """Write plan.md."""
        path = self.run_dir / "plan.md"
        path.write_text(plan_md, encoding="utf-8")
        return path

    def produce_final_report(self, report_md: str) -> Path:
        """Write final_report.md."""
        path = self.run_dir / "final_report.md"
        path.write_text(report_md, encoding="utf-8")
        return path

    def produce_verification(self, results: dict[str, Any]) -> Path:
        """Write verification.json."""
        path = self.run_dir / "verification.json"
        path.write_text(json.dumps(results, indent=2, sort_keys=True), encoding="utf-8")
        return path

    def produce_patch(self, diff: str) -> Path:
        """Write patch.diff."""
        path = self.run_dir / "patch.diff"
        path.write_text(diff, encoding="utf-8")
        return path

    def produce_context_run_report(self, report: dict[str, Any] | Any) -> Path:
        """Write context_run_report.md.

        Args:
            report: Dict or dataclass with fields:
                run_id, scope, write_mode, files_scanned, files_selected,
                generated_files, timing, entropy.
        """
        path = self.run_dir / "context_run_report.md"

        # Normalize dataclass → dict
        if hasattr(report, "__dataclass_fields__"):
            from dataclasses import asdict

            data = asdict(report)  # type: ignore[arg-type]
        else:
            data = dict(report)  # type: ignore[arg-type]

        lines: list[str] = [
            "# Context Run Report",
            "",
            f"- **Run ID**: {data.get('run_id', 'N/A')}",
            f"- **Scope**: {data.get('scope', 'N/A')}",
            f"- **Write Mode**: {data.get('write_mode', 'N/A')}",
            "",
            "## Files",
            "",
            f"- **Scanned**: {data.get('files_scanned', 'N/A')}",
            f"- **Selected**: {data.get('files_selected', 'N/A')}",
            f"- **Generated**: {data.get('generated_files', 'N/A')}",
            "",
            "## Telemetry",
            "",
            f"- **Timing**: {data.get('timing', 'N/A')}",
            f"- **Entropy**: {data.get('entropy', 'N/A')}",
            "",
        ]
        path.write_text("\n".join(lines), encoding="utf-8")
        return path

    def produce_snapshot_zip(self, snapshot_path: Path) -> Path:
        """Copy snapshot zip into artifacts."""
        dst = self.run_dir / "oci_snapshot.zip"
        dst.write_bytes(snapshot_path.read_bytes())
        return dst

    def produce_bundle_zip(self, bundle_path: Path) -> Path:
        """Copy result bundle zip into artifacts."""
        dst = self.run_dir / "oci_bundle.zip"
        dst.write_bytes(bundle_path.read_bytes())
        return dst

    def produce_context_lock(self, lock_path: Path | str | None = None) -> Path:
        """Copy the context lockfile into artifacts as context.lock.json.

        Defaults to ``docs/AIprojectcontext/context.lock.json`` relative
        to the project root (resolved from *cwd*).
        """
        if lock_path is None:
            lock_path = Path("docs/AIprojectcontext/context.lock.json")
        src = Path(lock_path)
        dst = self.run_dir / "context.lock.json"
        if src.exists():
            dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        else:
            dst.write_text("{}", encoding="utf-8")
        return dst

    def produce_snapshot(self, snapshot_path: Path) -> Path:
        """Copy an AICtx snapshot zip into the artifact store.

        Returns the artifact-relative path.
        """
        dst = self.run_dir / "snapshot.zip"
        dst.write_bytes(snapshot_path.read_bytes())
        meta = {
            "original_path": str(snapshot_path),
            "size_bytes": dst.stat().st_size,
            "sha256": _sha256_file(dst),
        }
        (self.run_dir / "snapshot.json").write_text(
            json.dumps(meta, indent=2, sort_keys=True), encoding="utf-8"
        )
        return dst

    def produce_public_docs_impact(self, report: dict[str, Any] | Any) -> Path:
        """Write public_docs_impact.md."""
        path = self.run_dir / "public_docs_impact.md"

        if hasattr(report, "__dataclass_fields__"):
            from dataclasses import asdict

            data = asdict(report)  # type: ignore[arg-type]
        else:
            data = dict(report)  # type: ignore[arg-type]

        lines: list[str] = [
            "# Public Docs Impact Report",
            "",
        ]
        entries = data.get("entries", [])
        if entries:
            lines.append("## Entries")
            lines.append("")
            for entry in entries:
                lines.append(f"- {entry}")
            lines.append("")
        else:
            lines.append("No public documentation impacts detected.")
            lines.append("")

        path.write_text("\n".join(lines), encoding="utf-8")
        return path
