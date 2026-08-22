"""Provider-reported token accounting for multi-turn experiments."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class UsageTotals:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    model_requests: int = 0

    @property
    def total_tokens(self) -> int:
        """Total tokens without double-counting cached input."""

        return self.input_tokens + self.output_tokens

    def add_response(self, response: Any) -> None:
        """Accumulate usage fields reported by one provider response."""

        self.input_tokens += int(
            getattr(response, "prompt_tokens", 0) or 0
        )
        self.output_tokens += int(
            getattr(response, "response_tokens", 0) or 0
        )
        self.cache_read_tokens += int(
            getattr(response, "cache_read_tokens", 0) or 0
        )
        self.cache_write_tokens += int(
            getattr(response, "cache_write_tokens", 0) or 0
        )
        self.model_requests += 1
