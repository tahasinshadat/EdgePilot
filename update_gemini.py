import re

with open("providers/gemini.py", "r") as f:
    code = f.read()

stream_method = """
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
            
        if hasattr(self, "_tools") and self._tools:
            function_declarations = []
            for tool in self._tools:
                props = {
                    k: {"type": v.get("type", "string"), "description": v.get("description", "")}
                    for k, v in tool["parameters"].get("properties", {}).items()
                }
                function_declarations.append(
                    {
                        "name": tool["name"],
                        "description": tool["description"],
                        "parameters": {
                            "type": "object",
                            "properties": props,
                            "required": tool["parameters"].get("required", []),
                        },
                    }
                )

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
"""

code = code + "\n" + stream_method
with open("providers/gemini.py", "w") as f:
    f.write(code)

print("Updated gemini.py")
