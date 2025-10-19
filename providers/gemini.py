"""Gemini provider implementation."""

from __future__ import annotations

import requests

from .base import BaseLLM, ChatMessage, LLMResponse, ProviderConfig

DEFAULT_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta"


class GeminiProvider(BaseLLM):
    """Calls Gemini via REST API."""

    def __init__(self, config: ProviderConfig) -> None:
        self.config = config
        if not self.config.api_key:
            raise ValueError("Gemini provider requires GEMINI_API_KEY")

    @classmethod
    def describe(cls) -> dict:
        return {
            "name": "Gemini",
            "id": "gemini",
            "model": "gemini-2.0-flash",
            "supports_tools": False,
        }

    def generate(self, messages: list[ChatMessage]) -> LLMResponse:
        prepared = self.format_messages(messages)
        endpoint = f"{self.config.base_url or DEFAULT_ENDPOINT}/models/{self.config.model}:generateContent"
        headers = {
            "Content-Type": "application/json",
            "X-goog-api-key": self.config.api_key,
        }
        contents = []
        for message in prepared:
            role = "user" if message["role"] == "user" else "model"
            if message["role"] == "system":
                role = "user"
            contents.append({"role": role, "parts": [{"text": message["content"]}]})

        payload = {"contents": contents}
        response = requests.post(endpoint, headers=headers, json=payload, timeout=self.config.timeout_sec)
        response.raise_for_status()
        data = response.json()
        candidates = data.get("candidates", [])
        text = ""
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            for part in parts:
                maybe = part.get("text")
                if maybe:
                    text = maybe.strip()
                    break
        usage = data.get("usageMetadata", {})
        prompt_tokens = int(usage.get("promptTokenCount", 0) or 0)
        response_tokens = int(usage.get("candidatesTokenCount", 0) or 0)
        if not text:
            text = "Gemini did not return any content."
        return LLMResponse(text=text, prompt_tokens=prompt_tokens, response_tokens=response_tokens)
