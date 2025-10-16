# edgepilot/llm/ollama.py
from __future__ import annotations

import time
import httpx
from typing import Optional
from .provider import LLMProvider, LLMResult
from ..config import get_config
from ..usage import record_usage


class OllamaProvider(LLMProvider):
    def __init__(self):
        self.cfg = get_config()

    async def complete(self, prompt: str, system: str | None = None) -> LLMResult:
        url = (self.cfg.llm.base_url or "http://localhost:11434").rstrip("/") + "/api/generate"
        # Basic "system" prefixing for now
        req_prompt = (f"System: {system}\n\n" if system else "") + prompt
        body = {
            "model": self.cfg.llm.model,
            "prompt": req_prompt,
            "stream": False,
            "options": {
                "temperature": self.cfg.llm.temperature,
                "num_ctx": self.cfg.llm.num_ctx or 8192,
            },
        }
        t0 = time.time()
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post(url, json=body)
            r.raise_for_status()
            data = r.json()
        latency = int((time.time() - t0) * 1000)
        text = data.get("response", "")
        # Ollama doesn't return token counts reliably; estimate by chars
        tokens_in = len(req_prompt) // 4
        tokens_out = len(text) // 4
        record_usage("ollama", self.cfg.llm.model, prompt_len=len(req_prompt),
                     response_len=len(text), tool_calls=0, tokens_in=tokens_in, tokens_out=tokens_out, latency_ms=latency, ok=True)
        return LLMResult(text=text, tokens_in=tokens_in, tokens_out=tokens_out, latency_ms=latency, raw=data)
