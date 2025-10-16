# edgepilot/api/routers/metrics.py
from __future__ import annotations

from fastapi import APIRouter, Query
from ...metrics import get_metrics_service

router = APIRouter()


@router.get("/snapshot")
def snapshot(include_processes: bool = Query(False), top_n: int = Query(15, ge=1, le=100)):
    svc = get_metrics_service()
    return svc.snapshot(include_processes=include_processes, top_n=top_n)
