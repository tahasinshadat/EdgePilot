# edgepilot/llm/provider.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Optional, Any, Dict


@dataclass
class LLMResult:
    text: str
    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None
    latency_ms: Optional[int] = None
    raw: Optional[Dict[str, Any]] = None


class LLMProvider(Protocol):
    async def complete(self, prompt: str, system: str | None = None) -> LLMResult: ...
