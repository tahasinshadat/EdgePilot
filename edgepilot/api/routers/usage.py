# edgepilot/api/routers/usage.py
from __future__ import annotations

from fastapi import APIRouter
from ...usage import usage_stats

router = APIRouter()


@router.get("/stats")
def stats():
    return usage_stats()
