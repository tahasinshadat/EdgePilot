# edgepilot/api/routers/runs.py
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel
from ...metrics import get_metrics_service

router = APIRouter()


class RunStartBody(BaseModel):
    user_note: str | None = None
    sampling_sec: int | None = None


@router.post("/start")
async def start_run(body: RunStartBody):
    svc = get_metrics_service()
    return svc.start_run(user_note=body.user_note or "", sampling_sec=body.sampling_sec)


class RunEndBody(BaseModel):
    run_id: str


@router.post("/end")
async def end_run(body: RunEndBody):
    svc = get_metrics_service()
    return await svc.end_run(body.run_id)
