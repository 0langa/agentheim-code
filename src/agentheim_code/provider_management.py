"""Provider and model management service layer.

Implements profile/account/model CRUD, secret rotation, import/export,
and structured validation errors on top of the shared config storage.
"""

from __future__ import annotations

import contextlib
import logging
from datetime import UTC, datetime
from typing import Any, cast

from config.config import (
    ModelBinding,
    ModelRole,
    ProfilesDocument,
    ProviderAccount,
    TeamProfile,
    get_secret_store,
    load_profiles_document,
    make_secret_ref,
    normalize_model_binding,
    save_profiles_document,
)
from config.config import list_provider_templates as _list_templates

logger = logging.getLogger("agentheim_code.provider_management")


class ValidationError(Exception):
    def __init__(self, code: str, message: str, field: str | None = None) -> None:
        self.code = code
        self.message = message
        self.field = field
        super().__init__(message)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.field:
            result["field"] = self.field
        return result


def _utcnow() -> str:
    return datetime.now(tz=UTC).isoformat()


def _redact_account(account: ProviderAccount) -> dict[str, Any]:
    d: dict[str, Any] = account.model_dump()
    if account.secret_ref:
        d["secret_ref"] = "***"
    d["has_secret"] = bool(account.secret_ref)
    # Redact any header that looks like a secret
    redacted_headers: dict[str, str] = {}
    for k, v in account.headers.items():
        if any(s in k.lower() for s in ("secret", "key", "token", "password", "credential")):
            redacted_headers[k] = f"{v[:2]}***{v[-2:]}" if len(v) > 4 else "****"
        else:
            redacted_headers[k] = v
    d["headers"] = redacted_headers
    return d


def _redact_binding(binding: ModelBinding) -> dict[str, Any]:
    return cast(dict[str, Any], binding.model_dump())


def _template_map() -> dict[str, dict[str, Any]]:
    return {t["kind"]: t for t in _list_templates(include_experimental=True)}


def _ensure_doc() -> ProfilesDocument:
    try:
        return load_profiles_document()
    except Exception:
        return ProfilesDocument(version=1, default_profile="default", profiles={})


def _save(doc: ProfilesDocument) -> None:
    save_profiles_document(doc)


def _profile_or_raise(doc: ProfilesDocument, name: str) -> TeamProfile:
    if name not in doc.profiles:
        raise ValidationError("profile_not_found", f"Profile '{name}' not found.")
    return doc.profiles[name]


def _validate_provider_account(
    account: ProviderAccount, template_map: dict[str, dict[str, Any]] | None = None
) -> None:
    tmpl = (template_map or _template_map()).get(account.kind)
    if not tmpl and (not account.endpoint or account.endpoint == "-"):
        # Allow custom/unknown kinds as long as endpoint looks reasonable
        raise ValidationError(
            "invalid_endpoint", "Endpoint is required for custom providers.", "endpoint"
        )
    if not account.id or not account.id.strip():
        raise ValidationError("missing_id", "Provider account id is required.", "id")
    if account.id in {"new", "default", "auto"}:
        raise ValidationError("reserved_id", f"Provider id '{account.id}' is reserved.", "id")


def _validate_model_binding(binding: ModelBinding, profile: TeamProfile) -> None:
    if not binding.id or not binding.id.strip():
        raise ValidationError("missing_id", "Model binding id is required.", "id")
    if binding.provider not in profile.providers:
        raise ValidationError(
            "unknown_provider",
            f"Model binding references unknown provider '{binding.provider}'.",
            "provider",
        )


# ---------------------------------------------------------------------------
# Profile CRUD
# ---------------------------------------------------------------------------


def list_profiles() -> dict[str, Any]:
    doc = _ensure_doc()
    default_profile = doc.default_profile
    if doc.profiles and default_profile not in doc.profiles:
        default_profile = next(iter(doc.profiles))
    return {
        "configured": bool(doc.profiles),
        "default_profile": default_profile,
        "profiles": [
            {
                "name": p.name,
                "providers": [_redact_account(a) for a in p.providers.values()],
                "models": [_redact_binding(m) for m in p.models.values()],
            }
            for p in doc.profiles.values()
        ],
    }


def get_profile(name: str) -> dict[str, Any]:
    doc = _ensure_doc()
    profile = _profile_or_raise(doc, name)
    return {
        "name": profile.name,
        "providers": [_redact_account(a) for a in profile.providers.values()],
        "models": [_redact_binding(m) for m in profile.models.values()],
    }


def create_profile(name: str, set_as_default: bool = False) -> TeamProfile:
    if not name or not name.strip():
        raise ValidationError("missing_name", "Profile name is required.", "name")
    doc = _ensure_doc()
    if name in doc.profiles:
        raise ValidationError("duplicate_profile", f"Profile '{name}' already exists.", "name")
    profile = TeamProfile(name=name)
    doc.profiles[name] = profile
    if set_as_default or not doc.default_profile or doc.default_profile not in doc.profiles:
        doc.default_profile = name
    _save(doc)
    logger.info("Created profile '%s'", name)
    return profile


def update_profile(name: str, updates: dict[str, Any]) -> TeamProfile:
    doc = _ensure_doc()
    profile = _profile_or_raise(doc, name)
    allowed = {"privacy_mode"}
    changed = {k: v for k, v in updates.items() if k in allowed}
    if changed:
        profile = profile.model_copy(update=changed)
        doc.profiles[name] = profile
        _save(doc)
    return profile


def delete_profile(name: str) -> None:
    doc = _ensure_doc()
    profile = _profile_or_raise(doc, name)
    store = get_secret_store()
    for account in profile.providers.values():
        if account.secret_ref:
            with contextlib.suppress(Exception):
                store.delete(account.secret_ref)
    del doc.profiles[name]
    if doc.default_profile == name:
        doc.default_profile = next(iter(doc.profiles), "default")
    _save(doc)
    logger.info("Deleted profile '%s'", name)


def duplicate_profile(source_name: str, target_name: str) -> TeamProfile:
    doc = _ensure_doc()
    source = _profile_or_raise(doc, source_name)
    if target_name in doc.profiles:
        raise ValidationError(
            "duplicate_profile", f"Profile '{target_name}' already exists.", "name"
        )
    # Deep copy providers and models; do NOT copy secrets (user must re-enter)
    new_providers = {}
    for pid, acc in source.providers.items():
        new_acc = acc.model_copy(update={"secret_ref": None})
        new_providers[pid] = new_acc
    new_models = {}
    for mid, binding in source.models.items():
        new_models[mid] = binding.model_copy()
    target = TeamProfile(
        name=target_name,
        providers=new_providers,
        models=new_models,
        privacy_mode=source.privacy_mode,
    )
    doc.profiles[target_name] = target
    _save(doc)
    logger.info("Duplicated profile '%s' -> '%s'", source_name, target_name)
    return target


def set_default_profile(name: str) -> None:
    doc = _ensure_doc()
    _profile_or_raise(doc, name)
    doc.default_profile = name
    _save(doc)


def export_profile(name: str) -> dict[str, Any]:
    doc = _ensure_doc()
    profile = _profile_or_raise(doc, name)
    # Export must never include secrets
    return {
        "name": profile.name,
        "privacy_mode": profile.privacy_mode,
        "providers": [
            {**_redact_account(a), "secret_ref": None, "has_secret": bool(a.secret_ref)}
            for a in profile.providers.values()
        ],
        "models": [_redact_binding(m) for m in profile.models.values()],
    }


def import_profile(data: dict[str, Any], name: str | None = None) -> TeamProfile:
    """Import a profile from an exported JSON payload."""
    profile_name = (name or data.get("name", "")).strip()
    if not profile_name:
        raise ValidationError("missing_name", "Profile name is required for import.", "name")
    doc = _ensure_doc()
    if profile_name in doc.profiles:
        raise ValidationError(
            "duplicate_profile", f"Profile '{profile_name}' already exists.", "name"
        )

    raw_providers = data.get("providers", [])
    raw_models = data.get("models", [])
    providers: dict[str, ProviderAccount] = {}
    models: dict[str, ModelBinding] = {}

    for rp in raw_providers:
        if not isinstance(rp, dict):
            continue
        pid = str(rp.get("id", "")).strip()
        if not pid:
            continue
        providers[pid] = ProviderAccount(
            id=pid,
            kind=str(rp.get("kind", "openai_compatible")),
            endpoint=str(rp.get("endpoint", "-")),
            auth_mode=rp.get("auth_mode", "api_key"),
            secret_ref=None,
            timeout_seconds=int(rp.get("timeout_seconds", 60)),
            headers=dict(rp.get("headers", {})),
            metadata=dict(rp.get("metadata", {})),
            display_name=rp.get("display_name"),
            notes=rp.get("notes"),
            disabled=bool(rp.get("disabled", False)),
        )

    for rm in raw_models:
        if not isinstance(rm, dict):
            continue
        mid = str(rm.get("id", "")).strip()
        if not mid:
            continue
        models[mid] = ModelBinding(
            id=mid,
            role=rm.get("role", "planner"),
            provider=str(rm.get("provider", "")),
            model=str(rm.get("model", "")),
            display_name=rm.get("display_name"),
            capabilities=list(rm.get("capabilities", ["text"])),
            source=rm.get("source", "manual"),
            remote_id=rm.get("remote_id"),
            enabled=bool(rm.get("enabled", True)),
            is_default=bool(rm.get("is_default", False)),
            context_window=rm.get("context_window"),
            max_output_tokens=rm.get("max_output_tokens"),
            supports_tools=rm.get("supports_tools"),
            supports_vision=rm.get("supports_vision"),
            supports_streaming=rm.get("supports_streaming"),
            metadata=dict(rm.get("metadata", {})),
        )

    normalized_models = {
        mid: normalize_model_binding(
            binding,
            TeamProfile(name=profile_name, providers=providers, models={}),
        )
        for mid, binding in models.items()
    }
    profile = TeamProfile(
        name=profile_name,
        providers=providers,
        models=normalized_models,
        privacy_mode=str(data.get("privacy_mode", "standard")),
    )
    # Validate refs
    for m in profile.models.values():
        if m.provider not in profile.providers:
            raise ValidationError(
                "invalid_import",
                f"Imported model '{m.id}' references unknown provider '{m.provider}'.",
                "provider",
            )

    doc.profiles[profile_name] = profile
    _save(doc)
    logger.info("Imported profile '%s'", profile_name)
    return profile


# ---------------------------------------------------------------------------
# Provider Account CRUD
# ---------------------------------------------------------------------------


def add_account(profile_name: str, account: ProviderAccount) -> ProviderAccount:
    doc = _ensure_doc()
    profile = _profile_or_raise(doc, profile_name)
    _validate_provider_account(account)
    if account.id in profile.providers:
        raise ValidationError(
            "duplicate_account", f"Account '{account.id}' already exists in profile.", "id"
        )
    profile.providers[account.id] = account
    doc.profiles[profile_name] = profile
    _save(doc)
    logger.info("Added account '%s' to profile '%s'", account.id, profile_name)
    return account


def update_account(profile_name: str, account_id: str, updates: dict[str, Any]) -> ProviderAccount:
    doc = _ensure_doc()
    profile = _profile_or_raise(doc, profile_name)
    if account_id not in profile.providers:
        raise ValidationError("account_not_found", f"Account '{account_id}' not found.", "id")
    current = profile.providers[account_id]
    # Build a safe update dict
    allowed = {
        "endpoint",
        "auth_mode",
        "timeout_seconds",
        "headers",
        "metadata",
        "display_name",
        "notes",
        "disabled",
    }
    changed = {k: v for k, v in updates.items() if k in allowed}
    updated = cast(ProviderAccount, current.model_copy(update=changed))
    _validate_provider_account(updated)
    profile.providers[account_id] = updated
    # If provider id changed inside metadata or kind, update model bindings that reference it
    doc.profiles[profile_name] = profile
    _save(doc)
    logger.info("Updated account '%s' in profile '%s'", account_id, profile_name)
    return updated


def delete_account(profile_name: str, account_id: str, cascade: bool = False) -> None:
    doc = _ensure_doc()
    profile = _profile_or_raise(doc, profile_name)
    if account_id not in profile.providers:
        raise ValidationError("account_not_found", f"Account '{account_id}' not found.", "id")
    dependent = [m for m in profile.models.values() if m.provider == account_id]
    if dependent and not cascade:
        raise ValidationError(
            "dependent_models",
            f"Account '{account_id}' has {len(dependent)} model bindings. Use cascade=true to remove them.",
        )
    account = profile.providers[account_id]
    if account.secret_ref:
        with contextlib.suppress(Exception):
            get_secret_store().delete(account.secret_ref)
    del profile.providers[account_id]
    if cascade:
        profile.models = {mid: m for mid, m in profile.models.items() if m.provider != account_id}
    doc.profiles[profile_name] = profile
    _save(doc)
    logger.info(
        "Deleted account '%s' from profile '%s' (cascade=%s)", account_id, profile_name, cascade
    )


def rotate_secret(profile_name: str, account_id: str, secret_name: str, secret_value: str) -> None:
    doc = _ensure_doc()
    profile = _profile_or_raise(doc, profile_name)
    if account_id not in profile.providers:
        raise ValidationError("account_not_found", f"Account '{account_id}' not found.", "id")
    account = profile.providers[account_id]
    ref = make_secret_ref(account_id, secret_name)
    store = get_secret_store()
    store.set(ref, secret_value)
    updated = account.model_copy(update={"secret_ref": ref})
    profile.providers[account_id] = updated
    doc.profiles[profile_name] = profile
    _save(doc)
    logger.info("Rotated secret '%s' for account '%s'", secret_name, account_id)


def _account_fields(
    account: ProviderAccount,
    *,
    secret_value: str = "",
    fallback_secret_ref: str | None = None,
) -> dict[str, str]:
    fields: dict[str, str] = {"endpoint": account.endpoint}
    api_key = secret_value
    secret_ref = fallback_secret_ref or account.secret_ref
    if not api_key and secret_ref:
        with contextlib.suppress(Exception):
            api_key = get_secret_store().get(secret_ref) or ""
    if api_key:
        fields["api_key"] = api_key
    for key, value in account.headers.items():
        fields[key] = value
    for key, value in account.metadata.items():
        if isinstance(value, str):
            fields[key] = value
    return fields


def test_account(profile_name: str, account_id: str, sample_model: str = "") -> dict[str, Any]:
    """Test a saved provider account by performing a real inference call."""
    from agentheim_code.provider_wizard import verify_provider_connection

    doc = _ensure_doc()
    profile = _profile_or_raise(doc, profile_name)
    if account_id not in profile.providers:
        raise ValidationError("account_not_found", f"Account '{account_id}' not found.", "id")
    account = profile.providers[account_id]
    fields = _account_fields(account)
    result = verify_provider_connection(
        provider_kind=account.kind,
        fields=fields,
        model_id=sample_model or str(account.metadata.get("deployment", "")).strip(),
    )
    # Persist verification result
    status = "ok" if result.get("ok") else "failed"
    updated = account.model_copy(
        update={
            "last_verified_at": _utcnow(),
            "last_verified_status": status,
            "last_verified_error": result.get("error") or None,
        }
    )
    profile.providers[account_id] = updated
    doc.profiles[profile_name] = profile
    _save(doc)
    return result


def validate_account_draft(
    account: ProviderAccount,
    *,
    secret_value: str = "",
    sample_model: str = "",
    profile_name: str | None = None,
    existing_account_id: str | None = None,
) -> dict[str, Any]:
    """Test an unsaved provider draft without mutating stored profile state."""
    from agentheim_code.provider_wizard import verify_provider_connection

    _validate_provider_account(account)
    fallback_secret_ref: str | None = None
    if profile_name and existing_account_id:
        doc = _ensure_doc()
        profile = _profile_or_raise(doc, profile_name)
        existing = profile.providers.get(existing_account_id)
        if existing:
            fallback_secret_ref = existing.secret_ref

    fields = _account_fields(
        account,
        secret_value=secret_value,
        fallback_secret_ref=fallback_secret_ref,
    )
    return verify_provider_connection(
        provider_kind=account.kind,
        fields=fields,
        model_id=sample_model or str(account.metadata.get("deployment", "")).strip(),
    )


# ---------------------------------------------------------------------------
# Model Binding CRUD
# ---------------------------------------------------------------------------


def add_model(profile_name: str, binding: ModelBinding) -> ModelBinding:
    doc = _ensure_doc()
    profile = _profile_or_raise(doc, profile_name)
    _validate_model_binding(binding, profile)
    binding = normalize_model_binding(binding, profile)
    if binding.id in profile.models:
        raise ValidationError(
            "duplicate_binding", f"Model binding '{binding.id}' already exists.", "id"
        )
    # If this is the first binding or marked default, clear other defaults
    if binding.is_default or not profile.models:
        for m in profile.models.values():
            if m.is_default:
                profile.models[m.id] = m.model_copy(update={"is_default": False})
        binding = binding.model_copy(update={"is_default": True})
    profile.models[binding.id] = binding
    doc.profiles[profile_name] = profile
    _save(doc)
    logger.info("Added model binding '%s' to profile '%s'", binding.id, profile_name)
    return binding


def update_model(profile_name: str, binding_id: str, updates: dict[str, Any]) -> ModelBinding:
    doc = _ensure_doc()
    profile = _profile_or_raise(doc, profile_name)
    if binding_id not in profile.models:
        raise ValidationError("binding_not_found", f"Model binding '{binding_id}' not found.", "id")
    current = profile.models[binding_id]
    allowed = {
        "role",
        "provider",
        "model",
        "display_name",
        "capabilities",
        "enabled",
        "is_default",
        "context_window",
        "max_output_tokens",
        "supports_tools",
        "supports_vision",
        "supports_streaming",
        "metadata",
    }
    changed = {k: v for k, v in updates.items() if k in allowed}
    updated = cast(ModelBinding, current.model_copy(update=changed))
    _validate_model_binding(updated, profile)
    updated = normalize_model_binding(updated, profile)
    # Handle default switch
    if updated.is_default and not current.is_default:
        for m in profile.models.values():
            if m.is_default and m.id != binding_id:
                profile.models[m.id] = m.model_copy(update={"is_default": False})
    profile.models[binding_id] = updated
    doc.profiles[profile_name] = profile
    _save(doc)
    logger.info("Updated model binding '%s' in profile '%s'", binding_id, profile_name)
    return updated


def delete_model(profile_name: str, binding_id: str) -> None:
    doc = _ensure_doc()
    profile = _profile_or_raise(doc, profile_name)
    if binding_id not in profile.models:
        raise ValidationError("binding_not_found", f"Model binding '{binding_id}' not found.", "id")
    del profile.models[binding_id]
    doc.profiles[profile_name] = profile
    _save(doc)
    logger.info("Deleted model binding '%s' from profile '%s'", binding_id, profile_name)


def set_default_model(profile_name: str, binding_id: str) -> ModelBinding:
    doc = _ensure_doc()
    profile = _profile_or_raise(doc, profile_name)
    if binding_id not in profile.models:
        raise ValidationError("binding_not_found", f"Model binding '{binding_id}' not found.", "id")
    for m in profile.models.values():
        if m.is_default:
            profile.models[m.id] = m.model_copy(update={"is_default": False})
    updated = cast(ModelBinding, profile.models[binding_id].model_copy(update={"is_default": True}))
    profile.models[binding_id] = updated
    doc.profiles[profile_name] = profile
    _save(doc)
    logger.info("Set default model '%s' in profile '%s'", binding_id, profile_name)
    return updated


def assign_role(profile_name: str, binding_id: str, role: str) -> ModelBinding:
    doc = _ensure_doc()
    profile = _profile_or_raise(doc, profile_name)
    if binding_id not in profile.models:
        raise ValidationError("binding_not_found", f"Model binding '{binding_id}' not found.", "id")
    try:
        validated_role = ModelRole(role)
    except ValueError as exc:
        allowed = ", ".join(member.value for member in ModelRole)
        raise ValidationError(
            "invalid_role",
            f"Unknown model role '{role}'. Allowed roles: {allowed}.",
            "role",
        ) from exc
    updated = cast(
        ModelBinding, profile.models[binding_id].model_copy(update={"role": validated_role})
    )
    profile.models[binding_id] = updated
    doc.profiles[profile_name] = profile
    _save(doc)
    logger.info(
        "Assigned role '%s' to model '%s' in profile '%s'",
        validated_role.value,
        binding_id,
        profile_name,
    )
    return updated


def import_discovered_models(
    profile_name: str, account_id: str, models: list[dict[str, Any]]
) -> list[ModelBinding]:
    doc = _ensure_doc()
    profile = _profile_or_raise(doc, profile_name)
    if account_id not in profile.providers:
        raise ValidationError("account_not_found", f"Account '{account_id}' not found.", "id")
    created: list[ModelBinding] = []
    for raw in models:
        model_id = str(raw.get("provider_model_name", raw.get("id", ""))).strip()
        if not model_id:
            continue
        display = raw.get("display_name") or model_id
        caps = list(raw.get("capabilities", ["text"]))
        binding_id = model_id.replace("/", "_").replace(":", "_")
        # Avoid duplicates
        if binding_id in profile.models:
            continue
        binding = ModelBinding(
            id=binding_id,
            role="planner",
            provider=account_id,
            model=model_id,
            display_name=display,
            capabilities=caps,
            source="discovered",
            remote_id=raw.get("id") or model_id,
            context_window=raw.get("context_window"),
            max_output_tokens=raw.get("max_output_tokens"),
            supports_tools=raw.get("supports_tools"),
            supports_vision=raw.get("supports_vision"),
            supports_streaming=raw.get("supports_streaming"),
        )
        binding = normalize_model_binding(binding, profile)
        profile.models[binding_id] = binding
        created.append(binding)
    doc.profiles[profile_name] = profile
    _save(doc)
    logger.info("Imported %d discovered models into profile '%s'", len(created), profile_name)
    return created
