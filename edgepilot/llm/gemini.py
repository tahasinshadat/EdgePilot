# edgepilot/llm/gemini.py
from __future__ import annotations

from typing import Optional
from .provider import LLMProvider, LLMResult
from ..config import get_config
from ..usage import record_usage


class GeminiProvider(LLMProvider):
    """Thin wrapper; works if `google-generativeai` package and API key are available."""
    def __init__(self):
        self.cfg = get_config()
        try:
            import google.generativeai as genai  # type: ignore
            if self.cfg.llm.api_key:
                genai.configure(api_key=self.cfg.llm.api_key)
            self._model = genai.GenerativeModel(self.cfg.llm.model or "gemini-2.0-flash")  # type: ignore[attr-defined]
            self._err = None
        except Exception as e:
            self._model = None
            self._err = e

    async def complete(self, prompt: str, system: str | None = None) -> LLMResult:
        if not self._model:
            raise RuntimeError(f"Gemini provider not available: {self._err}")
        # Synchronous SDK; wrap in thread
        import asyncio
        def _call():
            return self._model.generate_content((system + "\n\n" if system else "") + prompt)  # type: ignore[operator]
        resp = await asyncio.to_thread(_call)
        text = getattr(resp, "text", "")
        record_usage("gemini", self.cfg.llm.model, len(prompt), len(text))
        return LLMResult(text=text, raw=resp)  # type: ignore[arg-type]
