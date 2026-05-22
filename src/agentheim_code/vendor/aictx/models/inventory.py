"""Repository inventory data model."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field


class FileEntry(BaseModel):
    """A single file in the repository inventory."""

    path: str
    kind: Literal["source", "doc", "manifest", "test", "generated", "binary", "ignored", "other"]
    language: str | None = None
    size_bytes: int
    sha256: str
    is_doc: bool = False
    is_source: bool = False
    is_test: bool = False
    is_manifest: bool = False
    is_generated: bool = False
    is_binary: bool = False
    is_ignored: bool = False
    include_reason: str | None = None
    exclude_reason: str | None = None


class SecretFinding(BaseModel):
    """A high-confidence secret detection result."""

    path: str
    detector_name: str
    severity: Literal["high", "medium", "low"]
    line_number: int | None = None


class GitStatusSnapshot(BaseModel):
    """Deterministic snapshot of the current git worktree status."""

    is_dirty: bool
    tracked_files: list[str] = Field(default_factory=list)
    untracked_files: list[str] = Field(default_factory=list)
    modified_files: list[str] = Field(default_factory=list)
    deleted_files: list[str] = Field(default_factory=list)
    renamed_files: list[dict[str, str]] = Field(default_factory=list)


class RepositoryInventory(BaseModel):
    """Complete repository inventory snapshot."""

    repo_root: str
    branch: str
    head_commit: str
    dirty_state: bool
    git_status: GitStatusSnapshot
    files: list[FileEntry] = Field(default_factory=list)
    docs: list[FileEntry] = Field(default_factory=list)
    manifests: list[FileEntry] = Field(default_factory=list)
    build_systems: list[str] = Field(default_factory=list)
    detected_languages: list[str] = Field(default_factory=list)
    project_classification: dict[str, str] = Field(default_factory=dict)
    entrypoints: list[str] = Field(default_factory=list)
    test_projects: list[str] = Field(default_factory=list)
    secrets: list[SecretFinding] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    scanner_version: str = Field(default="0.1.0")
