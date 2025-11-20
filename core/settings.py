"""Runtime configuration helpers shared across CLI and API."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from providers.base import ProviderConfig


SYSTEM_PROMPT = (
    "You are EdgePilot, an on-prem AI copilot who understands real-time system capacity, bottlenecks, "
    "and scheduling needs for engineers. Provide succinct, actionable guidance grounded in the latest "
    "system context."
)

PROVIDER_ENV_SETTINGS = {
    "gemini": {
        "api_key": "GEMINI_API_KEY",
        "model": "GEMINI_MODEL",
        "default_model": "gemini-2.0-flash",
        "base_url": "GEMINI_BASE_URL",
    },
    "claude": {
        "api_key": "ANTHROPIC_API_KEY",
        "model": "CLAUDE_MODEL",
        "default_model": "claude-3-5-haiku-20241022",
        "base_url": "CLAUDE_BASE_URL",
    },
    "gpt": {
        "api_key": "OPENAI_API_KEY",
        "model": "GPT_MODEL",
        "default_model": "gpt-4o-mini",
        "base_url": "GPT_BASE_URL",
    },
}


def load_env() -> None:
    env_path = Path("env") / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=False)


load_env()
DEFAULT_PROVIDER = os.getenv("DEFAULT_PROVIDER", "gemini").lower()


def provider_config(name: str) -> ProviderConfig:
    key = name.lower()
    settings = PROVIDER_ENV_SETTINGS.get(key)
    if not settings:
        raise ValueError(f"Unsupported provider '{name}'")

    api_key = os.getenv(settings["api_key"], "").strip()
    model = os.getenv(settings["model"], settings["default_model"]).strip()
    base_url = os.getenv(settings["base_url"], "").strip() or None
    timeout = int(os.getenv("LLM_TIMEOUT_SEC", "60"))
    return ProviderConfig(api_key=api_key, model=model or settings["default_model"], timeout_sec=timeout, base_url=base_url)
