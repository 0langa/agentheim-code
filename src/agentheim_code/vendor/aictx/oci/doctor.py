"""Local OCI readiness checks."""

from __future__ import annotations

import configparser
import importlib.util
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class OCIReadinessReport(BaseModel):
    """Non-mutating OCI readiness result."""

    profile: str
    config_file: str
    sdk_available: bool
    config_file_exists: bool
    profile_exists: bool
    compartment_id_present: bool
    model_id_present: bool
    auth_ok: bool = False
    bucket_access: bool = False
    region_matches: bool = False
    ready: bool
    missing: list[str] = Field(default_factory=list)


def run_oci_doctor(
    profile: str = "DEFAULT",
    config_file: Path | None = None,
    model_id: str | None = None,
    compartment_id: str | None = None,
    region: str | None = None,
    bucket: str | None = None,
) -> OCIReadinessReport:
    """Check local OCI SDK/config readiness without network calls."""
    resolved_config = config_file or (Path.home() / ".oci" / "config")
    sdk_available = importlib.util.find_spec("oci") is not None
    config_exists = resolved_config.exists()
    profile_exists = False
    compartment_id_present = bool(compartment_id) or bool(os.getenv("OCI_COMPARTMENT_ID"))
    model_id_present = bool(model_id) and model_id != "dry_run"
    auth_ok = False
    bucket_access = False
    region_matches = False

    if config_exists:
        parser = configparser.ConfigParser()
        parser.read(resolved_config, encoding="utf-8")
        profile_exists = parser.has_section(profile)
        if profile == "DEFAULT":
            profile_exists = bool(parser.defaults()) or parser.has_section("DEFAULT")
        if not compartment_id_present:
            compartment_id_present = _config_has_compartment(parser, profile)

    missing: list[str] = []
    if not sdk_available:
        missing.append("oci python package")
    if not config_exists:
        missing.append(str(resolved_config))
    elif not profile_exists:
        missing.append(f"OCI profile {profile}")
    if not compartment_id_present:
        missing.append("OCI_COMPARTMENT_ID or compartment_id")
    if not model_id_present:
        missing.append("model_id")

    if sdk_available and config_exists and profile_exists:
        auth_ok, region_matches, bucket_access = _validate_runtime(
            profile, resolved_config, region, bucket
        )
        if not auth_ok and (region is not None or bucket is not None):
            missing.append("OCI auth")
        if region and not region_matches:
            missing.append("configured region mismatch")
        if bucket and not bucket_access:
            missing.append(f"bucket access: {bucket}")

    return OCIReadinessReport(
        profile=profile,
        config_file=str(resolved_config),
        sdk_available=sdk_available,
        config_file_exists=config_exists,
        profile_exists=profile_exists,
        compartment_id_present=compartment_id_present,
        model_id_present=model_id_present,
        auth_ok=auth_ok,
        bucket_access=bucket_access,
        region_matches=region_matches if region else True,
        ready=not missing,
        missing=missing,
    )


def _config_has_compartment(parser: configparser.ConfigParser, profile: str) -> bool:
    if profile == "DEFAULT":
        return bool(parser.defaults().get("compartment_id"))
    if not parser.has_section(profile):
        return False
    return bool(parser.get(profile, "compartment_id", fallback=""))


def _validate_runtime(
    profile: str,
    config_file: Path,
    region: str | None,
    bucket: str | None,
) -> tuple[bool, bool, bool]:
    try:
        import oci

        sdk_config: dict[str, Any] = oci.config.from_file(str(config_file), profile)
        auth_ok = True
        region_matches = True if not region else sdk_config.get("region") == region
        bucket_access = False
        if bucket:
            object_client = oci.object_storage.ObjectStorageClient(sdk_config)
            namespace = object_client.get_namespace().data
            object_client.head_bucket(namespace, bucket)
            bucket_access = True
        return auth_ok, region_matches, bucket_access
    except Exception:
        return False, not region, False
