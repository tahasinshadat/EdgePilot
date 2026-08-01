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
            "model": "gemini-3.1-flash-lite",
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
            function_declarations = []

            for schema in self.tool_schemas:
                function_declarations.append(
                    {
                        "name": schema["name"],
                        "description": schema.get("description", ""),
                        "parameters": schema.get(
                            "parameters",
                            {
                                "type": "OBJECT",
                                "properties": {},
                            },
                        ),
                    }
                )

            payload["tools"] = [
                {
                    "functionDeclarations": function_declarations,
                }
            ]

        response = requests.post(
            endpoint,
            headers=headers,
            json=payload,
            timeout=self.config.timeout_sec,
        )

        if not response.ok:
            raise RuntimeError(
                f"Gemini API error {response.status_code}: {response.text}"
            )

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


    def generate_stream(self, messages: Iterable[ChatMessage]):
        endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{self.config.model}:streamGenerateContent?alt=sse&key={self.config.api_key}"
        headers = {"Content-Type": "application/json"}
        
        system_instruction = None
        contents = []
        
        for msg in messages:
            if msg.get("role") == "system":
                system_instruction = {"parts": [{"text": msg["content"]}]}
            elif msg.get("role") == "assistant":
                contents.append({"role": "model", "parts": [{"text": msg["content"]}]})
            else:
                contents.append({"role": "user", "parts": [{"text": msg["content"]}]})
                
        payload = {"contents": contents}
        if system_instruction:
            payload["systemInstruction"] = system_instruction
            
        if getattr(self, "tools_enabled", False) and getattr(self, "tool_schemas", []):
            function_declarations = []
            for schema in self.tool_schemas:
                gemini_tool = {
                    "name": schema["name"],
                    "description": schema["description"],
                    "parameters": schema["parameters"],
                }
                function_declarations.append(gemini_tool)

            payload["tools"] = [{"functionDeclarations": function_declarations}]

        import requests, json
        response = requests.post(endpoint, headers=headers, json=payload, timeout=self.config.timeout_sec, stream=True)
        
        if not response.ok:
            raise RuntimeError(f"Gemini API error {response.status_code}: {response.text}")
            
        full_text = ""
        tool_calls = []
        prompt_tokens = 0
        response_tokens = 0
        finish_reason = None
        
        for line in response.iter_lines():
            if line:
                line_str = line.decode('utf-8').strip()
                if line_str.startswith("data: "):
                    data_str = line_str[6:]
                    if data_str == "[DONE]":
                        continue
                    try:
                        data = json.loads(data_str)
                        candidates = data.get("candidates", [])
                        if candidates:
                            candidate = candidates[0]
                            if candidate.get("finishReason"):
                                finish_reason = candidate.get("finishReason")
                                
                            parts = candidate.get("content", {}).get("parts", [])
                            for part in parts:
                                if "text" in part:
                                    chunk = part["text"]
                                    full_text += chunk
                                    yield chunk
                                elif "functionCall" in part:
                                    func_call = part["functionCall"]
                                    # Streaming function calls can sometimes be chunks, but Gemini usually emits them in one block.
                                    tool_calls.append(ToolCall(name=func_call["name"], arguments=func_call.get("args", {})))
                        
                        usage = data.get("usageMetadata", {})
                        if usage:
                            if usage.get("promptTokenCount"):
                                prompt_tokens = int(usage.get("promptTokenCount"))
                            if usage.get("candidatesTokenCount"):
                                response_tokens = int(usage.get("candidatesTokenCount"))
                    except Exception:
                        pass
                        
        if not full_text and not tool_calls:
            full_text = "Gemini did not return any content."
            
        yield LLMResponse(
            text=full_text.strip(),
            prompt_tokens=prompt_tokens,
            response_tokens=response_tokens,
            tool_calls=tool_calls,
            finish_reason=finish_reason
        )
