from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from config.config import AgentModelConfig, ModelRole
from core.errors import ConfigError, ProviderError
from providers.base import ModelRequest
from providers.oci_genai import OCIGenAIProvider


def _fake_oci_module(*, chat_side_effect: Exception | None = None):
    state = {"chat_side_effect": chat_side_effect}

    class ConfigFileNotFound(Exception):
        pass

    class InvalidConfig(Exception):
        pass

    class InvalidKeyFilePath(Exception):
        pass

    class ServiceError(Exception):
        def __init__(self, status: int | None = None, message: str = "", code: str = "") -> None:
            super().__init__(message)
            self.status = status
            self.message = message
            self.code = code

    class ClientError(ServiceError):
        pass

    class TextContent:
        TYPE_TEXT = "text"

        def __init__(self, type: str, text: str) -> None:
            self.type = type
            self.text = text

    class SystemMessage:
        ROLE_SYSTEM = "system"

        def __init__(self, role: str, content: list[TextContent]) -> None:
            self.role = role
            self.content = content

    class UserMessage:
        ROLE_USER = "user"

        def __init__(self, role: str, content: list[TextContent]) -> None:
            self.role = role
            self.content = content

    class AssistantMessage:
        ROLE_ASSISTANT = "assistant"

        def __init__(self, role: str, content: list[TextContent]) -> None:
            self.role = role
            self.content = content

    class GenericChatRequest:
        API_FORMAT_GENERIC = "generic"

        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class OnDemandServingMode:
        SERVING_TYPE_ON_DEMAND = "on_demand"

        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class ChatDetails:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class GenerativeAiInferenceClient:
        def __init__(self, config):
            self.config = config

        def chat(self, details):
            if state["chat_side_effect"] is not None:
                raise state["chat_side_effect"]
            message = SimpleNamespace(content=[SimpleNamespace(text="ok")])
            choice = SimpleNamespace(message=message, finish_reason="stop")
            usage = SimpleNamespace(input_tokens=12, output_tokens=7)
            chat_response = SimpleNamespace(choices=[choice], usage=usage)
            return SimpleNamespace(data=SimpleNamespace(chat_response=chat_response))

    config_module = SimpleNamespace(
        from_file=lambda file_location=None, profile_name="DEFAULT": {
            "region": "eu-frankfurt-1",
            "compartment_id": "ocid1.compartment.oc1..example",
            "file_location": file_location,
            "profile_name": profile_name,
        },
        ConfigFileNotFound=ConfigFileNotFound,
        InvalidConfig=InvalidConfig,
        InvalidKeyFilePath=InvalidKeyFilePath,
    )

    module = SimpleNamespace(
        config=config_module,
        exceptions=SimpleNamespace(ServiceError=ServiceError, ClientError=ClientError),
        generative_ai_inference=SimpleNamespace(
            GenerativeAiInferenceClient=GenerativeAiInferenceClient,
            models=SimpleNamespace(
                TextContent=TextContent,
                SystemMessage=SystemMessage,
                UserMessage=UserMessage,
                AssistantMessage=AssistantMessage,
                GenericChatRequest=GenericChatRequest,
                OnDemandServingMode=OnDemandServingMode,
                ChatDetails=ChatDetails,
            ),
        ),
    )
    module._state = state
    return module


def _config() -> AgentModelConfig:
    return AgentModelConfig(
        role=ModelRole.PLANNER,
        provider="oci",
        provider_type="oci_genai",
        endpoint="-",
        api_key="-",
        auth_mode="oci_config",
        model="cohere-command",
        timeout_seconds=30,
        headers={},
        metadata={
            "oci_config_path": "~/.oci/config",
            "oci_profile": "DEFAULT",
            "compartment_id": "ocid1.compartment.oc1..explicit",
        },
    )


def test_oci_provider_invokes_first_party_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("providers.oci_genai.importlib.util.find_spec", lambda _name: object())
    monkeypatch.setitem(sys.modules, "oci", _fake_oci_module())

    provider = OCIGenAIProvider(_config())
    response = provider.invoke(
        ModelRequest(
            role=ModelRole.PLANNER,
            system_prompt="You are helpful.",
            user_prompt="Say ok",
            temperature=0.0,
            max_output_tokens=10,
        )
    )

    assert response.provider == "oci"
    assert response.content == "ok"
    assert response.raw == {"input_tokens": 12, "output_tokens": 7, "finish_reason": "stop"}


def test_oci_provider_maps_service_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_oci = _fake_oci_module()
    fake_oci._state["chat_side_effect"] = fake_oci.exceptions.ServiceError(
        status=403,
        message="Not authorized",
        code="NotAuthorized",
    )
    monkeypatch.setattr("providers.oci_genai.importlib.util.find_spec", lambda _name: object())
    monkeypatch.setitem(sys.modules, "oci", fake_oci)

    provider = OCIGenAIProvider(_config())

    with pytest.raises(ProviderError, match="OCI access denied"):
        provider.invoke(
            ModelRequest(
                role=ModelRole.PLANNER,
                system_prompt="You are helpful.",
                user_prompt="Say ok",
            )
        )


def test_oci_provider_requires_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("providers.oci_genai.importlib.util.find_spec", lambda _name: None)

    with pytest.raises(ConfigError, match="OCI SDK not installed"):
        OCIGenAIProvider(_config())
