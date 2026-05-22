"""context.lock.json data model."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field


class GeneratedFileEntry(BaseModel):
    """A generated context file tracked in the lock."""

    path: str
    sha256: str
    generated_from_sections: list[str] = Field(default_factory=list)


class SourceFileEntry(BaseModel):
    """A source file tracked in the lock."""

    path: str
    sha256: str
    kind: str
    included_in_generation: bool = False


class SectionEntry(BaseModel):
    """A context section tracked in the lock."""

    section_id: str
    generated_file: str
    heading: str
    source_paths: list[str] = Field(default_factory=list)
    source_hashes: list[str] = Field(default_factory=list)
    fact_ids: list[str] = Field(default_factory=list)
    status: Literal["current", "stale", "unknown"] = "current"


class PublicDocsMapEntry(BaseModel):
    """A public doc mapped in the lock."""

    path: str
    purpose: str
    audience: str
    described_features: list[str] = Field(default_factory=list)
    source_paths: list[str] = Field(default_factory=list)
    last_verified_source_hashes: list[str] = Field(default_factory=list)
    stale_risk: Literal["low", "medium", "high"] = "low"


class ChangeImpactMapEntry(BaseModel):
    """A change impact mapping entry."""

    source_glob: str
    ai_context_sections: list[str] = Field(default_factory=list)
    public_doc_paths: list[str] = Field(default_factory=list)
    no_impact_reason: str | None = None


class ContextLock(BaseModel):
    """Top-level context lock file model."""

    schema_version: str = "1.0"
    tool_version: str = "0.1.0"
    repo_head_commit: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    model_provider: str = "none"
    model_name: str = "none"
    scanner_config_hash: str = ""
    generated_files: list[GeneratedFileEntry] = Field(default_factory=list)
    source_files: list[SourceFileEntry] = Field(default_factory=list)
    sections: list[SectionEntry] = Field(default_factory=list)
    public_docs_map: list[PublicDocsMapEntry] = Field(default_factory=list)
    change_impact_map: list[ChangeImpactMapEntry] = Field(default_factory=list)
    last_validation: datetime | None = None
