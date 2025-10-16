# edgepilot/usage.py
from __future__ import annotations

from typing import Optional, Dict, Any
from sqlalchemy import select, func
from .db import session_scope, init_db
from .models import Usage
from .config import get_config


def record_usage(provider: str, model: str, prompt_len: int, response_len: int,
                 tool_calls: int = 0, tokens_in: Optional[int] = None,
                 tokens_out: Optional[int] = None, latency_ms: Optional[int] = None,
                 ok: bool = True) -> None:
    init_db()
    with session_scope() as s:
        s.add(Usage(
            provider=provider,
            model=model,
            prompt_len=prompt_len,
            response_len=response_len,
            tool_calls=tool_calls,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=latency_ms,
            ok=ok,
        ))


def usage_stats() -> Dict[str, Any]:
    init_db()
    cfg = get_config()
    with session_scope() as s:
        q = select(
            func.count(Usage.id),
            func.avg(Usage.prompt_len),
            func.sum(Usage.tool_calls),
        )
        count, avg_prompt, tool_calls = s.execute(q).one()
        return {
            "provider": cfg.llm.provider,
            "model": cfg.llm.model,
            "calls": int(count or 0),
            "avg_context_chars": int(avg_prompt or 0),
            "tool_calls": int(tool_calls or 0),
        }
