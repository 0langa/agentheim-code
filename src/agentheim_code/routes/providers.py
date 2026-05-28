from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Never, cast

from fastapi import APIRouter, HTTPException

from agentheim_code.http_context import REQUEST_ID_HEADER, new_request_id
from agentheim_code.provider_capabilities import get_capabilities
from agentheim_code.provider_discovery import list_remote_models
from agentheim_code.provider_management import (
    ValidationError,
    add_account,
    add_model,
    assign_role,
    create_profile,
    delete_account,
    delete_model,
    delete_profile,
    duplicate_profile,
    export_profile,
    get_profile,
    import_discovered_models,
    import_profile,
    list_profiles,
    rotate_secret,
    set_default_model,
    set_default_profile,
    test_account,
    update_account,
    update_model,
    update_profile,
)
from agentheim_code.provider_wizard import (
    create_profile as wizard_create_profile,
)
from agentheim_code.provider_wizard import (
    delete_profile as wizard_delete_profile,
)
from agentheim_code.provider_wizard import (
    get_templates,
    verify_provider_connection,
)
from config.config import (
    ModelBinding,
    ProviderAccount,
    list_provider_templates,
    load_profiles_document,
    save_profiles_document,
)

router = APIRouter()


def _backend() -> Any:
    from agentheim_code import backend

    return backend


def _utcnow() -> str:
    return datetime.now(tz=UTC).isoformat()


def _redact_account(account: ProviderAccount) -> dict[str, Any]:
    d: dict[str, Any] = account.model_dump()
    if account.secret_ref:
        d["secret_ref"] = "***"
    d["has_secret"] = bool(account.secret_ref)
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


def _management_error(exc: ValidationError) -> Never:
    raise HTTPException(
        status_code=400,
        detail=exc.to_dict(),
        headers={REQUEST_ID_HEADER: new_request_id()},
    )


@router.get("/api/providers/health")
def api_provider_health() -> dict[str, Any]:
    health = _backend().load_health()
    return {"health": {k: v.to_dict() for k, v in health.items()}}


@router.get("/api/providers/templates")
def api_provider_templates() -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], list_provider_templates(include_experimental=True))


@router.get("/api/providers/profiles")
def api_provider_profiles() -> dict[str, Any]:
    try:
        document = _backend().load_profiles_document()
    except Exception as exc:
        return {"configured": False, "error": str(exc), "profiles": []}
    return {
        "configured": True,
        "default_profile": document.default_profile,
        "profiles": [
            {
                "name": profile.name,
                "providers": [
                    {
                        "id": provider.id,
                        "kind": provider.kind,
                        "auth_mode": provider.auth_mode,
                        "endpoint": provider.endpoint,
                        "has_secret": bool(provider.secret_ref),
                    }
                    for provider in profile.providers.values()
                ],
                "models": [binding.model_dump() for binding in profile.models.values()],
            }
            for profile in document.profiles.values()
        ],
    }


@router.get("/api/providers/wizard-templates")
def api_wizard_templates() -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], get_templates(include_experimental=True))


@router.post("/api/providers/profiles")
def api_create_provider_profile(body: dict[str, Any]) -> dict[str, Any]:
    profile = wizard_create_profile(
        name=body["name"],
        provider_kind=body["provider_kind"],
        provider_id=body["provider_id"],
        model_id=body["model_id"],
        fields=body.get("fields", {}),
        set_as_default=body.get("set_as_default", False),
    )
    return {"ok": True, "profile": profile.model_dump()}


@router.delete("/api/providers/profiles/{name}")
def api_delete_provider_profile(name: str) -> dict[str, Any]:
    wizard_delete_profile(name)
    return {"ok": True}


@router.post("/api/providers/test")
def api_test_provider(body: dict[str, Any]) -> dict[str, Any]:
    return verify_provider_connection(
        provider_kind=body["provider_kind"],
        fields=body.get("fields", {}),
        model_id=body.get("model_id", ""),
    )


@router.get("/api/provider-management/profiles")
def api_mgmt_list_profiles() -> dict[str, Any]:
    return list_profiles()


@router.post("/api/provider-management/profiles")
def api_mgmt_create_profile(body: dict[str, Any]) -> dict[str, Any]:
    try:
        profile = create_profile(
            name=body["name"],
            set_as_default=body.get("set_as_default", False),
        )
        return {"ok": True, "profile": {"name": profile.name}}
    except ValidationError as exc:
        return _management_error(exc)


@router.get("/api/provider-management/profiles/{profile_name}")
def api_mgmt_get_profile(profile_name: str) -> dict[str, Any]:
    try:
        return {"ok": True, "profile": get_profile(profile_name)}
    except ValidationError as exc:
        return _management_error(exc)


@router.patch("/api/provider-management/profiles/{profile_name}")
def api_mgmt_patch_profile(profile_name: str, body: dict[str, Any]) -> dict[str, Any]:
    try:
        profile = update_profile(profile_name, body)
        return {"ok": True, "profile": {"name": profile.name}}
    except ValidationError as exc:
        return _management_error(exc)


@router.delete("/api/provider-management/profiles/{profile_name}")
def api_mgmt_delete_profile(profile_name: str) -> dict[str, Any]:
    try:
        delete_profile(profile_name)
        return {"ok": True}
    except ValidationError as exc:
        return _management_error(exc)


@router.post("/api/provider-management/profiles/{profile_name}/duplicate")
def api_mgmt_duplicate_profile(profile_name: str, body: dict[str, Any]) -> dict[str, Any]:
    try:
        target = body.get("target_name", f"{profile_name} copy")
        profile = duplicate_profile(profile_name, target)
        return {"ok": True, "profile": {"name": profile.name}}
    except ValidationError as exc:
        return _management_error(exc)


@router.post("/api/provider-management/profiles/{profile_name}/set-default")
def api_mgmt_set_default_profile(profile_name: str) -> dict[str, Any]:
    try:
        set_default_profile(profile_name)
        return {"ok": True}
    except ValidationError as exc:
        return _management_error(exc)


@router.get("/api/provider-management/profiles/{profile_name}/export")
def api_mgmt_export_profile(profile_name: str) -> dict[str, Any]:
    try:
        return {"ok": True, "data": export_profile(profile_name)}
    except ValidationError as exc:
        return _management_error(exc)


@router.post("/api/provider-management/profiles/import")
def api_mgmt_import_profile(body: dict[str, Any]) -> dict[str, Any]:
    try:
        profile = import_profile(body.get("data", {}), name=body.get("name"))
        return {"ok": True, "profile": {"name": profile.name}}
    except ValidationError as exc:
        return _management_error(exc)


@router.post("/api/provider-management/profiles/{profile_name}/accounts")
def api_mgmt_add_account(profile_name: str, body: dict[str, Any]) -> dict[str, Any]:
    try:
        account = ProviderAccount.model_validate(body)
        add_account(profile_name, account)
        return {"ok": True, "account": _redact_account(account)}
    except ValidationError as exc:
        return _management_error(exc)


@router.patch("/api/provider-management/profiles/{profile_name}/accounts/{account_id}")
def api_mgmt_patch_account(
    profile_name: str, account_id: str, body: dict[str, Any]
) -> dict[str, Any]:
    try:
        account = update_account(profile_name, account_id, body)
        return {"ok": True, "account": _redact_account(account)}
    except ValidationError as exc:
        return _management_error(exc)


@router.delete("/api/provider-management/profiles/{profile_name}/accounts/{account_id}")
def api_mgmt_delete_account(
    profile_name: str, account_id: str, cascade: bool = False
) -> dict[str, Any]:
    try:
        delete_account(profile_name, account_id, cascade=cascade)
        return {"ok": True}
    except ValidationError as exc:
        return _management_error(exc)


@router.post("/api/provider-management/profiles/{profile_name}/accounts/{account_id}/test")
def api_mgmt_test_account(
    profile_name: str, account_id: str, body: dict[str, Any] | None = None
) -> dict[str, Any]:
    try:
        result = test_account(
            profile_name,
            account_id,
            sample_model=(body or {}).get("model_id", ""),
        )
        return {"ok": True, "result": result}
    except ValidationError as exc:
        return _management_error(exc)


@router.post("/api/provider-management/accounts/test-draft")
def api_mgmt_test_account_draft(body: dict[str, Any]) -> dict[str, Any]:
    try:
        if "account" not in body:
            raise ValidationError(
                "missing_account", "Draft account payload is required.", "account"
            )
        account = ProviderAccount.model_validate(body["account"])
        result = _backend().validate_account_draft(
            account,
            secret_value=body.get("secret_value", ""),
            sample_model=body.get("model_id", ""),
            profile_name=body.get("profile_name"),
            existing_account_id=body.get("existing_account_id"),
        )
        return {"ok": True, "result": result}
    except ValidationError as exc:
        return _management_error(exc)


@router.post("/api/provider-management/profiles/{profile_name}/accounts/{account_id}/rotate-secret")
def api_mgmt_rotate_secret(
    profile_name: str, account_id: str, body: dict[str, Any]
) -> dict[str, Any]:
    try:
        rotate_secret(
            profile_name,
            account_id,
            secret_name=body.get("secret_name", "api_key"),
            secret_value=body.get("secret_value", ""),
        )
        return {"ok": True}
    except ValidationError as exc:
        return _management_error(exc)


def _do_discover_models(profile_name: str, account_id: str, *, persist: bool) -> dict[str, Any]:
    doc = load_profiles_document()
    profile = doc.profiles.get(profile_name)
    if not profile:
        raise ValidationError("profile_not_found", f"Profile '{profile_name}' not found.")
    account = profile.providers.get(account_id)
    if not account:
        raise ValidationError("account_not_found", f"Account '{account_id}' not found.")
    caps = get_capabilities(account.kind)
    if not caps.supports_remote_model_listing:
        return {
            "ok": True,
            "supported": False,
            "discovery_mode": caps.discovery_mode,
            "models": [],
        }
    discovered = list_remote_models(account)
    if persist:
        account = account.model_copy(update={"last_model_sync_at": _utcnow()})
        profile.providers[account_id] = account
        doc.profiles[profile_name] = profile
        save_profiles_document(doc)
    return {
        "ok": True,
        "supported": True,
        "discovery_mode": caps.discovery_mode,
        "models": [m.to_dict() for m in discovered],
    }


@router.post(
    "/api/provider-management/profiles/{profile_name}/accounts/{account_id}/discover-models"
)
def api_mgmt_discover_models(profile_name: str, account_id: str) -> dict[str, Any]:
    try:
        return _do_discover_models(profile_name, account_id, persist=True)
    except ValidationError as exc:
        return _management_error(exc)


@router.get(
    "/api/provider-management/profiles/{profile_name}/accounts/{account_id}/discovered-models"
)
def api_mgmt_get_discovered_models(profile_name: str, account_id: str) -> dict[str, Any]:
    try:
        return _do_discover_models(profile_name, account_id, persist=False)
    except ValidationError as exc:
        return _management_error(exc)


@router.post("/api/provider-management/profiles/{profile_name}/models")
def api_mgmt_add_model(profile_name: str, body: dict[str, Any]) -> dict[str, Any]:
    try:
        binding = ModelBinding.model_validate(body)
        add_model(profile_name, binding)
        return {"ok": True, "model": _redact_binding(binding)}
    except ValidationError as exc:
        return _management_error(exc)


@router.patch("/api/provider-management/profiles/{profile_name}/models/{binding_id}")
def api_mgmt_patch_model(
    profile_name: str, binding_id: str, body: dict[str, Any]
) -> dict[str, Any]:
    try:
        binding = update_model(profile_name, binding_id, body)
        return {"ok": True, "model": _redact_binding(binding)}
    except ValidationError as exc:
        return _management_error(exc)


@router.delete("/api/provider-management/profiles/{profile_name}/models/{binding_id}")
def api_mgmt_delete_model(profile_name: str, binding_id: str) -> dict[str, Any]:
    try:
        delete_model(profile_name, binding_id)
        return {"ok": True}
    except ValidationError as exc:
        return _management_error(exc)


@router.post("/api/provider-management/profiles/{profile_name}/models/{binding_id}/set-default")
def api_mgmt_set_default_model(profile_name: str, binding_id: str) -> dict[str, Any]:
    try:
        binding = set_default_model(profile_name, binding_id)
        return {"ok": True, "model": _redact_binding(binding)}
    except ValidationError as exc:
        return _management_error(exc)


@router.post("/api/provider-management/profiles/{profile_name}/models/{binding_id}/assign-role")
def api_mgmt_assign_role(
    profile_name: str, binding_id: str, body: dict[str, Any]
) -> dict[str, Any]:
    try:
        binding = assign_role(profile_name, binding_id, body.get("role", "planner"))
        return {"ok": True, "model": _redact_binding(binding)}
    except ValidationError as exc:
        return _management_error(exc)


@router.post("/api/provider-management/profiles/{profile_name}/models/import-discovered")
def api_mgmt_import_discovered(profile_name: str, body: dict[str, Any]) -> dict[str, Any]:
    try:
        imported = import_discovered_models(
            profile_name,
            account_id=body["account_id"],
            models=body.get("models", []),
        )
        return {"ok": True, "models": [_redact_binding(m) for m in imported]}
    except ValidationError as exc:
        return _management_error(exc)


@router.get("/api/provider-management/templates")
def api_mgmt_templates() -> list[dict[str, Any]]:
    templates = list_provider_templates(include_experimental=True)
    for t in templates:
        caps = get_capabilities(t["kind"])
        t["capabilities_meta"] = caps.to_dict()
    return cast(list[dict[str, Any]], templates)


@router.get("/api/provider-management/templates/{template_id}")
def api_mgmt_template(template_id: str) -> dict[str, Any]:
    templates = {t["kind"]: t for t in list_provider_templates(include_experimental=True)}
    if template_id not in templates:
        raise HTTPException(status_code=404, detail="Template not found")
    t = templates[template_id]
    caps = get_capabilities(template_id)
    return {"ok": True, "template": {**t, "capabilities_meta": caps.to_dict()}}
