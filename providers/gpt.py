"""OpenAI GPT provider placeholder."""

from __future__ import annotations

from .base import BaseLLM, ChatMessage, LLMResponse, ProviderConfig


class GPTProvider(BaseLLM):  # pragma: no cover - placeholder
    """Placeholder implementation to show structure for OpenAI GPT."""

    def __init__(self, config: ProviderConfig) -> None:
        self.config = config
        if not self.config.api_key:
            raise ValueError("GPT provider requires OPENAI_API_KEY")

    @classmethod
    def describe(cls) -> dict:
        return {
            "name": "GPT",
            "id": "gpt",
            "model": "gpt-4o-mini",
            "supports_tools": True,
        }

    def generate(self, messages: list[ChatMessage]) -> LLMResponse:
        raise NotImplementedError(
            "GPT provider not yet implemented. Configure GEMINI_API_KEY or activate another provider."
        )
