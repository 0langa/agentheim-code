"""Dry-run model provider for local development and tests."""

from __future__ import annotations

from agentheim_code.vendor.aictx.llm.base import ChatRequest, ChatResponse, ModelProvider


class DryRunProvider(ModelProvider):
    """Provider that returns placeholder responses without network calls."""

    def metadata(self) -> dict[str, str]:
        """Return safe provider metadata."""
        return {"provider": "dry_run", "network": "false"}

    def chat(self, request: ChatRequest) -> ChatResponse:
        """Return a deterministic dry-run response."""
        prompt_text = request.system_prompt + "".join(
            message.get("content", "") for message in request.messages
        )
        return ChatResponse(
            content=f"[dry-run] purpose={request.purpose} run_id={request.run_id}",
            finish_reason="stop",
            input_tokens=len(prompt_text) // 4,
            output_tokens=10,
        )

    def count_tokens(self, text: str) -> int | None:
        """Return a rough character-based estimate."""
        return len(text) // 4
