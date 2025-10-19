"""Provider registry for EdgePilot."""

from __future__ import annotations

from typing import Dict, Type

from .base import BaseLLM, ProviderConfig, LLMResponse  # noqa: F401
from .gemini import GeminiProvider  # noqa: F401
from .claude import ClaudeProvider  # noqa: F401
from .gpt import GPTProvider  # noqa: F401

_PROVIDERS: Dict[str, Type[BaseLLM]] = {
    "gemini": GeminiProvider,
    "claude": ClaudeProvider,
    "gpt": GPTProvider,
}


def available_providers() -> Dict[str, dict]:
    """Return provider metadata for UI discovery."""
    return {
        name: provider.describe()
        for name, provider in _PROVIDERS.items()
    }


def get_provider(name: str, config: ProviderConfig) -> BaseLLM:
    """Instantiate a provider by name."""
    key = name.lower()
    if key not in _PROVIDERS:
        raise ValueError(f"Unknown provider '{name}'")
    return _PROVIDERS[key](config)
