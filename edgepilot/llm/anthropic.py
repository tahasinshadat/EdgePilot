# edgepilot/llm/anthropic.py
from __future__ import annotations

from typing import Optional
from .provider import LLMProvider, LLMResult
from ..config import get_config
from ..usage import record_usage


class AnthropicProvider(LLMProvider):
    """Thin wrapper; works if `anthropic` package and API key are available."""
    def __init__(self):
        self.cfg = get_config()
        try:
            import anthropic  # type: ignore
        except Exception as e:
            self._err = e
            self._client = None
        else:
            self._err = None
            self._client = anthropic.Anthropic(api_key=self.cfg.llm.api_key)

    async def complete(self, prompt: str, system: str | None = None) -> LLMResult:
        if not self._client:
            raise RuntimeError(f"Anthropic provider not available: {self._err}")

        model = self.cfg.llm.model or "claude-3-5-sonnet-20240620"
        msg = await self._client.messages.create(  # type: ignore[func-returns-value]
            model=model,
            max_tokens=self.cfg.llm.max_tokens,
            temperature=self.cfg.llm.temperature,
            system=system or "",
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(block["text"] for block in msg.content if block["type"] == "text")  # type: ignore[index]
        # Use provided token counts if present
        tokens_in = getattr(msg.usage, "input_tokens", None)  # type: ignore[attr-defined]
        tokens_out = getattr(msg.usage, "output_tokens", None)  # type: ignore[attr-defined]
        record_usage("anthropic", model, len(prompt), len(text), tokens_in=tokens_in, tokens_out=tokens_out)
        return LLMResult(text=text, tokens_in=tokens_in, tokens_out=tokens_out, raw=msg)  # type: ignore[arg-type]
