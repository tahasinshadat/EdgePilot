"""Base interfaces for LLM providers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Literal, Optional, Protocol, TypedDict


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
class ToolCall:
    """Represents a function/tool call from the LLM."""

    name: str
    arguments: Dict[str, Any]
    id: Optional[str] = None


@dataclass
class LLMResponse:
    """LLM response payload returned to the caller."""

    text: str
    prompt_tokens: int
    response_tokens: int
    tool_calls: List[ToolCall] = field(default_factory=list)
    finish_reason: Optional[str] = None

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.response_tokens

    @property
    def has_tool_calls(self) -> bool:
        """Check if the response contains tool calls."""
        return len(self.tool_calls) > 0


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
