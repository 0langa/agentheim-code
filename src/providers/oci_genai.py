from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from typing import Any, cast

from config.config import AgentModelConfig
from core.errors import ConfigError, ProviderError
from providers.base import ModelProvider, ModelRequest, ModelResponse


def _require_oci_sdk() -> Any:
    spec = importlib.util.find_spec("oci")
    if spec is None:
        raise ConfigError(
            "OCI SDK not installed. Install with: pip install agentheim-code[cloud-oci]"
        )

    import oci

    if not hasattr(oci, "config"):
        raise ConfigError(
            "OCI SDK import is incomplete or shadowed. Reinstall the official oci package."
        )
    return oci


def _load_oci_config(profile: str, config_file: Path | None) -> dict[str, Any]:
    oci = _require_oci_sdk()
    try:
        if config_file is not None:
            return cast(
                dict[str, Any],
                oci.config.from_file(
                    file_location=str(config_file),
                    profile_name=profile,
                ),
            )
        return cast(dict[str, Any], oci.config.from_file(profile_name=profile))
    except oci.config.ConfigFileNotFound as exc:
        raise ConfigError(f"OCI config file not found: {exc}") from exc
    except (oci.config.InvalidConfig, oci.config.InvalidKeyFilePath) as exc:
        raise ConfigError(f"OCI config invalid: {exc}") from exc
    except Exception as exc:
        raise ConfigError(f"Failed to load OCI config: {exc}") from exc


def _resolve_compartment_id(config_value: str | None, oci_config_dict: dict[str, Any]) -> str:
    if config_value:
        return config_value

    env_id = os.getenv("OCI_COMPARTMENT_ID", "")
    if env_id:
        return env_id

    file_id = str(oci_config_dict.get("compartment_id", ""))
    if file_id:
        return file_id

    raise ConfigError(
        "OCI compartment_id required. Set metadata.compartment_id, OCI_COMPARTMENT_ID, "
        "or compartment_id in the OCI config file."
    )


def _resolve_model_id(model_id: str) -> str:
    if model_id and model_id != "dry_run":
        return model_id
    raise ConfigError("OCI GenAI provider requires a real model id.")


def _build_oci_messages(oci: Any, request: ModelRequest) -> list[Any]:
    messages: list[Any] = []
    models = oci.generative_ai_inference.models
    if request.system_prompt:
        messages.append(
            models.SystemMessage(
                role=models.SystemMessage.ROLE_SYSTEM,
                content=[
                    models.TextContent(
                        type=models.TextContent.TYPE_TEXT, text=request.system_prompt
                    )
                ],
            )
        )

    for message in [{"role": "user", "content": request.user_prompt}]:
        role = str(message.get("role", "user"))
        content = str(message.get("content", ""))
        content_blocks = [models.TextContent(type=models.TextContent.TYPE_TEXT, text=content)]
        if role == "assistant":
            messages.append(
                models.AssistantMessage(
                    role=models.AssistantMessage.ROLE_ASSISTANT,
                    content=content_blocks,
                )
            )
        else:
            messages.append(
                models.UserMessage(
                    role=models.UserMessage.ROLE_USER,
                    content=content_blocks,
                )
            )
    return messages


def _extract_chat_response(response_data: Any) -> tuple[str, str, int, int]:
    content = ""
    finish_reason = ""
    input_tokens = 0
    output_tokens = 0
    try:
        chat_response = response_data.chat_response
        if chat_response and chat_response.choices:
            choice = chat_response.choices[0]
            if choice.message:
                raw_content = choice.message.content or ""
                if isinstance(raw_content, list):
                    content = "".join(str(getattr(item, "text", "") or "") for item in raw_content)
                else:
                    content = str(raw_content)
            finish_reason = choice.finish_reason or ""
        if chat_response and chat_response.usage:
            input_tokens = chat_response.usage.input_tokens or 0
            output_tokens = chat_response.usage.output_tokens or 0
    except Exception:
        pass
    return content, finish_reason, input_tokens, output_tokens


def _raise_from_oci_error(exc: Any) -> None:
    status = getattr(exc, "status", None)
    message = getattr(exc, "message", str(exc)) or str(exc)
    code = getattr(exc, "code", "")
    lowered = f"{message} {code}".lower()

    if status in (401, 404):
        raise ProviderError(f"OCI auth failed: {message}", http_status=status) from exc
    if status == 403 or "notauthorized" in lowered or "not authorized" in lowered:
        raise ProviderError(f"OCI access denied: {message}", http_status=status) from exc
    if status == 400 and "quota" in lowered:
        raise ProviderError(f"OCI quota exceeded: {message}", http_status=status) from exc
    if "model" in lowered and ("not found" in lowered or "invalid" in lowered):
        raise ProviderError(
            f"OCI model access denied or invalid: {message}",
            http_status=status,
        ) from exc
    if "compartment" in lowered and ("not found" in lowered or "invalid" in lowered):
        raise ProviderError(
            f"OCI compartment invalid or inaccessible: {message}",
            http_status=status,
        ) from exc
    if "region" in lowered and ("invalid" in lowered or "not found" in lowered):
        raise ProviderError(f"OCI region invalid: {message}", http_status=status) from exc
    raise ProviderError(f"OCI service error ({status}): {message}", http_status=status) from exc


class OCIGenAIProvider(ModelProvider):
    def __init__(self, config: AgentModelConfig) -> None:
        super().__init__(config)
        self.model_id = _resolve_model_id(config.model)
        config_path = str(config.metadata.get("oci_config_path", "") or "").strip()
        self.profile = str(config.metadata.get("oci_profile", "DEFAULT") or "DEFAULT")
        self.config_file = Path(config_path).expanduser() if config_path else None
        self._oci_config = _load_oci_config(self.profile, self.config_file)
        self.compartment_id = _resolve_compartment_id(
            str(config.metadata.get("compartment_id", "") or ""),
            self._oci_config,
        )

    def invoke(self, request: ModelRequest) -> ModelResponse:
        self.validate_request(request)
        oci = _require_oci_sdk()
        client = oci.generative_ai_inference.GenerativeAiInferenceClient(config=self._oci_config)
        models = oci.generative_ai_inference.models

        chat_request = models.GenericChatRequest(
            api_format=models.GenericChatRequest.API_FORMAT_GENERIC,
            messages=_build_oci_messages(oci, request),
            temperature=request.temperature,
            max_tokens=request.max_output_tokens or 4096,
        )
        serving_mode = models.OnDemandServingMode(
            serving_type=models.OnDemandServingMode.SERVING_TYPE_ON_DEMAND,
            model_id=self.model_id,
        )
        chat_details = models.ChatDetails(
            compartment_id=self.compartment_id,
            serving_mode=serving_mode,
            chat_request=chat_request,
        )

        try:
            response = client.chat(chat_details)
        except (oci.exceptions.ServiceError, oci.exceptions.ClientError) as exc:
            _raise_from_oci_error(exc)
        except Exception as exc:
            raise ProviderError(f"OCI chat request failed: {exc}") from exc

        content, finish_reason, input_tokens, output_tokens = _extract_chat_response(response.data)
        return ModelResponse(
            role=request.role,
            model=self.config.model,
            provider=self.config.provider,
            content=content,
            raw={
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "finish_reason": finish_reason,
            },
        )
