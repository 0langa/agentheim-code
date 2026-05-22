"""Public docs map data model."""

from __future__ import annotations

from pydantic import BaseModel, Field


class DocsMapEntry(BaseModel):
    """Mapping of a public doc to code areas."""

    path: str
    purpose: str
    audience: str
    described_features: list[str] = Field(default_factory=list)
    source_paths: list[str] = Field(default_factory=list)
    last_verified_source_hashes: list[str] = Field(default_factory=list)
    stale_risk: str = "low"


class DocsMap(BaseModel):
    """Complete public docs map."""

    entries: list[DocsMapEntry] = Field(default_factory=list)
