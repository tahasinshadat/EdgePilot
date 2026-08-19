"""Anthropic Claude provider implementation."""

from __future__ import annotations

import os
from typing import Dict, List, Any

import httpx

from .base import BaseLLM, ChatMessage, LLMResponse, ProviderConfig, ToolCall

DEFAULT_ENDPOINT = "https://api.anthropic.com/v1/messages"
MAX_OUTPUT_TOKENS = 1024

# ── Prompt caching ──────────────────────────────────────────────────────
# The tool schemas are ~22,000 characters and byte-identical on every single
# request — measured at 86% of a whole request. Without caching we pay full
# input price to re-send them each time; a reliability sweep spent roughly
# 6.4M of its 7.4M input tokens on re-sends, and the product re-sends them on
# every chat message a user types.
#
# Anthropic caches by prefix, in the order tools -> system -> messages, and a
# `cache_control` marker caches everything up to and including the block it
# sits on. One marker on the last tool therefore covers all tools; one on the
# system prompt extends the cached prefix through it. Cache writes cost 1.25x
# and reads 0.1x, so this pays for itself from the second request onward.
#
# Set EDGEPILOT_PROMPT_CACHE=0 to disable, e.g. to measure the difference.
_CACHE_CONTROL = {"type": "ephemeral"}


def _caching_enabled() -> bool:
    return os.getenv("EDGEPILOT_PROMPT_CACHE", "1").strip().lower() not in {
        "0", "false", "no", "off",
    }


def _with_cache_breakpoint(schemas: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Mark the last tool so the whole tool block is cached.

    Copies rather than mutating: ``self.tool_schemas`` is shared with the
    caller, and stamping it in place would leak a breakpoint into the Gemini
    formatter's output too.
    """
    if not schemas or not _caching_enabled():
        return schemas

    marked = [dict(schema) for schema in schemas]
    marked[-1]["cache_control"] = dict(_CACHE_CONTROL)
    return marked


def _cacheable_system(text: str):
    """Return the system prompt as a cached block, or plain text if disabled."""
    if not _caching_enabled():
        return text

    return [{"type": "text", "text": text, "cache_control": dict(_CACHE_CONTROL)}]


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
        self.tools_enabled = False
        self.tool_schemas: List[Dict[str, Any]] = []
        if not self.config.api_key:
            raise ValueError("Claude provider requires ANTHROPIC_API_KEY")

    @classmethod
    def describe(cls) -> dict:
        return {
            "name": "Claude",
            "id": "claude",
            "model": "claude-3-5-sonnet-20240620",
            "supports_tools": True,
        }

    def enable_tools(self, tool_schemas: List[Dict[str, Any]]) -> None:
        """Enable function calling with provider-formatted schemas."""
        self.tools_enabled = True
        self.tool_schemas = tool_schemas

    def generate_stream(
            self,
            messages: List[ChatMessage],
    ):
        """Use the non-streaming Claude request through the streaming UI."""
        yield self.generate(messages)

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
        if self.tools_enabled and self.tool_schemas:
            payload["tools"] = _with_cache_breakpoint(self.tool_schemas)
            payload["tool_choice"] = {"type": "auto"}
        if system_prompts:
            payload["system"] = _cacheable_system("\n\n".join(system_prompts))

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
        tool_calls: List[ToolCall] = []
        for block in data.get("content", []):
            if block.get("type") == "text" and block.get("text"):
                text_blocks.append(block["text"])
            elif block.get("type") == "tool_use":
                tool_calls.append(
                    ToolCall(
                        name=block.get("name", ""),
                        arguments=block.get("input") or {},
                        id=block.get("id"),
                    )
                )
        reply_text = "\n\n".join(text_blocks).strip()
        if not reply_text and not tool_calls:
            reply_text = "Claude did not return any content."

        usage = data.get("usage", {})
        # With prompt caching, cached tokens are reported *separately* and are
        # not included in input_tokens. Summing them keeps prompt_tokens the
        # true size of the prompt — otherwise enabling the cache would look
        # like the prompt had shrunk by 86%, and every cost figure derived from
        # it would be wrong in the flattering direction.
        cache_read = int(usage.get("cache_read_input_tokens", 0) or 0)
        cache_written = int(usage.get("cache_creation_input_tokens", 0) or 0)
        uncached = int(usage.get("input_tokens", 0) or 0)

        response = LLMResponse(
            text=reply_text,
            prompt_tokens=uncached + cache_read + cache_written,
            response_tokens=int(usage.get("output_tokens", 0) or 0),
            tool_calls=tool_calls,
            finish_reason=data.get("stop_reason"),
        )

        # Attached rather than added to LLMResponse: the dataclass is shared
        # with providers that have no cache, and only Claude reports these.
        response.cache_read_tokens = cache_read
        response.cache_write_tokens = cache_written
        response.uncached_tokens = uncached

        return response
