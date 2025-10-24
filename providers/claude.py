"""Anthropic Claude provider implementation."""

from __future__ import annotations

import os
from typing import Dict, List

import httpx

from .base import BaseLLM, ChatMessage, LLMResponse, ProviderConfig

DEFAULT_ENDPOINT = "https://api.anthropic.com/v1/messages"
MAX_OUTPUT_TOKENS = 1024


def _anthropic_headers(api_key: str) -> Dict[str, str]:
    version = os.getenv("ANTHROPIC_VERSION", "2023-06-01")
    headers = {
        "x-api-key": api_key,
        "anthropic-version": version,
        "content-type": "application/json",
    }
    beta = os.getenv("ANTHROPIC_BETA")
    if beta:
        headers["anthropic-beta"] = beta
    return headers


class ClaudeProvider(BaseLLM):
    """Invoke Anthropic Claude models via Messages API."""

    def __init__(self, config: ProviderConfig) -> None:
        self.config = config
        if not self.config.api_key:
            raise ValueError("Claude provider requires ANTHROPIC_API_KEY")

    @classmethod
    def describe(cls) -> dict:
        return {
            "name": "Claude",
            "id": "claude",
            "model": "claude-3-5-haiku-20241022",
            "supports_tools": True,
        }

    def generate(self, messages: List[ChatMessage]) -> LLMResponse:
        prepared = self.format_messages(messages)
        system_prompts: List[str] = []
        anthropic_messages = []

        for msg in prepared:
            role = msg.get("role")
            content = msg.get("content", "")
            if not content:
                continue
            if role == "system":
                system_prompts.append(content)
                continue
            anthropic_messages.append(
                {
                    "role": "assistant" if role == "assistant" else "user",
                    "content": [{"type": "text", "text": content}],
                }
            )

        if not anthropic_messages:
            raise ValueError("Claude requires at least one user message.")

        endpoint = self.config.base_url or DEFAULT_ENDPOINT
        payload: Dict[str, object] = {
            "model": self.config.model or self.describe()["model"],
            "messages": anthropic_messages,
            "max_tokens": MAX_OUTPUT_TOKENS,
        }
        if system_prompts:
            payload["system"] = "\n\n".join(system_prompts)

        headers = _anthropic_headers(self.config.api_key)

        with httpx.Client(timeout=self.config.timeout_sec) as client:
            response = client.post(endpoint, headers=headers, json=payload)

        if response.status_code == 404:
            raise RuntimeError(
                "Claude API returned 404. Check model access and the endpoint. "
                f"Request model: {payload['model']}. Body: {response.text}"
            )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(f"Claude API error {response.status_code}: {response.text}") from exc

        data = response.json()

        text_blocks = []
        for block in data.get("content", []):
            if block.get("type") == "text" and block.get("text"):
                text_blocks.append(block["text"])
        reply = "\n\n".join(text_blocks).strip() or "Claude did not return any content."

        usage = data.get("usage", {})
        prompt_tokens = int(usage.get("input_tokens", 0) or 0)
        response_tokens = int(usage.get("output_tokens", 0) or 0)

        return LLMResponse(text=reply, prompt_tokens=prompt_tokens, response_tokens=response_tokens)
