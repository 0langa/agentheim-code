from __future__ import annotations

from unittest.mock import patch

from config.config import ConfigError
from interfaces.readiness import (
    ReadinessStatus,
    _compute_overall_status,
    build_readiness_state,
)


def test_readiness_without_profiles_uses_real_agentheim_code_guidance() -> None:
    with patch("interfaces.readiness.load_team_config", side_effect=ConfigError("missing profile")):
        state = build_readiness_state()

    assert state.status == ReadinessStatus.needs_provider
    assert state.next_actions == [
        "Launch the app and add a provider from Settings.",
        "Or create a valid providers.json profile document in the shared config directory.",
    ]


def test_auth_failure_guidance_uses_real_product_actions() -> None:
    state = _compute_overall_status(
        has_providers=True,
        has_models=True,
        missing_roles=[],
        provider_with_placeholder=None,
        provider_with_missing_secret=None,
        local_ok=True,
        lane_status="PASS",
        lane_detail="",
        model_conn_ok=False,
        model_conn_detail="401 unauthorized",
        optional_unavailable=False,
    )

    assert state.status == ReadinessStatus.auth_failed
    assert state.next_actions == [
        "Open Settings and re-save the provider credentials, then test the provider again.",
        "Use `agentheim-code provider-test` when you want to validate credentials from the terminal.",
    ]
