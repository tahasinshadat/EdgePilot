"""Base interfaces for LLM providers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Literal, Protocol, TypedDict


MessageRole = Literal["user", "assistant", "system"]


class ChatMessage(TypedDict, total=False):
    """Simple chat message structure."""

    role: MessageRole
    content: str
    created_at: float


@dataclass
class ProviderConfig:
    """Configuration shared across providers."""

    api_key: str
    model: str
    timeout_sec: int = 60
    base_url: str | None = None


@dataclass
class LLMResponse:
    """LLM response payload returned to the caller."""

    text: str
    prompt_tokens: int
    response_tokens: int

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.response_tokens


class BaseLLM(Protocol):
    """Provider protocol."""

    config: ProviderConfig

    def __init__(self, config: ProviderConfig) -> None:
        ...

    @classmethod
    def describe(cls) -> dict:
        """Metadata used by the UI."""
        ...

    def generate(self, messages: Iterable[ChatMessage]) -> LLMResponse:
        """Generate a completion from the conversation history."""
        ...

    def format_messages(self, messages: Iterable[ChatMessage]) -> List[ChatMessage]:
        """Allow providers to tweak the message list before sending."""
        return list(messages)
