"""Remote result bundle — packing, unpacking, integrity verification.

A result bundle is a zip file produced by the remote worker containing:
- aictx.patch
- validation-report.md
- run-report.json
- generated/
- logs/
"""

import hashlib
import json
import zipfile
from pathlib import Path

from agentheim_code.vendor.aictx.errors import RemoteJobError

RESULT_BUNDLE_FILENAME = "aictx-result.zip"


def create_result_bundle(
    output_dir: Path,
    patch_path: Path | None = None,
    validation_report: str | None = None,
    run_report: dict[str, object] | None = None,
    generated_dir: Path | None = None,
    logs_dir: Path | None = None,
) -> Path:
    """Package remote execution outputs into a deterministic result bundle zip.

    Returns path to the created bundle.
    """
    bundle_path = output_dir / RESULT_BUNDLE_FILENAME
    bundle_path.parent.mkdir(parents=True, exist_ok=True)

    bundle_manifest: dict[str, object] = {
        "created_at": "2024-01-01T00:00:00+00:00",
        "files": {},
    }
    files_manifest = bundle_manifest["files"]
    assert isinstance(files_manifest, dict)

    with zipfile.ZipFile(bundle_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        if patch_path and patch_path.is_file():
            data = patch_path.read_bytes()
            _writestr_deterministic(zf, "aictx.patch", data)
            files_manifest["aictx.patch"] = hashlib.sha256(data).hexdigest()

        if validation_report:
            report_bytes = validation_report.encode("utf-8")
            _writestr_deterministic(zf, "validation-report.md", report_bytes)
            files_manifest["validation-report.md"] = hashlib.sha256(report_bytes).hexdigest()

        if run_report:
            dump = json.dumps(run_report, indent=2, sort_keys=True)
            dump_bytes = dump.encode("utf-8")
            _writestr_deterministic(zf, "run-report.json", dump_bytes)
            files_manifest["run-report.json"] = hashlib.sha256(dump_bytes).hexdigest()

        if generated_dir and generated_dir.is_dir():
            for path in sorted(generated_dir.rglob("*")):
                if not path.is_file():
                    continue
                rel = f"generated/{path.relative_to(generated_dir).as_posix()}"
                data = path.read_bytes()
                _writestr_deterministic(zf, rel, data)
                files_manifest[rel] = hashlib.sha256(data).hexdigest()

        if logs_dir and logs_dir.is_dir():
            for path in sorted(logs_dir.rglob("*")):
                if not path.is_file():
                    continue
                rel = f"logs/{path.relative_to(logs_dir).as_posix()}"
                data = path.read_bytes()
                _writestr_deterministic(zf, rel, data)
                files_manifest[rel] = hashlib.sha256(data).hexdigest()

        # Write bundle manifest
        _writestr_deterministic(
            zf,
            "bundle-manifest.json",
            json.dumps(bundle_manifest, indent=2, sort_keys=True).encode("utf-8"),
        )

    logger = __import__("logging").getLogger("aictx.oci.bundle")
    logger.info("result bundle created path=%s", bundle_path)
    return bundle_path


def unpack_result_bundle(bundle_path: Path, dest_dir: Path) -> dict[str, Path]:
    """Unpack a result bundle into *dest_dir* and verify integrity.

    Returns a dict mapping logical names to extracted paths:
        {"patch": Path, "validation_report": Path, "run_report": Path, "generated": Path, "logs": Path}
    """
    if not bundle_path.is_file():
        raise RemoteJobError(f"Result bundle not found: {bundle_path}")

    dest_dir.mkdir(parents=True, exist_ok=True)
    extracted: dict[str, Path] = {}

    with zipfile.ZipFile(bundle_path, "r") as zf:
        # Verify bundle-manifest.json first
        if "bundle-manifest.json" not in zf.namelist():
            raise RemoteJobError("Result bundle missing bundle-manifest.json")

        manifest = json.loads(zf.read("bundle-manifest.json"))
        expected_hashes: dict[str, str] = manifest.get("files", {})

        for name in zf.namelist():
            if name == "bundle-manifest.json":
                continue
            data = zf.read(name)
            # Verify hash if recorded in manifest
            if name in expected_hashes:
                actual = hashlib.sha256(data).hexdigest()
                if actual != expected_hashes[name]:
                    raise RemoteJobError(f"Bundle integrity check failed for {name}")

            target = dest_dir / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)

            # Map logical names
            if name == "aictx.patch":
                extracted["patch"] = target
            elif name == "validation-report.md":
                extracted["validation_report"] = target
            elif name == "run-report.json":
                extracted["run_report"] = target
            elif name.startswith("generated/"):
                extracted.setdefault("generated", dest_dir / "generated")
            elif name.startswith("logs/"):
                extracted.setdefault("logs", dest_dir / "logs")

    logger = __import__("logging").getLogger("aictx.oci.bundle")
    logger.info("result bundle unpacked path=%s files=%d", bundle_path, len(extracted))
    return extracted


def verify_bundle(bundle_path: Path) -> dict[str, object]:
    """Verify bundle integrity without extracting.

    Returns verification result dict.
    """
    if not bundle_path.is_file():
        return {"valid": False, "error": "bundle not found"}

    errors: list[str] = []
    try:
        with zipfile.ZipFile(bundle_path, "r") as zf:
            names = zf.namelist()

            if "bundle-manifest.json" not in names:
                errors.append("missing bundle-manifest.json")
                return {"valid": False, "errors": errors}

            manifest = json.loads(zf.read("bundle-manifest.json"))
            expected_hashes: dict[str, str] = manifest.get("files", {})

            for name in names:
                if name == "bundle-manifest.json":
                    continue
                data = zf.read(name)
                if name in expected_hashes:
                    actual = hashlib.sha256(data).hexdigest()
                    if actual != expected_hashes[name]:
                        errors.append(f"hash mismatch: {name}")

            # Check required files
            if "aictx.patch" not in names:
                errors.append("missing aictx.patch")
            if "run-report.json" not in names:
                errors.append("missing run-report.json")

    except (zipfile.BadZipFile, json.JSONDecodeError) as exc:
        return {"valid": False, "error": f"bundle corrupted: {exc}"}

    return {
        "valid": len(errors) == 0,
        "errors": errors if errors else [],
        "file_count": len(names) if "names" in dir() else 0,
    }


def _writestr_deterministic(zf: zipfile.ZipFile, name: str, data: bytes) -> None:
    info = zipfile.ZipInfo(name, date_time=(2024, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    zf.writestr(info, data)
