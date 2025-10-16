# edgepilot/api/routers/tasks.py
from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel
from typing import Optional
from ...scheduler import get_scheduler

router = APIRouter()


class EnqueueBody(BaseModel):
    name: str
    command: str
    requires_gpu: bool = False
    est_runtime_sec: Optional[int] = None
    priority: int = 5
    deadline_ts: Optional[str] = None
    max_cpu_pct: int = 90
    max_mem_mb: int = 0
    min_vram_mb: int = 0


@router.post("/enqueue")
def enqueue(body: EnqueueBody):
    sch = get_scheduler()
    t = sch.enqueue(**body.model_dump())
    return {"task_id": t.id, "state": t.state}


@router.get("/list")
def list_tasks(state: str = Query("any")):
    sch = get_scheduler()
    rows = sch.list(state=state)
    return [
        {"id": r.id, "name": r.name, "command": r.command, "state": r.state, "priority": r.priority,
         "created_at": r.created_at.isoformat(), "started_at": r.started_at.isoformat() if r.started_at else None,
         "ended_at": r.ended_at.isoformat() if r.ended_at else None, "pid": r.pid, "log_path": r.log_path}
        for r in rows
    ]


class CancelBody(BaseModel):
    task_id: str


@router.post("/cancel")
def cancel(body: CancelBody):
    sch = get_scheduler()
    return {"canceled": bool(sch.cancel(body.task_id))}
