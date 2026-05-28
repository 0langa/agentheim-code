from __future__ import annotations

import socket
from enum import StrEnum
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from config.config import (
    ConfigError,
    ModelRole,
    TeamConfig,
    load_team_config,
)
from core.public_api import build_model_registry
from providers.base import ModelRequest


class ReadinessStatus(StrEnum):
    ready = "ready"
    needs_provider = "needs_provider"
    needs_secret = "needs_secret"
    needs_model = "needs_model"
    needs_roles = "needs_roles"
    endpoint_unreachable = "endpoint_unreachable"
    auth_failed = "auth_failed"
    model_failed = "model_failed"
    optional_integration_unavailable = "optional_integration_unavailable"


class ProviderReadiness(BaseModel):
    provider_id: str
    provider_type: str
    endpoint: str
    status: ReadinessStatus
    detail: str = ""


class OptionalIntegrationState(BaseModel):
    integration_id: str
    available: bool
    detail: str = ""
    next_action: str = ""


class ReadinessState(BaseModel):
    status: ReadinessStatus
    profile_name: str = ""
    model_count: int = 0
    missing_roles: list[str] = Field(default_factory=list)
    configured_providers: list[ProviderReadiness] = Field(default_factory=list)
    optional_integrations: list[OptionalIntegrationState] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    detail: str = ""
    lane: str = ""
    lane_detail: str = ""
    local_reachability_ok: bool = True
    local_reachability_detail: str = ""
    model_connectivity_ok: bool | None = None
    model_connectivity_detail: str = ""
    privacy_mode: str = "standard"


_REQUIRED_ROLES = (ModelRole.PLANNER,)
_SECRET_AUTH_MODES = {"api_key", "bearer", "x_api_key", "bedrock_api_key"}
_OPENAI_TYPES = {"openai_v1", "openai_compatible", "azure_foundry"}
_GOOGLE_TYPES = {"gemini", "vertex_ai"}
_PLACEHOLDER_ENDPOINTS = {"-", "https://example.com/v1", "https://YOUR-RESOURCE.openai.azure.com"}


def _is_local_host(host: str | None) -> bool:
    return host in {"localhost", "127.0.0.1", "::1"}


def _endpoint_target(endpoint: str) -> tuple[str | None, int | None]:
    parsed = urlparse(endpoint)
    if parsed.scheme not in {"http", "https"}:
        return None, None
    port = parsed.port
    if port is None:
        port = 443 if parsed.scheme == "https" else 80
    return parsed.hostname, port


def _check_role_coverage(config: TeamConfig) -> tuple[list[str], str]:
    bound_roles = {model.role for model in config.models.values()}
    missing = [role.value for role in _REQUIRED_ROLES if role not in bound_roles]
    if missing:
        return missing, f"missing roles: {', '.join(missing)}"
    return [], "planner bound"


def _check_first_class_lane(config: TeamConfig) -> tuple[str, str]:
    providers = list(config.providers.values())
    provider_types = {provider.provider_type for provider in providers}
    lane = "advanced/experimental"
    detail = ""

    if provider_types & _OPENAI_TYPES:
        lane = "openai-compatible"
        detail = ", ".join(
            sorted(provider.id for provider in providers if provider.provider_type in _OPENAI_TYPES)
        )
    elif provider_types & _GOOGLE_TYPES:
        lane = "google"
        detail = ", ".join(
            sorted(provider.id for provider in providers if provider.provider_type in _GOOGLE_TYPES)
        )
    else:
        local_compatible = []
        for provider in providers:
            host, _port = _endpoint_target(provider.endpoint)
            if provider.provider_type == "openai_compatible" and _is_local_host(host):
                local_compatible.append(provider.id)
        if local_compatible:
            lane = "self-hosted"
            detail = ", ".join(sorted(local_compatible))

    if lane == "advanced/experimental":
        return (
            "WARN",
            "no OpenAI-compatible, Google, or localhost self-hosted first-class lane configured",
        )

    google_warnings = []
    if lane == "google":
        for provider in providers:
            if provider.provider_type != "vertex_ai":
                continue
            if not provider.metadata.get("project_id"):
                google_warnings.append(f"{provider.id}: missing metadata.project_id")
            if not provider.metadata.get("location"):
                google_warnings.append(f"{provider.id}: missing metadata.location")
        if google_warnings:
            return "WARN", "; ".join(google_warnings)

    placeholder_warnings = []
    for provider in providers:
        if provider.provider_type not in _OPENAI_TYPES | _GOOGLE_TYPES:
            continue
        if provider.endpoint in _PLACEHOLDER_ENDPOINTS:
            placeholder_warnings.append(f"{provider.id}: endpoint still placeholder")
        if provider.auth_mode in _SECRET_AUTH_MODES and not provider.secret_ref:
            placeholder_warnings.append(f"{provider.id}: missing secret_ref")
    if placeholder_warnings:
        return "WARN", "; ".join(placeholder_warnings)

    return "PASS", f"{lane} lane ready for smoke checks via: {detail}"


def _check_local_reachability(config: TeamConfig) -> tuple[bool, str]:
    local_targets: list[tuple[str, str, int]] = []
    for provider in config.providers.values():
        host, port = _endpoint_target(provider.endpoint)
        if host and port and _is_local_host(host):
            local_targets.append((provider.id, host, port))

    if not local_targets:
        return True, "no localhost providers configured"

    failures: list[str] = []
    for provider_id, host, port in local_targets:
        try:
            with socket.create_connection((host, port), timeout=1.5):
                pass
        except OSError as exc:
            failures.append(f"{provider_id}@{host}:{port} ({exc})")

    if failures:
        return False, "; ".join(failures)
    return True, ", ".join(f"{pid}@{h}:{p}" for pid, h, p in local_targets)


def _check_model_connectivity(config: TeamConfig) -> tuple[bool, str]:
    registry = build_model_registry(config)
    by_role = config.by_role()
    first_role = next(iter(by_role))
    model = registry.resolve_model(first_role.value, "json")
    provider = registry.create_provider(model.config)
    response = provider.invoke(
        ModelRequest(
            role=model.config.role,
            system_prompt="Reply with exactly: pong",
            user_prompt="ping",
            temperature=0.0,
        )
    )
    if response.content.strip():
        return True, f"{model.config.provider} / {model.config.model} responded"
    return False, "empty response"


def _compute_overall_status(
    has_providers: bool,
    has_models: bool,
    missing_roles: list[str],
    provider_with_placeholder: ProviderReadiness | None,
    provider_with_missing_secret: ProviderReadiness | None,
    local_ok: bool,
    lane_status: str,
    lane_detail: str,
    model_conn_ok: bool | None,
    model_conn_detail: str,
    optional_unavailable: bool,
) -> ReadinessState:
    if not has_providers:
        return ReadinessState(
            status=ReadinessStatus.needs_provider,
            detail="No providers configured in profile.",
            next_actions=[
                "Launch the app and add a provider from Settings.",
                "Or create a valid providers.json profile document in the shared config directory.",
            ],
        )
    if not has_models:
        return ReadinessState(
            status=ReadinessStatus.needs_model,
            detail="No models configured in profile.",
            next_actions=[
                "Update the shared provider profile so at least one planner model is bound.",
            ],
        )
    if provider_with_placeholder is not None:
        return ReadinessState(
            status=ReadinessStatus.endpoint_unreachable,
            detail=f"Provider '{provider_with_placeholder.provider_id}' has placeholder endpoint: {provider_with_placeholder.endpoint}",
            next_actions=[
                f"Open Settings and replace the placeholder endpoint for '{provider_with_placeholder.provider_id}'.",
            ],
        )
    if provider_with_missing_secret is not None:
        return ReadinessState(
            status=ReadinessStatus.needs_secret,
            detail=f"Provider '{provider_with_missing_secret.provider_id}' is missing a secret.",
            next_actions=[
                f"Open Settings and re-save '{provider_with_missing_secret.provider_id}' with valid credentials.",
            ],
        )
    if missing_roles:
        return ReadinessState(
            status=ReadinessStatus.needs_roles,
            missing_roles=missing_roles,
            detail=f"missing roles: {', '.join(missing_roles)}",
            next_actions=[
                "Update the shared provider profile so a planner model is assigned.",
            ],
        )
    if not local_ok:
        return ReadinessState(
            status=ReadinessStatus.endpoint_unreachable,
            detail="Local endpoint unreachable.",
            next_actions=[
                "Start the local provider server (e.g., Ollama, LM Studio).",
            ],
        )
    if lane_status == "WARN":
        if "placeholder" in lane_detail:
            return ReadinessState(
                status=ReadinessStatus.endpoint_unreachable,
                detail=lane_detail,
                next_actions=[
                    "Open Settings and replace placeholder provider endpoints with real API base URLs.",
                ],
            )
        if "missing secret_ref" in lane_detail:
            return ReadinessState(
                status=ReadinessStatus.needs_secret,
                detail=lane_detail,
                next_actions=[
                    "Open Settings and re-save the affected provider with working credentials.",
                ],
            )
    if model_conn_ok is False:
        lower_detail = model_conn_detail.lower()
        if any(
            kw in lower_detail
            for kw in (
                "auth",
                "unauthorized",
                "401",
                "403",
                "api key",
                "credential",
                "authentication",
            )
        ):
            return ReadinessState(
                status=ReadinessStatus.auth_failed,
                detail=f"Authentication failed: {model_conn_detail}",
                next_actions=[
                    "Open Settings and re-save the provider credentials, then test the provider again.",
                    "Use `agentheim-code provider-test` when you want to validate credentials from the terminal.",
                ],
            )
        return ReadinessState(
            status=ReadinessStatus.model_failed,
            detail=f"Model connectivity check failed: {model_conn_detail}",
            next_actions=[
                "Re-test the provider from Settings or with `agentheim-code provider-test` using the intended model.",
                "Run `agentheim-code doctor` after fixing provider endpoint, auth, or model selection issues.",
            ],
        )
    if optional_unavailable:
        return ReadinessState(
            status=ReadinessStatus.optional_integration_unavailable,
            detail="Some optional integrations are unavailable.",
            next_actions=[
                "Optional integrations are not required for basic operation.",
            ],
        )
    return ReadinessState(
        status=ReadinessStatus.ready,
        detail="All checks passed.",
        next_actions=[
            "Launch the workbench with `agentheim-code app --web` or open the packaged desktop shell.",
            "Start a session and send a prompt from the coder UI or `agentheim-code coder`.",
        ],
    )


def build_readiness_state(
    *,
    profile: str | None = None,
    skip_connectivity: bool = False,
    check_optional_integrations: bool = True,
) -> ReadinessState:
    """Build the shared readiness state for the current environment."""
    try:
        config = load_team_config(profile=profile)
    except ConfigError as exc:
        return ReadinessState(
            status=ReadinessStatus.needs_provider,
            detail=str(exc),
            next_actions=[
                "Launch the app and add a provider from Settings.",
                "Or create a valid providers.json profile document in the shared config directory.",
            ],
        )

    profile_name = config.profile_name
    providers = list(config.providers.values())
    models = list(config.models.values())
    has_providers = bool(providers)
    has_models = bool(models)

    configured_providers: list[ProviderReadiness] = []
    provider_with_placeholder: ProviderReadiness | None = None
    provider_with_missing_secret: ProviderReadiness | None = None

    for provider in providers:
        provider_status = ReadinessStatus.ready
        provider_detail = "configured"
        if provider.endpoint in _PLACEHOLDER_ENDPOINTS:
            provider_status = ReadinessStatus.endpoint_unreachable
            provider_detail = f"endpoint is placeholder: {provider.endpoint}"
            provider_with_placeholder = ProviderReadiness(
                provider_id=provider.id,
                provider_type=provider.provider_type,
                endpoint=provider.endpoint,
                status=provider_status,
                detail=provider_detail,
            )
        elif (
            provider.auth_mode in _SECRET_AUTH_MODES
            and not provider.secret_ref
            and not provider.api_key
        ):
            provider_status = ReadinessStatus.needs_secret
            provider_detail = "missing secret_ref"
            provider_with_missing_secret = ProviderReadiness(
                provider_id=provider.id,
                provider_type=provider.provider_type,
                endpoint=provider.endpoint,
                status=provider_status,
                detail=provider_detail,
            )
        configured_providers.append(
            ProviderReadiness(
                provider_id=provider.id,
                provider_type=provider.provider_type,
                endpoint=provider.endpoint,
                status=provider_status,
                detail=provider_detail,
            )
        )

    missing_roles: list[str] = []
    role_detail = ""
    if has_providers and has_models:
        missing_roles, role_detail = _check_role_coverage(config)

    lane_status = "SKIP"
    lane_detail = ""
    if has_providers and has_models and not missing_roles:
        lane_status, lane_detail = _check_first_class_lane(config)

    local_ok = True
    local_detail = ""
    if has_providers:
        local_ok, local_detail = _check_local_reachability(config)

    model_conn_ok: bool | None = None
    model_conn_detail = ""
    if not skip_connectivity and has_providers and has_models and not missing_roles and local_ok:
        try:
            model_conn_ok, model_conn_detail = _check_model_connectivity(config)
        except Exception as exc:
            model_conn_ok = False
            model_conn_detail = str(exc)

    optional_integrations: list[OptionalIntegrationState] = []
    if check_optional_integrations:
        from interfaces.integration_checks import check_all_optional_integrations

        optional_integrations = check_all_optional_integrations(repo_root=None)

    any_optional_unavailable = any(not oi.available for oi in optional_integrations)

    state = _compute_overall_status(
        has_providers=has_providers,
        has_models=has_models,
        missing_roles=missing_roles,
        provider_with_placeholder=provider_with_placeholder,
        provider_with_missing_secret=provider_with_missing_secret,
        local_ok=local_ok,
        lane_status=lane_status,
        lane_detail=lane_detail,
        model_conn_ok=model_conn_ok,
        model_conn_detail=model_conn_detail,
        optional_unavailable=any_optional_unavailable,
    )

    state.profile_name = profile_name
    state.model_count = len(models)
    state.configured_providers = configured_providers
    state.missing_roles = missing_roles
    state.optional_integrations = optional_integrations
    state.lane = lane_status if lane_status != "SKIP" else ""
    state.lane_detail = lane_detail
    state.local_reachability_ok = local_ok
    state.local_reachability_detail = local_detail
    state.model_connectivity_ok = model_conn_ok
    state.model_connectivity_detail = model_conn_detail
    state.privacy_mode = config.privacy_mode

    return state
