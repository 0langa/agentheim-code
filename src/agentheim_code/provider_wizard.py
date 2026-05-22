from __future__ import annotations

import contextlib
import logging
from pathlib import Path
from typing import Any, cast

from config.config import (
    ModelBinding,
    ProfilesDocument,
    ProviderAccount,
    TeamProfile,
    get_secret_store,
    list_provider_templates,
    load_profiles_document,
    make_secret_ref,
    save_profiles_document,
)

logger = logging.getLogger("agentheim_code.provider_wizard")


def _profiles_path() -> Path:
    from config.config import get_config_dir

    return cast(Path, get_config_dir()) / "profiles.toml"


def get_templates(include_experimental: bool = False) -> list[dict[str, Any]]:
    """Return provider templates augmented with wizard field schemas."""
    templates = cast(
        list[dict[str, Any]], list_provider_templates(include_experimental=include_experimental)
    )
    field_map = {
        "openai_compatible": [
            {"name": "api_key", "label": "API Key", "type": "password", "required": True},
            {"name": "endpoint", "label": "Base URL", "type": "url", "required": True},
        ],
        "azure_foundry": [
            {"name": "api_key", "label": "API Key", "type": "password", "required": True},
            {"name": "endpoint", "label": "Endpoint URL", "type": "url", "required": True},
            {"name": "deployment", "label": "Deployment Name", "type": "text", "required": False},
        ],
        "aws_bedrock": [
            {
                "name": "region",
                "label": "AWS Region",
                "type": "text",
                "required": True,
                "default": "us-east-1",
            },
            {"name": "access_key_id", "label": "Access Key ID", "type": "text", "required": False},
            {
                "name": "secret_access_key",
                "label": "Secret Access Key",
                "type": "password",
                "required": False,
            },
        ],
        "gemini": [
            {"name": "api_key", "label": "API Key", "type": "password", "required": True},
        ],
        "anthropic": [
            {"name": "api_key", "label": "API Key", "type": "password", "required": True},
        ],
        "oci_genai": [
            {
                "name": "config_path",
                "label": "OCI Config Path",
                "type": "text",
                "required": False,
                "default": "~/.oci/config",
            },
            {
                "name": "profile",
                "label": "OCI Profile",
                "type": "text",
                "required": False,
                "default": "DEFAULT",
            },
        ],
        "ollama": [
            {
                "name": "endpoint",
                "label": "Ollama Host",
                "type": "url",
                "required": True,
                "default": "http://localhost:11434",
            },
        ],
        "lm_studio": [
            {
                "name": "endpoint",
                "label": "LM Studio URL",
                "type": "url",
                "required": True,
                "default": "http://localhost:1234/v1",
            },
        ],
        "llama_cpp": [
            {
                "name": "endpoint",
                "label": "Server URL",
                "type": "url",
                "required": True,
                "default": "http://localhost:8080/v1",
            },
        ],
    }
    for template in templates:
        ptype = template.get("provider_type", "")
        template["wizard_fields"] = field_map.get(
            ptype,
            [
                {"name": "api_key", "label": "API Key", "type": "password", "required": True},
                {"name": "endpoint", "label": "Endpoint", "type": "url", "required": False},
            ],
        )
    return templates


def create_profile(
    name: str,
    provider_kind: str,
    provider_id: str,
    model_id: str,
    fields: dict[str, str],
    set_as_default: bool = False,
) -> TeamProfile:
    """Create a new provider profile with a single provider and model binding."""
    templates = list_provider_templates(include_experimental=True)
    template_map = {t["kind"]: t for t in templates}
    if provider_kind not in template_map:
        raise ValueError(f"Unknown provider kind: {provider_kind}")

    template = template_map[provider_kind]
    endpoint = fields.get("endpoint", fields.get("base_url", template.get("endpoint", "-")))
    if endpoint in ("", "-"):
        endpoint = template.get("endpoint", "-")

    # Build provider account
    provider_account = ProviderAccount(
        id=provider_id,
        kind=provider_kind,
        endpoint=endpoint,
        auth_mode=template.get("auth_mode", "api_key"),
        secret_ref=None,
        timeout_seconds=60,
        headers={},
        metadata={"template": provider_kind, "capabilities": template.get("capabilities", [])},
    )

    # Store secret if api_key provided
    api_key = fields.get("api_key", "")
    if api_key:
        secret_ref = make_secret_ref(provider_id)
        store = get_secret_store()
        store.set(secret_ref, api_key)
        provider_account = provider_account.model_copy(update={"secret_ref": secret_ref})

    # Handle AWS credentials in headers
    if provider_kind == "aws_bedrock":
        region = fields.get("region", "us-east-1")
        headers = {"aws-region": region}
        if fields.get("access_key_id"):
            headers["aws-access-key-id"] = fields["access_key_id"]
        if fields.get("secret_access_key"):
            secret_ref = make_secret_ref(provider_id, "aws_secret")
            store = get_secret_store()
            store.set(secret_ref, fields["secret_access_key"])
            headers["aws-secret-access-key-ref"] = secret_ref
        provider_account = provider_account.model_copy(update={"headers": headers})

    # Handle OCI config
    if provider_kind == "oci_genai":
        metadata = dict(provider_account.metadata)
        metadata["oci_config_path"] = fields.get("config_path", "~/.oci/config")
        metadata["oci_profile"] = fields.get("profile", "DEFAULT")
        provider_account = provider_account.model_copy(update={"metadata": metadata})

    # Build model binding
    model_binding = ModelBinding(
        id="planner",
        role="planner",
        provider=provider_id,
        model=model_id,
        capabilities=template.get("capabilities", ["text"]),
    )

    # Load existing document
    try:
        doc = load_profiles_document()
    except Exception:
        doc = ProfilesDocument(version=1, default_profile=name, profiles={})

    # Create or update profile
    if name in doc.profiles:
        profile = doc.profiles[name]
        new_providers = dict(profile.providers)
        new_providers[provider_id] = provider_account
        new_models = dict(profile.models)
        new_models["planner"] = model_binding
        profile = profile.model_copy(update={"providers": new_providers, "models": new_models})
    else:
        profile = TeamProfile(
            name=name,
            providers={provider_id: provider_account},
            models={"planner": model_binding},
        )

    doc.profiles[name] = profile
    if set_as_default or not doc.default_profile:
        doc.default_profile = name

    save_profiles_document(doc)
    logger.info("Created provider profile '%s' with provider '%s'", name, provider_id)
    return profile


def delete_profile(name: str) -> None:
    """Delete a provider profile and its associated secrets."""
    doc = load_profiles_document()
    if name not in doc.profiles:
        raise ValueError(f"Profile '{name}' not found")

    profile = doc.profiles[name]
    store = get_secret_store()
    for provider in profile.providers.values():
        if provider.secret_ref:
            with contextlib.suppress(Exception):
                store.delete(provider.secret_ref)

    del doc.profiles[name]
    if doc.default_profile == name:
        doc.default_profile = next(iter(doc.profiles), "default")
    save_profiles_document(doc)
    logger.info("Deleted provider profile '%s'", name)


def test_provider_connection(provider_kind: str, fields: dict[str, str]) -> dict[str, Any]:
    """Test if a provider configuration can connect successfully."""
    from agentheim_core.providers import build_provider

    from config.config import ProviderConfig

    templates = list_provider_templates(include_experimental=True)
    template_map = {t["kind"]: t for t in templates}
    if provider_kind not in template_map:
        return {"ok": False, "error": f"Unknown provider kind: {provider_kind}"}

    template = template_map[provider_kind]
    endpoint = fields.get("endpoint", fields.get("base_url", template.get("endpoint", "-")))
    if endpoint in ("", "-"):
        endpoint = template.get("endpoint", "-")

    api_key = fields.get("api_key", "")
    headers = {}
    if provider_kind == "aws_bedrock":
        region = fields.get("region", "us-east-1")
        headers = {"aws-region": region}

    config = ProviderConfig(
        id="test",
        provider_type=template.get("provider_type", provider_kind),
        endpoint=endpoint,
        auth_mode=template.get("auth_mode", "api_key"),
        secret_ref=None,
        timeout_seconds=30,
        headers=headers,
        metadata={"template": provider_kind},
        api_key=api_key,
    )

    try:
        provider = build_provider(config)
        # Try a simple models list or health check if available
        if hasattr(provider, "list_models"):
            models = provider.list_models()
            return {"ok": True, "models_found": len(models)}
        return {"ok": True, "message": "Provider initialized successfully"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
