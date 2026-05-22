"""OCI Generative AI provider with lazy imports and fail-closed gates."""

from __future__ import annotations

import importlib.util
import logging
import os
from pathlib import Path
from typing import Any

from agentheim_code.vendor.aictx.errors import ConfigError
from agentheim_code.vendor.aictx.llm.base import ChatRequest, ChatResponse, ModelProvider

logger = logging.getLogger("aictx.llm.oci_genai")


def _require_oci_sdk() -> Any:
    """Lazy OCI SDK import; raise ConfigError if absent."""
    spec = importlib.util.find_spec("oci")
    if spec is None:
        raise ConfigError("OCI SDK not installed. Install with: pip install 'aictx[oci]'")
    import oci

    # Guard against namespace collisions (e.g. vendor package shadowing).
    if not hasattr(oci, "config"):
        raise ConfigError("OCI SDK not installed. Install with: pip install 'aictx[oci]'")
    return oci


def _load_oci_config(profile: str, config_file: Path | None) -> dict[str, Any]:
    """Load OCI SDK config dict from file or default location."""
    oci = _require_oci_sdk()
    try:
        if config_file:
            result: dict[str, Any] = oci.config.from_file(
                file_location=str(config_file),
                profile_name=profile,
            )
        else:
            result = oci.config.from_file(profile_name=profile)
        return result
    except oci.config.ConfigFileNotFound as exc:
        raise ConfigError(f"OCI config file not found: {exc}") from exc
    except (oci.config.InvalidConfig, oci.config.InvalidKeyFilePath) as exc:
        raise ConfigError(f"OCI config invalid: {exc}") from exc
    except Exception as exc:
        raise ConfigError(f"Failed to load OCI config: {exc}") from exc


def _resolve_compartment_id(config_value: str | None, oci_config_dict: dict[str, Any]) -> str:
    """Resolve compartment_id from config value, env var, or OCI config file."""
    if config_value:
        return config_value
    env_id = os.getenv("OCI_COMPARTMENT_ID", "")
    if env_id:
        return env_id
    file_id = str(oci_config_dict.get("compartment_id", ""))
    if file_id:
        return file_id
    raise ConfigError(
        "OCI compartment_id required. "
        "Set in config.toml llm.compartment_id, ~/.oci/config compartment_id, or OCI_COMPARTMENT_ID env var."
    )


def _resolve_model_id(config_value: str) -> str:
    """Validate model_id is present."""
    if config_value and config_value != "dry_run":
        return config_value
    raise ConfigError(
        "OCI GenAI provider requires llm.model (OCID or model name). "
        "Example: config.toml -> [llm] model = 'cohere.command-r-plus'"
    )


class OCIGenAIProvider(ModelProvider):
    """Minimal OCI GenAI provider. Lazy imports. Fail-closed. No prompts logged unless debug."""

    def __init__(
        self,
        compartment_id: str | None,
        model_id: str,
        profile: str = "DEFAULT",
        config_file: Path | None = None,
        temperature: float = 0.0,
    ) -> None:
        self.model_id = _resolve_model_id(model_id)
        self.profile = profile
        self.config_file = config_file
        self.temperature = temperature

        oci_config_dict = _load_oci_config(profile, config_file)
        self.compartment_id = _resolve_compartment_id(compartment_id, oci_config_dict)
        self._oci_config = oci_config_dict

        logger.info(
            "OCI provider init. profile=%s model=%s compartment=%s",
            profile,
            self.model_id,
            _mask_id(self.compartment_id),
        )

    def metadata(self) -> dict[str, str]:
        """Return safe provider metadata without prompt content."""
        return {
            "provider": "oci_genai",
            "model": self.model_id,
            "profile": self.profile,
            "network": "true",
        }

    def chat(self, request: ChatRequest) -> ChatResponse:
        """Send a chat request via OCI Generative AI and return normalized response."""
        oci = _require_oci_sdk()
        client = oci.generative_ai_inference.GenerativeAiInferenceClient(config=self._oci_config)

        messages = _build_oci_messages(oci, request)
        chat_request = oci.generative_ai_inference.models.GenericChatRequest(
            api_format=oci.generative_ai_inference.models.GenericChatRequest.API_FORMAT_GENERIC,
            messages=messages,
            temperature=self.temperature,
            max_tokens=request.max_output_tokens,
        )
        serving_mode = oci.generative_ai_inference.models.OnDemandServingMode(
            serving_type=oci.generative_ai_inference.models.OnDemandServingMode.SERVING_TYPE_ON_DEMAND,
            model_id=self.model_id
        )
        chat_details = oci.generative_ai_inference.models.ChatDetails(
            compartment_id=self.compartment_id,
            serving_mode=serving_mode,
            chat_request=chat_request,
        )

        logger.debug(
            "OCI chat call. run_id=%s purpose=%s model=%s",
            request.run_id,
            request.purpose,
            self.model_id,
        )

        try:
            response = client.chat(chat_details)
        except (
            oci.exceptions.ServiceError,
            oci.exceptions.ClientError,
        ) as exc:
            _raise_from_oci_error(exc)
        except Exception as exc:
            raise ConfigError(f"OCI chat request failed: {exc}") from exc

        return _extract_chat_response(oci, response.data)

    def count_tokens(self, text: str) -> int | None:
        """Return rough local estimate until OCI tokenizer is implemented."""
        return len(text) // 4


def _build_oci_messages(oci: Any, request: ChatRequest) -> list[Any]:
    """Convert ChatRequest messages to OCI SDK message objects."""
    messages: list[Any] = []
    models = oci.generative_ai_inference.models
    if request.system_prompt:
        messages.append(
            models.SystemMessage(
                role=models.SystemMessage.ROLE_SYSTEM,
                content=[models.TextContent(type=models.TextContent.TYPE_TEXT, text=request.system_prompt)],
            )
        )
    for msg in request.messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        content_blocks = [models.TextContent(type=models.TextContent.TYPE_TEXT, text=content)]
        if role == "user":
            messages.append(
                models.UserMessage(role=models.UserMessage.ROLE_USER, content=content_blocks)
            )
        elif role == "assistant":
            messages.append(
                models.AssistantMessage(role=models.AssistantMessage.ROLE_ASSISTANT, content=content_blocks)
            )
    return messages


def _extract_chat_response(oci: Any, response_data: Any) -> ChatResponse:
    """Normalize OCI chat response to ChatResponse."""
    content = ""
    finish_reason = ""
    input_tokens = 0
    output_tokens = 0
    try:
        chat_resp = response_data.chat_response
        if chat_resp and chat_resp.choices:
            choice = chat_resp.choices[0]
            if choice.message:
                raw_content = choice.message.content or ""
                if isinstance(raw_content, list):
                    content = "".join(
                        str(getattr(item, "text", "") or "")
                        for item in raw_content
                    )
                else:
                    content = str(raw_content)
            finish_reason = choice.finish_reason or ""
        if chat_resp and chat_resp.usage:
            input_tokens = chat_resp.usage.input_tokens or 0
            output_tokens = chat_resp.usage.output_tokens or 0
    except Exception:
        pass
    return ChatResponse(
        content=content,
        finish_reason=finish_reason,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


def _raise_from_oci_error(exc: Any) -> None:
    """Map OCI SDK errors to clear ConfigError messages."""
    status = getattr(exc, "status", None)
    message = getattr(exc, "message", str(exc)) or str(exc)
    code = getattr(exc, "code", "")
    lowered = (message + " " + (code or "")).lower()

    if status in (401, 404):
        raise ConfigError(f"OCI auth failed: {message}") from exc
    if status == 403 or "notauthorized" in lowered or "not authorized" in lowered:
        raise ConfigError(f"OCI access denied: {message}") from exc
    if status == 400 and "quota" in lowered:
        raise ConfigError(f"OCI quota exceeded: {message}") from exc
    if "model" in lowered and ("not found" in lowered or "invalid" in lowered):
        raise ConfigError(f"OCI model access denied or invalid: {message}") from exc
    if "compartment" in lowered and ("not found" in lowered or "invalid" in lowered):
        raise ConfigError(f"OCI compartment invalid or inaccessible: {message}") from exc
    if "region" in lowered and ("invalid" in lowered or "not found" in lowered):
        raise ConfigError(f"OCI region invalid: {message}") from exc
    raise ConfigError(f"OCI service error ({status}): {message}") from exc


def _mask_id(value: str) -> str:
    """Mask sensitive OCID-like values for logs."""
    if len(value) <= 12:
        return "***"
    return value[:6] + "..."
