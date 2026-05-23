from __future__ import annotations

import json
from pathlib import Path

import requests

from agentheim_code import diagnostics
from agentheim_code.provider_health import (
    ProviderHealth,
    load_health,
    save_health,
    update_health_from_bakeoff,
)
from agentheim_code.structured_errors import from_exception, redact_text


def test_redact_text_masks_common_secret_patterns() -> None:
    text = "api_key=secretvalue Bearer tokenvalue sk-abcdefghijklmnopqrstuvwxyz"

    redacted = redact_text(text)

    assert "secretvalue" not in redacted
    assert "tokenvalue" not in redacted
    assert "abcdefghijklmnopqrstuvwxyz" not in redacted
    assert "api_key=***" in redacted
    assert "Bearer ***" in redacted
    assert "sk-***" in redacted


def test_structured_error_from_exception_includes_recovery() -> None:
    error = from_exception(RuntimeError("provider failed"), event_id="event-1")

    assert error.error_code == "E2099"
    assert error.message == "provider failed"
    assert error.technical_detail == "RuntimeError"
    assert error.related_event_id == "event-1"
    assert "try again" in error.recovery_action.lower()


def test_structured_error_maps_network_failures() -> None:
    error = from_exception(requests.exceptions.ConnectionError("network failed"))

    assert error.error_code == "E2009"
    assert "network" in error.message.lower()


def test_structured_error_maps_filesystem_failures() -> None:
    error = from_exception(OSError("disk full"))

    assert error.error_code == "E2010"
    assert "filesystem" in error.message.lower()


def test_provider_health_round_trips_to_redacted_json_file(tmp_path: Path, monkeypatch) -> None:
    health_file = tmp_path / "provider-health.json"
    monkeypatch.setattr("agentheim_code.provider_health._health_file", lambda: health_file)

    save_health(
        {
            "local/ollama": ProviderHealth(
                provider_id="ollama",
                profile="local",
                last_tested="2026-05-23T00:00:00+00:00",
                latency_ms=12.345,
                available=True,
                usage_extracted=False,
                known_limitations=["usage unavailable"],
                bakeoff_passed=True,
            )
        }
    )

    loaded = load_health()

    assert loaded["local/ollama"].provider_id == "ollama"
    assert loaded["local/ollama"].latency_ms == 12.35
    assert loaded["local/ollama"].known_limitations == ["usage unavailable"]


def test_update_health_from_bakeoff_persists_entry(tmp_path: Path, monkeypatch) -> None:
    health_file = tmp_path / "provider-health.json"
    monkeypatch.setattr("agentheim_code.provider_health._health_file", lambda: health_file)

    entries = update_health_from_bakeoff(
        entries=None,
        profile="local",
        provider_id="ollama",
        latency_ms=44.0,
        available=True,
        usage_extracted=True,
        passed=False,
        degraded=True,
        limitations=["slow verification"],
    )

    assert entries["local/ollama"].bakeoff_degraded is True
    payload = json.loads(health_file.read_text(encoding="utf-8"))
    assert payload["local/ollama"]["known_limitations"] == ["slow verification"]


def test_diagnostics_bundle_redacts_config_and_lists_logs(tmp_path: Path, monkeypatch) -> None:
    config = {
        "providers": {
            "openai": {
                "api_key": "sk-abcdefghijklmnopqrstuvwxyz",
                "endpoint": "https://example.test",
            }
        }
    }
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "agentheim.log").write_text("hello", encoding="utf-8")

    monkeypatch.setattr("agentheim_code.config.load_config", lambda: config)
    monkeypatch.setattr("agentheim_code.diagnostics.load_health", lambda: {})
    monkeypatch.setattr("platformdirs.user_log_dir", lambda *_args, **_kwargs: str(log_dir))

    bundle = diagnostics.generate_diagnostics_bundle()

    provider = bundle["config"]["providers"]["openai"]
    assert provider["api_key"] == "sk-***"
    assert provider["endpoint"] == "https://example.test"
    assert "agentheim.log" in bundle["log_paths"]


def test_write_diagnostics_bundle_creates_json(tmp_path: Path, monkeypatch) -> None:
    out = tmp_path / "diagnostics.json"
    monkeypatch.setattr(
        "agentheim_code.diagnostics.generate_diagnostics_bundle",
        lambda: {"system": {"app_version": "1.0.0"}},
    )

    diagnostics.write_diagnostics_bundle(out)

    assert json.loads(out.read_text(encoding="utf-8"))["system"]["app_version"] == "1.0.0"
