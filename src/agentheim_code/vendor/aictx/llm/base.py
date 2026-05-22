"""Abstract LLM provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ChatRequest:
    """Model chat request."""

    system_prompt: str = ""
    messages: list[dict[str, str]] = field(default_factory=list)
    temperature: float = 0.0
    max_output_tokens: int = 4096
    json_schema: dict[str, Any] | None = None
    run_id: str = ""
    purpose: str = ""


@dataclass
class ChatResponse:
    """Model chat response."""

    content: str = ""
    finish_reason: str = ""
    input_tokens: int = 0
    output_tokens: int = 0


class ModelProvider(ABC):
    """Abstract base for LLM providers."""

    def metadata(self) -> dict[str, str]:
        """Return provider metadata safe for run logs."""
        return {"provider": self.__class__.__name__}

    @abstractmethod
    def chat(self, request: ChatRequest) -> ChatResponse:
        """Send a chat request and return the response."""
        ...

    @abstractmethod
    def count_tokens(self, text: str) -> int | None:
        """Return the token count for *text*, or None if unsupported."""
        ...
