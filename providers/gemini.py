"""Gemini provider implementation with function calling support."""

from __future__ import annotations

import json
import requests

from .base import BaseLLM, ChatMessage, LLMResponse, ProviderConfig, ToolCall

DEFAULT_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta"


class GeminiProvider(BaseLLM):
    """Calls Gemini via REST API with function calling support."""

    def __init__(self, config: ProviderConfig) -> None:
        self.config = config
        self.tools_enabled = False
        self.tool_schemas = []
        if not self.config.api_key:
            raise ValueError("Gemini provider requires GEMINI_API_KEY")

    @classmethod
    def describe(cls) -> dict:
        return {
            "name": "Gemini",
            "id": "gemini",
            "model": "gemini-2.0-flash",
            "supports_tools": True,  # Changed to True
        }

    def enable_tools(self, tool_schemas: list) -> None:
        """Enable function calling with the provided tool schemas."""
        self.tools_enabled = True
        self.tool_schemas = tool_schemas

    def generate(self, messages: list[ChatMessage]) -> LLMResponse:
        prepared = self.format_messages(messages)
        endpoint = f"{self.config.base_url or DEFAULT_ENDPOINT}/models/{self.config.model}:generateContent"
        headers = {
            "Content-Type": "application/json",
            "X-goog-api-key": self.config.api_key,
        }
        
        # Convert messages to Gemini format
        contents = []
        for message in prepared:
            role = "user" if message["role"] == "user" else "model"
            if message["role"] == "system":
                role = "user"
            contents.append({"role": role, "parts": [{"text": message["content"]}]})

        # Build payload
        payload = {"contents": contents}
        
        # Add tools if enabled
        if self.tools_enabled and self.tool_schemas:
            # Convert tool schemas to Gemini function calling format
            tools = []
            for schema in self.tool_schemas:
                function_declaration = {
                    "name": schema["name"],
                    "description": schema["description"],
                    "parameters": schema["parameters"],
                }
                tools.append({"functionDeclarations": [function_declaration]})
            
            payload["tools"] = tools

        response = requests.post(endpoint, headers=headers, json=payload, timeout=self.config.timeout_sec)
        response.raise_for_status()
        data = response.json()
        
        # Parse response
        candidates = data.get("candidates", [])
        text = ""
        tool_calls = []
        finish_reason = None
        
        if candidates:
            candidate = candidates[0]
            finish_reason = candidate.get("finishReason")
            content = candidate.get("content", {})
            parts = content.get("parts", [])
            
            for part in parts:
                # Check for text content
                if "text" in part:
                    text = part["text"].strip()
                
                # Check for function call
                elif "functionCall" in part:
                    func_call = part["functionCall"]
                    tool_calls.append(ToolCall(
                        name=func_call["name"],
                        arguments=func_call.get("args", {}),
                    ))
        
        usage = data.get("usageMetadata", {})
        prompt_tokens = int(usage.get("promptTokenCount", 0) or 0)
        response_tokens = int(usage.get("candidatesTokenCount", 0) or 0)
        
        if not text and not tool_calls:
            text = "Gemini did not return any content."
        
        return LLMResponse(
            text=text,
            prompt_tokens=prompt_tokens,
            response_tokens=response_tokens,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
        )
