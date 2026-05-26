"""Shared provider/profile storage and template registry.

This module manages provider profiles, model bindings, and secret storage.
UI preferences and onboarding state are handled by src/agentheim_code/config.py.
See docs/adr/0001-config-surface-and-storage.md for the boundary.
"""

from __future__ import annotations

import base64
import contextlib
import getpass
import json
import os
import re
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal, cast

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from platformdirs import user_config_dir, user_data_dir
from pydantic import BaseModel, ConfigDict, Field, model_validator

from core.errors import ConfigError

SECRET_REF_PREFIX = "secret://"
APP_NAME = "agentheim"
PROFILE_FILE_NAME = "providers.json"
PROJECT_POINTER = Path(".ai-team") / "provider-profile.json"


class ModelRole(StrEnum):
    PLANNER = "planner"
    EXECUTOR = "executor"
    VERIFIER = "verifier"


class ModelCapability(StrEnum):
    TEXT = "text"
    JSON = "json"
    VISION = "vision"
    TOOLS = "tools"
    STREAMING = "streaming"
    EMBEDDINGS = "embeddings"
    RERANK = "rerank"


AuthMode = Literal[
    "api_key",
    "bearer",
    "x_api_key",
    "none",
    "aws_chain",
    "bedrock_api_key",
    "google_adc",
    "oci_config",
]


class ProviderConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    id: str = Field(min_length=1)
    provider_type: str = Field(min_length=1)
    endpoint: str = Field(default="-", min_length=1)
    auth_mode: AuthMode = "api_key"
    secret_ref: str | None = None
    timeout_seconds: int = Field(default=60, ge=1)
    headers: dict[str, str] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    api_key: str | None = Field(default=None, exclude=True)

    def redacted_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "provider_type": self.provider_type,
            "endpoint": self.endpoint,
            "auth_mode": self.auth_mode,
            "secret_ref": redact_secret_ref(self.secret_ref),
            "timeout_seconds": self.timeout_seconds,
            "headers": redact_mapping(self.headers),
            "metadata": redact_mapping(self.metadata),
            "api_key": redact_secret(self.api_key or ""),
        }


class ModelConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    role: ModelRole
    provider: str = Field(min_length=1)
    model_name: str = Field(min_length=1)
    display_name: str | None = None
    capabilities: list[str] = Field(default_factory=lambda: [ModelCapability.TEXT.value])

    def redacted_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "role": self.role.value,
            "provider": self.provider,
            "model_name": self.model_name,
            "display_name": self.display_name,
            "capabilities": self.capabilities,
        }


class AgentModelConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    role: ModelRole
    provider: str = Field(min_length=1)
    provider_type: str = Field(min_length=1)
    endpoint: str = Field(min_length=1)
    api_key: str = Field(default="-", min_length=1)
    auth_mode: AuthMode = "api_key"
    model: str = Field(min_length=1)
    timeout_seconds: int = Field(default=60, ge=1)
    headers: dict[str, str] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def redacted_dict(self) -> dict[str, Any]:
        return {
            "role": self.role.value,
            "provider": self.provider,
            "provider_type": self.provider_type,
            "endpoint": self.endpoint,
            "auth_mode": self.auth_mode,
            "api_key": redact_secret(self.api_key),
            "model": self.model,
            "timeout_seconds": self.timeout_seconds,
            "headers": redact_mapping(self.headers),
            "metadata": redact_mapping(self.metadata),
        }


class TeamConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    providers: dict[str, ProviderConfig]
    models: dict[str, ModelConfig]
    profile_name: str = "default"
    privacy_mode: str = "standard"

    def resolve_role(self, role: ModelRole) -> AgentModelConfig:
        by_role = [model for model in self.models.values() if model.role is role]
        if not by_role:
            raise ConfigError(f"No model binding configured for role '{role.value}'.")
        model = by_role[0]
        return self.resolve_model(model.id)

    def resolve_model(self, model_id: str) -> AgentModelConfig:
        model = self.models.get(model_id)
        if model is None:
            raise ConfigError(f"No model binding configured with id '{model_id}'.")
        provider = self.providers.get(model.provider)
        if provider is None:
            raise ConfigError(f"Model '{model.id}' references unknown provider '{model.provider}'.")
        api_key = provider.api_key or "-"
        if provider.auth_mode in {"api_key", "bearer", "x_api_key", "bedrock_api_key"}:
            if not provider.secret_ref and not provider.api_key:
                raise ConfigError(f"Provider '{provider.id}' requires a secret_ref.")
            if provider.secret_ref and not provider.api_key:
                api_key = get_secret_store().get(provider.secret_ref)
            if not api_key:
                raise ConfigError(f"Provider '{provider.id}' secret is empty.")
        return AgentModelConfig(
            role=model.role,
            provider=provider.id,
            provider_type=provider.provider_type,
            endpoint=provider.endpoint,
            api_key=api_key,
            auth_mode=provider.auth_mode,
            model=model.model_name,
            timeout_seconds=provider.timeout_seconds,
            headers=provider.headers,
            metadata={**provider.metadata, "capabilities": list(model.capabilities)},
        )

    def by_role(self) -> dict[ModelRole, AgentModelConfig]:
        seen: set[ModelRole] = set()
        result: dict[ModelRole, AgentModelConfig] = {}
        for model in self.models.values():
            if model.role not in seen:
                seen.add(model.role)
                result[model.role] = self.resolve_role(model.role)
        return result

    def dump(self, redacted: bool = True) -> dict[str, Any]:
        providers = {
            pid: (
                provider.redacted_dict() if redacted else provider.model_dump(exclude={"api_key"})
            )
            for pid, provider in self.providers.items()
        }
        models = {
            mid: (model.redacted_dict() if redacted else model.model_dump())
            for mid, model in self.models.items()
        }
        return {
            "profile_name": self.profile_name,
            "privacy_mode": self.privacy_mode,
            "providers": providers,
            "models": models,
        }


class ProviderAccount(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    endpoint: str = Field(default="-", min_length=1)
    auth_mode: AuthMode = "api_key"
    secret_ref: str | None = None
    timeout_seconds: int = Field(default=60, ge=1)
    headers: dict[str, str] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    # Optional management fields (added for provider-model-management)
    display_name: str | None = None
    notes: str | None = None
    disabled: bool = False
    last_verified_at: str | None = None
    last_verified_status: str | None = None
    last_verified_error: str | None = None
    last_model_sync_at: str | None = None


class ModelBinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    role: ModelRole
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    display_name: str | None = None
    capabilities: list[str] = Field(default_factory=lambda: [ModelCapability.TEXT.value])
    # Optional management fields (added for provider-model-management)
    source: Literal["manual", "discovered"] = "manual"
    remote_id: str | None = None
    enabled: bool = True
    is_default: bool = False
    context_window: int | None = None
    max_output_tokens: int | None = None
    supports_tools: bool | None = None
    supports_vision: bool | None = None
    supports_streaming: bool | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class TeamProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    providers: dict[str, ProviderAccount] = Field(default_factory=dict)
    models: dict[str, ModelBinding] = Field(default_factory=dict)
    privacy_mode: str = Field(default="standard")

    @model_validator(mode="after")
    def _validate_refs(self) -> TeamProfile:
        for model in self.models.values():
            if model.provider not in self.providers:
                raise ValueError(
                    f"Model '{model.id}' references unknown provider '{model.provider}'."
                )
        return self

    def to_team_config(self) -> TeamConfig:
        providers = {
            pid: ProviderConfig(
                id=provider.id,
                provider_type=provider.kind,
                endpoint=provider.endpoint,
                auth_mode=provider.auth_mode,
                secret_ref=provider.secret_ref,
                timeout_seconds=provider.timeout_seconds,
                headers=provider.headers,
                metadata=provider.metadata,
            )
            for pid, provider in self.providers.items()
        }
        models = {
            mid: ModelConfig(
                id=model.id,
                role=model.role,
                provider=model.provider,
                model_name=model.model,
                display_name=model.display_name,
                capabilities=model.capabilities,
            )
            for mid, model in self.models.items()
        }
        return TeamConfig(
            providers=providers,
            models=models,
            profile_name=self.name,
            privacy_mode=self.privacy_mode,
        )


class ProfilesDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = 1
    default_profile: str = "default"
    profiles: dict[str, TeamProfile] = Field(default_factory=dict)


def _normalize_profiles_document(document: ProfilesDocument) -> tuple[ProfilesDocument, bool]:
    changed = False
    if document.profiles and document.default_profile not in document.profiles:
        document = cast(
            ProfilesDocument,
            document.model_copy(update={"default_profile": next(iter(document.profiles))}),
        )
        changed = True
    return document, changed


class ProviderTemplate(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: str
    display_name: str
    endpoint: str
    auth_mode: AuthMode
    provider_type: str
    capabilities: list[str]
    docs_url: str
    headers: dict[str, str] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    support_state: str = "unknown"


PROVIDER_TEMPLATES: dict[str, ProviderTemplate] = {
    "openai_v1": ProviderTemplate(
        kind="openai_v1",
        display_name="OpenAI",
        endpoint="https://api.openai.com/v1",
        auth_mode="bearer",
        provider_type="openai_v1",
        capabilities=["text", "json", "vision", "tools", "streaming"],
        docs_url="https://platform.openai.com/docs/api-reference/authentication?api-mode=responses",
        support_state="beta",
    ),
    "openai_compatible": ProviderTemplate(
        kind="openai_compatible",
        display_name="OpenAI-compatible",
        endpoint="https://example.com/v1",
        auth_mode="bearer",
        provider_type="openai_compatible",
        capabilities=["text", "json", "streaming"],
        docs_url="https://platform.openai.com/docs/api-reference/authentication?api-mode=responses",
        support_state="beta",
    ),
    "azure_foundry": ProviderTemplate(
        kind="azure_foundry",
        display_name="Azure OpenAI / Foundry",
        endpoint="https://YOUR-RESOURCE.openai.azure.com",
        auth_mode="api_key",
        provider_type="azure_foundry",
        capabilities=["text", "json", "vision", "tools"],
        docs_url="https://learn.microsoft.com/en-us/azure/ai-services/openai/reference",
        support_state="beta",
    ),
    "aws_bedrock": ProviderTemplate(
        kind="aws_bedrock",
        display_name="AWS Bedrock",
        endpoint="-",
        auth_mode="aws_chain",
        provider_type="aws_bedrock",
        capabilities=["text", "json", "vision"],
        docs_url="https://docs.aws.amazon.com/bedrock/latest/userguide/api-keys-use.html",
        metadata={"region": "eu-central-1"},
        support_state="experimental",
    ),
    "oci_genai": ProviderTemplate(
        kind="oci_genai",
        display_name="OCI Generative AI",
        endpoint="-",
        auth_mode="oci_config",
        provider_type="oci_genai",
        capabilities=["text", "json"],
        docs_url="https://docs.oracle.com/en-us/iaas/tools/python/latest/api/generative_ai_inference/client/oci.generative_ai_inference.GenerativeAiInferenceClient.html",
        support_state="experimental",
    ),
    "xai_grok": ProviderTemplate(
        kind="xai_grok",
        display_name="xAI Grok",
        endpoint="https://api.x.ai/v1",
        auth_mode="bearer",
        provider_type="openai_compatible",
        capabilities=["text", "json", "vision", "tools"],
        docs_url="https://docs.x.ai/docs/grpc-reference",
        support_state="experimental",
    ),
    "gemini": ProviderTemplate(
        kind="gemini",
        display_name="Google Gemini API",
        endpoint="https://generativelanguage.googleapis.com",
        auth_mode="api_key",
        provider_type="gemini",
        capabilities=["text", "json", "vision", "tools", "streaming"],
        docs_url="https://ai.google.dev/gemini-api/docs/api-key",
        support_state="beta",
    ),
    "vertex_ai": ProviderTemplate(
        kind="vertex_ai",
        display_name="Google Vertex AI",
        endpoint="-",
        auth_mode="google_adc",
        provider_type="vertex_ai",
        capabilities=["text", "json", "vision", "tools"],
        docs_url="https://cloud.google.com/vertex-ai/docs/authentication",
        support_state="beta",
    ),
    "anthropic": ProviderTemplate(
        kind="anthropic",
        display_name="Anthropic Claude",
        endpoint="https://api.anthropic.com",
        auth_mode="x_api_key",
        provider_type="anthropic",
        capabilities=["text", "json", "vision", "tools", "streaming"],
        docs_url="https://platform.claude.com/docs/en/api/authentication/overview",
        support_state="experimental",
    ),
    "kimi_moonshot": ProviderTemplate(
        kind="kimi_moonshot",
        display_name="Kimi / Moonshot AI",
        endpoint="https://api.moonshot.ai/v1",
        auth_mode="bearer",
        provider_type="openai_compatible",
        capabilities=["text", "json", "vision", "tools"],
        docs_url="https://platform.kimi.ai/docs/api/overview",
        support_state="experimental",
    ),
    "mistral": ProviderTemplate(
        kind="mistral",
        display_name="Mistral AI",
        endpoint="https://api.mistral.ai/v1",
        auth_mode="bearer",
        provider_type="openai_compatible",
        capabilities=["text", "json", "tools", "streaming"],
        docs_url="https://docs.mistral.ai/admin/security-access/api-keys",
        support_state="experimental",
    ),
    "groq": ProviderTemplate(
        kind="groq",
        display_name="Groq",
        endpoint="https://api.groq.com/openai/v1",
        auth_mode="bearer",
        provider_type="openai_compatible",
        capabilities=["text", "json", "tools", "streaming"],
        docs_url="https://console.groq.com/docs/api-reference",
        support_state="experimental",
    ),
    "deepseek": ProviderTemplate(
        kind="deepseek",
        display_name="DeepSeek",
        endpoint="https://api.deepseek.com",
        auth_mode="bearer",
        provider_type="openai_compatible",
        capabilities=["text", "json", "tools"],
        docs_url="https://api-docs.deepseek.com/api/deepseek-api",
        support_state="experimental",
    ),
    "openrouter": ProviderTemplate(
        kind="openrouter",
        display_name="OpenRouter",
        endpoint="https://openrouter.ai/api/v1",
        auth_mode="bearer",
        provider_type="openai_compatible",
        capabilities=["text", "json", "vision", "tools"],
        docs_url="https://openrouter.ai/docs/api-keys",
        support_state="experimental",
    ),
    "together": ProviderTemplate(
        kind="together",
        display_name="Together AI",
        endpoint="https://api.together.xyz/v1",
        auth_mode="bearer",
        provider_type="openai_compatible",
        capabilities=["text", "json", "vision"],
        docs_url="https://docs.together.ai/docs/api-keys-authentication",
        support_state="experimental",
    ),
    "cohere": ProviderTemplate(
        kind="cohere",
        display_name="Cohere",
        endpoint="https://api.cohere.com",
        auth_mode="bearer",
        provider_type="cohere",
        capabilities=["text", "json", "tools", "rerank", "embeddings"],
        docs_url="https://docs.cohere.com/reference/check-api-key",
        support_state="experimental",
    ),
    "perplexity": ProviderTemplate(
        kind="perplexity",
        display_name="Perplexity",
        endpoint="https://api.perplexity.ai",
        auth_mode="bearer",
        provider_type="perplexity",
        capabilities=["text", "json", "tools"],
        docs_url="https://docs.perplexity.ai/docs/admin/api-key-management",
        support_state="experimental",
    ),
    "ollama": ProviderTemplate(
        kind="ollama",
        display_name="Ollama Local",
        endpoint="http://localhost:11434/v1",
        auth_mode="none",
        provider_type="openai_compatible",
        capabilities=["text", "json", "vision"],
        docs_url="https://docs.ollama.com/api/authentication",
        support_state="beta",
    ),
    "ollama_cloud": ProviderTemplate(
        kind="ollama_cloud",
        display_name="Ollama Cloud",
        endpoint="https://ollama.com/api",
        auth_mode="bearer",
        provider_type="ollama_cloud",
        capabilities=["text", "json"],
        docs_url="https://docs.ollama.com/api/authentication",
        support_state="experimental",
    ),
    "lm_studio": ProviderTemplate(
        kind="lm_studio",
        display_name="LM Studio",
        endpoint="http://localhost:1234/v1",
        auth_mode="none",
        provider_type="openai_compatible",
        capabilities=["text", "json", "vision"],
        docs_url="https://lmstudio.ai/docs/local-server",
        support_state="beta",
    ),
    "vllm": ProviderTemplate(
        kind="vllm",
        display_name="vLLM",
        endpoint="http://localhost:8000/v1",
        auth_mode="none",
        provider_type="openai_compatible",
        capabilities=["text", "json", "vision"],
        docs_url="https://docs.vllm.ai/en/latest/serving/openai_compatible_server.html",
        support_state="beta",
    ),
    "tgi": ProviderTemplate(
        kind="tgi",
        display_name="HuggingFace TGI",
        endpoint="http://localhost:8080/v1",
        auth_mode="none",
        provider_type="openai_compatible",
        capabilities=["text", "json"],
        docs_url="https://huggingface.co/docs/text-generation-inference/basic_tutorials/consuming_tgi",
        support_state="beta",
    ),
    "llama_cpp": ProviderTemplate(
        kind="llama_cpp",
        display_name="llama.cpp Server",
        endpoint="http://localhost:8080/v1",
        auth_mode="none",
        provider_type="openai_compatible",
        capabilities=["text", "json", "vision"],
        docs_url="https://github.com/ggerganov/llama.cpp/blob/master/examples/server/README.md",
        support_state="beta",
    ),
}


def redact_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 4:
        return "****"
    return f"{value[:2]}***{value[-2:]}"


def redact_secret_ref(value: str | None) -> str | None:
    if value is None:
        return None
    if not value.startswith(SECRET_REF_PREFIX):
        return redact_secret(value)
    return value


def redact_mapping(mapping: dict[str, Any]) -> dict[str, Any]:
    redacted: dict[str, Any] = {}
    for key, value in mapping.items():
        if re.search(r"(key|token|secret|password|credential)", key, re.IGNORECASE):
            redacted[key] = redact_secret(str(value))
        elif isinstance(value, dict):
            redacted[key] = redact_mapping(value)
        else:
            redacted[key] = value
    return redacted


def get_config_dir() -> Path:
    override = os.getenv("AGENTHEIM_CONFIG_DIR", "").strip()
    return Path(override).expanduser() if override else Path(user_config_dir(APP_NAME))


def get_data_dir() -> Path:
    override = os.getenv("AGENTHEIM_DATA_DIR", "").strip()
    return Path(override).expanduser() if override else Path(user_data_dir(APP_NAME))


def get_profiles_path() -> Path:
    return get_config_dir() / PROFILE_FILE_NAME


def load_profiles_document(path: Path | None = None) -> ProfilesDocument:
    profile_path = path or get_profiles_path()
    if not profile_path.exists():
        raise ConfigError(
            "No Agentheim Code provider profile found. Launch the app and add a provider from Settings, "
            "or place a providers.json file in the shared config directory."
        )
    try:
        raw = json.loads(profile_path.read_text(encoding="utf-8"))
        document = cast(ProfilesDocument, ProfilesDocument.model_validate(raw))
        document, changed = _normalize_profiles_document(document)
        if changed:
            save_profiles_document(document, profile_path)
        return document
    except ConfigError:
        raise
    except Exception as exc:
        raise ConfigError(f"Failed to load provider profiles from {profile_path}: {exc}") from exc


def save_profiles_document(document: ProfilesDocument, path: Path | None = None) -> Path:
    profile_path = path or get_profiles_path()
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(
        json.dumps(document.model_dump(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return profile_path


def resolve_profile_name(profile: str | None = None, project_root: Path | None = None) -> str:
    if profile:
        return profile
    pointer_root = project_root or Path.cwd()
    pointer_path = pointer_root / PROJECT_POINTER
    if pointer_path.exists():
        try:
            raw = json.loads(pointer_path.read_text(encoding="utf-8"))
            pointed = str(raw.get("profile", "")).strip()
            if pointed:
                return pointed
        except Exception as exc:
            raise ConfigError(
                f"Invalid project provider profile pointer at {pointer_path}: {exc}"
            ) from exc
    return load_profiles_document().default_profile


def write_project_profile_pointer(profile: str, project_root: Path | None = None) -> Path:
    root = project_root or Path.cwd()
    pointer_path = root / PROJECT_POINTER
    pointer_path.parent.mkdir(parents=True, exist_ok=True)
    pointer_path.write_text(json.dumps({"profile": profile}, indent=2) + "\n", encoding="utf-8")
    return pointer_path


def load_team_config(profile: str | None = None, project_root: Path | None = None) -> TeamConfig:
    document = load_profiles_document()
    profile_name = resolve_profile_name(profile=profile, project_root=project_root)
    team_profile = document.profiles.get(profile_name)
    if team_profile is None:
        available = ", ".join(sorted(document.profiles)) or "none"
        raise ConfigError(
            f"Provider profile '{profile_name}' not found. Available profiles: {available}."
        )
    return team_profile.to_team_config()


def provider_account_from_template(
    provider_id: str,
    template_id: str,
    *,
    endpoint: str | None = None,
    auth_mode: AuthMode | None = None,
    secret_ref: str | None = None,
    timeout_seconds: int | None = None,
    headers: dict[str, str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> ProviderAccount:
    template = PROVIDER_TEMPLATES.get(template_id)
    if template is None:
        supported = ", ".join(sorted(PROVIDER_TEMPLATES))
        raise ConfigError(f"Unknown provider template '{template_id}'. Supported: {supported}")
    return ProviderAccount(
        id=provider_id,
        kind=template.provider_type,
        endpoint=endpoint or template.endpoint,
        auth_mode=auth_mode or template.auth_mode,
        secret_ref=secret_ref,
        timeout_seconds=timeout_seconds or 60,
        headers={**template.headers, **(headers or {})},
        metadata={"template": template_id, **template.metadata, **(metadata or {})},
    )


class SecretStore:
    def set(self, ref: str, value: str) -> None:
        raise NotImplementedError

    def get(self, ref: str) -> str:
        raise NotImplementedError

    def delete(self, ref: str) -> None:
        raise NotImplementedError


class KeyringSecretStore(SecretStore):
    service_name = "agentheim"

    def __init__(self) -> None:
        try:
            import keyring  # type: ignore
        except Exception as exc:
            raise RuntimeError("keyring unavailable") from exc
        self._keyring = keyring

    def set(self, ref: str, value: str) -> None:
        self._keyring.set_password(self.service_name, ref, value)

    def get(self, ref: str) -> str:
        value = self._keyring.get_password(self.service_name, ref)
        if value is None:
            raise ConfigError(f"Secret '{ref}' not found in OS keychain.")
        return cast(str, value)

    def delete(self, ref: str) -> None:
        with contextlib.suppress(Exception):
            self._keyring.delete_password(self.service_name, ref)


class EncryptedFileSecretStore(SecretStore):
    def __init__(self, path: Path | None = None, passphrase: str | None = None) -> None:
        self.path = path or (get_data_dir() / "vault.enc")
        self.salt_path = self.path.with_suffix(".salt")
        self._passphrase = passphrase

    def set(self, ref: str, value: str) -> None:
        data = self._load()
        data[ref] = value
        self._save(data)

    def get(self, ref: str) -> str:
        data = self._load()
        if ref not in data:
            raise ConfigError(f"Secret '{ref}' not found in encrypted vault.")
        return str(data[ref])

    def delete(self, ref: str) -> None:
        data = self._load()
        if ref in data:
            del data[ref]
            self._save(data)

    def _pass(self) -> str:
        env_value = os.getenv("AGENTHEIM_VAULT_PASSPHRASE", "")
        if env_value:
            return env_value
        if self._passphrase:
            return self._passphrase
        return getpass.getpass("Agentheim vault passphrase: ")

    def _fernet(self) -> Fernet:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.salt_path.exists():
            salt = self.salt_path.read_bytes()
        else:
            salt = os.urandom(16)
            self.salt_path.write_bytes(salt)
        kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=390000)
        key = base64.urlsafe_b64encode(kdf.derive(self._pass().encode("utf-8")))
        return Fernet(key)

    def _load(self) -> dict[str, str]:
        if not self.path.exists():
            return {}
        try:
            plaintext = self._fernet().decrypt(self.path.read_bytes())
            raw = json.loads(plaintext.decode("utf-8"))
        except InvalidToken as exc:
            raise ConfigError("Invalid Agentheim vault passphrase.") from exc
        except Exception as exc:
            raise ConfigError(f"Failed to read Agentheim encrypted vault: {exc}") from exc
        if not isinstance(raw, dict):
            raise ConfigError("Agentheim encrypted vault is corrupt.")
        return {str(k): str(v) for k, v in raw.items()}

    def _save(self, data: dict[str, str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        token = self._fernet().encrypt(json.dumps(data, sort_keys=True).encode("utf-8"))
        self.path.write_bytes(token)


def get_secret_store(prefer_keyring: bool = True) -> SecretStore:
    import logging

    logger = logging.getLogger(__name__)
    if os.getenv("AGENTHEIM_SECRET_BACKEND", "").strip().lower() == "file":
        return EncryptedFileSecretStore()
    if prefer_keyring:
        try:
            return KeyringSecretStore()
        except Exception as exc:
            logger.warning(
                "OS keychain unavailable (%s); falling back to encrypted file vault. Set AGENTHEIM_SECRET_BACKEND=file to silence this warning.",
                exc,
            )
    return EncryptedFileSecretStore()


def make_secret_ref(provider_id: str, name: str = "api_key") -> str:
    return f"{SECRET_REF_PREFIX}provider/{provider_id}/{name}"


def list_provider_templates(include_experimental: bool = False) -> list[dict[str, Any]]:
    templates = sorted(PROVIDER_TEMPLATES.values(), key=lambda item: item.kind)
    if not include_experimental:
        templates = [t for t in templates if t.support_state != "experimental"]
    return [template.model_dump() for template in templates]
