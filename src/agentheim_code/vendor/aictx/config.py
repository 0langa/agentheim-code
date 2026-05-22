"""Configuration loading and validation."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from agentheim_code.vendor.aictx.errors import ConfigError
from agentheim_code.vendor.aictx.oci.config import OCIConfig


class ProjectConfig(BaseModel):
    """Project-level settings."""

    context_dir: str = Field(default="docs/AIprojectcontext")
    agents_file: str = Field(default="AGENTS.md")
    public_docs_dirs: list[str] = Field(default_factory=lambda: ["docs", "."])


class ExecutionConfig(BaseModel):
    """Execution behavior settings."""

    default_execution: Literal["local", "oci-job"] = Field(default="local")
    write_mode: Literal["patch", "apply"] = Field(default="patch")
    allow_dirty: bool = Field(default=False)


class LimitsConfig(BaseModel):
    """Safety limits."""

    max_input_tokens_per_run: int = Field(default=500_000)
    max_output_tokens_per_run: int = Field(default=100_000)
    max_files_per_run: int = Field(default=5_000)
    max_file_bytes: int = Field(default=250_000)
    max_remote_runtime_minutes: int = Field(default=45)


class LLMConfig(BaseModel):
    """LLM provider settings."""

    provider: str = Field(default="dry_run")
    model: str = Field(default="dry_run")
    temperature: float = Field(default=0.0)
    compartment_id: str | None = Field(default=None)
    profile: str | None = Field(default=None)
    config_file: str | None = Field(default=None)


class AictxConfig(BaseModel):
    """Top-level configuration model."""

    project: ProjectConfig = Field(default_factory=ProjectConfig)
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)
    limits: LimitsConfig = Field(default_factory=LimitsConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    oci: OCIConfig = Field(default_factory=OCIConfig)


CONFIG_FILENAME = ".aictx/config.toml"


def load_config(repo_root: Path) -> AictxConfig:
    """Load configuration from repository or defaults."""
    config_path = repo_root / CONFIG_FILENAME
    if not config_path.exists():
        return AictxConfig()

    try:
        data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Invalid TOML in {config_path}: {exc}") from exc
    except OSError as exc:
        raise ConfigError(f"Could not read config file {config_path}: {exc}") from exc

    try:
        return AictxConfig(**data)
    except Exception as exc:
        raise ConfigError(f"Invalid configuration in {config_path}: {exc}") from exc
