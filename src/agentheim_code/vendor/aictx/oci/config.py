"""OCI configuration loading from config.toml [oci] section and environment."""

from __future__ import annotations

import configparser
import importlib.util
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel


class OCIConfig(BaseModel):
    """OCI connection and runtime settings."""

    enabled: bool = False
    region: str = ""
    compartment_id: str = ""
    bucket: str = "aictx-run-artifacts"
    profile: str = "DEFAULT"
    config_file: str = str(Path.home() / ".oci" / "config")
    project_id: str = ""
    subnet_id: str = ""
    log_group_id: str = ""
    max_snapshot_size_mb: int = 250
    max_remote_runtime_minutes: int = 45
    max_upload_retries: int = 3
    max_download_retries: int = 3

    SUPPORTED_REGIONS: tuple[str, ...] = (
        "af-johannesburg-1",
        "ap-chuncheon-1",
        "ap-hyderabad-1",
        "ap-melbourne-1",
        "ap-mumbai-1",
        "ap-osaka-1",
        "ap-seoul-1",
        "ap-singapore-1",
        "ap-sydney-1",
        "ap-tokyo-1",
        "ca-montreal-1",
        "ca-toronto-1",
        "eu-amsterdam-1",
        "eu-frankfurt-1",
        "eu-madrid-1",
        "eu-marseille-1",
        "eu-milan-1",
        "eu-paris-1",
        "eu-stockholm-1",
        "eu-zurich-1",
        "il-jerusalem-1",
        "me-abudhabi-1",
        "me-dubai-1",
        "me-jeddah-1",
        "mx-queretaro-1",
        "sa-bogota-1",
        "sa-santiago-1",
        "sa-saopaulo-1",
        "sa-vinhedo-1",
        "uk-cardiff-1",
        "uk-london-1",
        "us-ashburn-1",
        "us-chicago-1",
        "us-phoenix-1",
        "us-sanjose-1",
    )

    def validate_settings(self) -> list[str]:
        """Return list of validation errors.  Empty means valid."""
        errors: list[str] = []
        if self.enabled:
            if not self.region:
                errors.append("oci.region is required when OCI is enabled")
            elif self.region not in self.SUPPORTED_REGIONS:
                errors.append(f"oci.region is not supported: {self.region}")
            if not self.compartment_id:
                errors.append("oci.compartment_id is required when OCI is enabled")
            if not self.bucket:
                errors.append("oci.bucket is required when OCI is enabled")
            if not self.profile:
                errors.append("oci.profile is required when OCI is enabled")
            if not Path(self.config_file).expanduser().exists():
                errors.append(f"oci.config_file does not exist: {self.config_file}")
            if self.max_snapshot_size_mb < 1 or self.max_snapshot_size_mb > 1024:
                errors.append("oci.max_snapshot_size_mb must be 1-1024")
            if self.max_remote_runtime_minutes < 1 or self.max_remote_runtime_minutes > 120:
                errors.append("oci.max_remote_runtime_minutes must be 1-120")
            if self.max_upload_retries < 0 or self.max_upload_retries > 10:
                errors.append("oci.max_upload_retries must be 0-10")
            if self.max_download_retries < 0 or self.max_download_retries > 10:
                errors.append("oci.max_download_retries must be 0-10")
            if not self._sdk_available():
                errors.append("oci python package is not installed")
            elif self.profile and Path(self.config_file).expanduser().exists():
                profile_errors = self._validate_profile()
                errors.extend(profile_errors)
        return errors

    def to_sdk_config(self) -> dict[str, Any]:
        """Load and return the OCI SDK config dict from file/profile."""
        import oci

        config_path = self.config_file if self.config_file else str(Path.home() / ".oci" / "config")
        try:
            return dict(
                oci.config.from_file(
                    file_location=config_path,
                    profile_name=self.profile,
                )
            )
        except Exception as exc:
            raise RuntimeError(f"Failed to load OCI config from {config_path}: {exc}") from exc

    def validate_runtime_access(self) -> list[str]:
        """Validate SDK auth, bucket, and region access when OCI is enabled."""
        errors: list[str] = []
        if not self.enabled:
            return errors
        try:
            sdk_config = self.to_sdk_config()
        except Exception as exc:
            return [str(exc)]

        try:
            import oci

            object_client = oci.object_storage.ObjectStorageClient(sdk_config)
            namespace = object_client.get_namespace().data
            object_client.head_bucket(namespace, self.bucket)
        except Exception as exc:
            errors.append(f"bucket access failed: {exc}")
        return errors

    def resolve_compartment_id(self) -> str:
        """Return compartment_id from config, env var, or empty."""
        if self.compartment_id:
            return self.compartment_id
        env_id = os.getenv("OCI_COMPARTMENT_ID", "")
        if env_id:
            return env_id
        return self.compartment_id

    def _sdk_available(self) -> bool:
        return importlib.util.find_spec("oci") is not None

    def _validate_profile(self) -> list[str]:
        parser = configparser.ConfigParser()
        parser.read(Path(self.config_file).expanduser(), encoding="utf-8")
        if self.profile == "DEFAULT":
            if not (bool(parser.defaults()) or parser.has_section("DEFAULT")):
                return [f"oci.profile not found in config: {self.profile}"]
            return []
        if not parser.has_section(self.profile):
            return [f"oci.profile not found in config: {self.profile}"]
        return []
