"""Deterministic snapshot creation — manifest, inventory, sanitised repo content.

Same repo state always produces identical snapshot hashes.
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

from agentheim_code.vendor.aictx.errors import SafetyError, SecretScanError
from agentheim_code.vendor.aictx.models.inventory import RepositoryInventory
from agentheim_code.vendor.aictx.scan.scanner import scan_repository
from agentheim_code.vendor.aictx.verify.hashes import sha256_file

SNAPSHOT_FILENAME = "aictx-snapshot.zip"

# Files/paths rejected by default unless explicitly overridden
FORBIDDEN_PATH_SUBSTRINGS = {
    ".env",
    ".pem",
    ".key",
    ".pfx",
    ".p12",
    ".cert",
    ".secret",
    "credentials",
    "secrets.yml",
    "secrets.yaml",
    "sqlite",
    ".db",
    ".db3",
    ".sqlite",
    ".sqlite3",
    "node_modules",
    ".venv",
    "__pycache__",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
    ".git",
    ".ai-team/runs",
    ".ai-team/cache",
    ".ai-team/tmp",
    ".aictx/runs",
    ".aictx/cache",
    ".aictx/tmp",
    "build/",
    "dist/",
    "bin/",
    "obj/",
    ".vs/",
    ".vscode/",
}

# Hard limits enforced BEFORE upload
MAX_FILES = 10_000
MAX_BYTES = 500 * 1024 * 1024  # 500 MiB
MAX_ARCHIVE_DEPTH = 12
MAX_OUTPUT_BYTES = 250 * 1024 * 1024


class SnapshotManifest:
    """Deterministic snapshot metadata."""

    def __init__(self) -> None:
        self.created_at = "2024-01-01T00:00:00+00:00"
        self.files: list[dict[str, object]] = []
        self.sha256_hashes: dict[str, str] = {}
        self.scanner_config_hash: str = ""
        self.generation_metadata: dict[str, object] = {}

    def to_dict(self) -> dict[str, object]:
        return {
            "created_at": self.created_at,
            "file_count": len(self.files),
            "files": self.files,
            "sha256_hashes": self.sha256_hashes,
            "scanner_config_hash": self.scanner_config_hash,
            "generation_metadata": self.generation_metadata,
        }


def create_snapshot(
    repo_root: Path,
    output_dir: Path,
    inventory: RepositoryInventory | None = None,
    skip_secret_scan: bool = False,
    override_forbidden: set[str] | None = None,
) -> Path:
    """Create a deterministic, sanitised snapshot zip at *output_dir*/aictx-snapshot.zip.

    Returns path to the created snapshot.
    """
    if inventory is None:
        inventory = scan_repository(repo_root)

    snapshot_path = output_dir / SNAPSHOT_FILENAME
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)

    manifest = SnapshotManifest()
    included_files: list[tuple[str, Path]] = []
    forbidden = set(FORBIDDEN_PATH_SUBSTRINGS) - (override_forbidden or set())
    manifest.scanner_config_hash = _compute_scanner_config_hash(repo_root)
    manifest.generation_metadata = {
        "repo_root": str(repo_root),
        "inventory_head": inventory.head_commit,
        "inventory_branch": inventory.branch,
    }

    for entry in inventory.files:
        if entry.is_ignored or entry.is_binary or entry.is_generated:
            continue
        if entry.sha256 == "skipped":
            continue
        if _has_forbidden_path(entry.path, forbidden):
            continue
        if entry.path.count("/") > MAX_ARCHIVE_DEPTH:
            raise SafetyError(f"Snapshot path exceeds max depth {MAX_ARCHIVE_DEPTH}: {entry.path}")
        full_path = repo_root / entry.path
        if not full_path.is_file():
            continue
        included_files.append((entry.path, full_path))

    if len(included_files) > MAX_FILES:
        raise SafetyError(
            f"Snapshot would include {len(included_files)} files (max {MAX_FILES}). "
            "Adjust .aictxignore or increase limit."
        )

    total_bytes = sum(p.stat().st_size for _, p in included_files)
    if total_bytes > MAX_BYTES:
        raise SafetyError(
            f"Snapshot would be {total_bytes} bytes (max {MAX_BYTES}). "
            "Adjust .aictxignore or increase limit."
        )
    if total_bytes > MAX_OUTPUT_BYTES:
        raise SafetyError(
            f"Snapshot output size would be {total_bytes} bytes (max {MAX_OUTPUT_BYTES})."
        )

    # Secret scan unless explicitly skipped
    if not skip_secret_scan:
        _scan_snapshot_secrets(repo_root, included_files)

    # Build deterministic archive
    with zipfile.ZipFile(snapshot_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        # Write manifest first for deterministic ordering
        for rel_path, full_path in sorted(included_files, key=lambda x: x[0]):
            arcname = f"repo/{rel_path}"
            try:
                data = full_path.read_bytes()
            except OSError:
                continue
            info = zipfile.ZipInfo.from_file(full_path, arcname)
            info.date_time = (2024, 1, 1, 0, 0, 0)
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, data)
            file_hash = hashlib.sha256(data).hexdigest()
            manifest.files.append(
                {
                    "path": rel_path,
                    "size": len(data),
                    "sha256": file_hash,
                }
            )
            manifest.sha256_hashes[rel_path] = file_hash

        # Inject manifest.json
        manifest_bytes = json.dumps(manifest.to_dict(), indent=2, sort_keys=True).encode("utf-8")
        manifest_info = zipfile.ZipInfo("manifest.json", date_time=(2024, 1, 1, 0, 0, 0))
        manifest_info.compress_type = zipfile.ZIP_DEFLATED
        zf.writestr(manifest_info, manifest_bytes)

        inventory_bytes = inventory.model_dump_json(indent=2).encode("utf-8")
        inventory_info = zipfile.ZipInfo("inventory.json", date_time=(2024, 1, 1, 0, 0, 0))
        inventory_info.compress_type = zipfile.ZIP_DEFLATED
        zf.writestr(inventory_info, inventory_bytes)

    logger = __import__("logging").getLogger("aictx.oci.snapshot")
    logger.info(
        "snapshot created path=%s files=%d bytes=%d sha256=%s",
        snapshot_path,
        len(included_files),
        total_bytes,
        sha256_file(snapshot_path),
    )
    return snapshot_path


def verify_snapshot(snapshot_path: Path) -> dict[str, object]:
    """Verify snapshot integrity — manifest, hashes, forbidden paths.

    Returns a verification result dict.
    """
    if not snapshot_path.is_file():
        return {"valid": False, "error": "snapshot file not found"}

    errors: list[str] = []
    try:
        with zipfile.ZipFile(snapshot_path, "r") as zf:
            names = zf.namelist()

            if "manifest.json" not in names:
                errors.append("missing manifest.json")
            if "inventory.json" not in names:
                errors.append("missing inventory.json")

            manifest_raw = zf.read("manifest.json")
            manifest = json.loads(manifest_raw)
            file_entries: list[dict[str, object]] = manifest.get("files", [])

            for entry in file_entries:
                rel_path = str(entry.get("path", ""))
                expected_hash = str(entry.get("sha256", ""))
                arcname = f"repo/{rel_path}"
                if arcname not in names:
                    errors.append(f"missing file in archive: {rel_path}")
                    continue
                actual_hash = hashlib.sha256(zf.read(arcname)).hexdigest()
                if actual_hash != expected_hash:
                    errors.append(f"hash mismatch: {rel_path}")

                # Check forbidden paths even in archived state
                if _has_forbidden_path(rel_path, FORBIDDEN_PATH_SUBSTRINGS):
                    errors.append(f"forbidden path in snapshot: {rel_path}")
                if rel_path.count("/") > MAX_ARCHIVE_DEPTH:
                    errors.append(f"path depth exceeded: {rel_path}")

    except (zipfile.BadZipFile, json.JSONDecodeError, KeyError) as exc:
        return {"valid": False, "error": f"snapshot corrupted: {exc}"}

    valid = len(errors) == 0
    return {
        "valid": valid,
        "file_count": len(file_entries) if "file_entries" in dir() else 0,
        "errors": errors if not valid else [],
    }


def _has_forbidden_path(rel_path: str, forbidden: set[str]) -> bool:
    path_lower = rel_path.lower()
    return any(substr in path_lower for substr in forbidden)


def _scan_snapshot_secrets(repo_root: Path, included_files: list[tuple[str, Path]]) -> None:
    """Scan *included_files* for high-confidence secrets; abort on finding."""
    from agentheim_code.vendor.aictx.scan.secrets import scan_for_secrets

    offending: list[str] = []
    for rel_path, full_path in included_files:
        try:
            content = full_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        findings = scan_for_secrets(content, full_path)
        if findings:
            offending.append(rel_path)

    if offending:
        raise SecretScanError(
            "Secret scan blocked snapshot creation. Offending files:\n"
            + "\n".join(f"  - {p}" for p in offending)
            + "\nReview and remove secrets, then retry. "
            "Use --skip-secret-scan to override (not recommended)."
        )


def _compute_scanner_config_hash(repo_root: Path) -> str:
    config_path = repo_root / ".aictx" / "config.toml"
    ignore_path = repo_root / ".aictxignore"
    payload = []
    for path in (config_path, ignore_path):
        if path.exists():
            payload.append(path.read_text(encoding="utf-8"))
    return hashlib.sha256("\n---\n".join(payload).encode("utf-8")).hexdigest()
