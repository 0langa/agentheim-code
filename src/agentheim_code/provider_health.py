"""Provider health state tracking for Agentheim Code.

Stores last test time, latency, model availability, usage extraction support,
and known limitations per provider profile.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from platformdirs import user_data_dir


@dataclass
class ProviderHealth:
    provider_id: str
    profile: str
    last_tested: str = ""
    latency_ms: float = 0.0
    available: bool = False
    usage_extracted: bool = False
    known_limitations: list[str] = field(default_factory=list)
    bakeoff_passed: bool = False
    bakeoff_degraded: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "profile": self.profile,
            "last_tested": self.last_tested,
            "latency_ms": round(self.latency_ms, 2),
            "available": self.available,
            "usage_extracted": self.usage_extracted,
            "known_limitations": self.known_limitations,
            "bakeoff_passed": self.bakeoff_passed,
            "bakeoff_degraded": self.bakeoff_degraded,
        }


def _health_file() -> Path:
    return Path(user_data_dir("agentheim", "Agentheim")) / "provider-health.json"


def load_health() -> dict[str, ProviderHealth]:
    path = _health_file()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return {k: ProviderHealth(**v) for k, v in data.items() if isinstance(v, dict)}


def save_health(entries: dict[str, ProviderHealth]) -> None:
    path = _health_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {k: v.to_dict() for k, v in entries.items()}
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def update_health_from_bakeoff(
    entries: dict[str, ProviderHealth] | None,
    profile: str,
    provider_id: str,
    latency_ms: float,
    available: bool,
    usage_extracted: bool,
    passed: bool,
    degraded: bool,
    limitations: list[str] | None = None,
) -> dict[str, ProviderHealth]:
    if entries is None:
        entries = load_health()
    key = f"{profile}/{provider_id}"
    entries[key] = ProviderHealth(
        provider_id=provider_id,
        profile=profile,
        last_tested=datetime.now(tz=UTC).isoformat(),
        latency_ms=latency_ms,
        available=available,
        usage_extracted=usage_extracted,
        known_limitations=limitations or [],
        bakeoff_passed=passed,
        bakeoff_degraded=degraded,
    )
    save_health(entries)
    return entries
