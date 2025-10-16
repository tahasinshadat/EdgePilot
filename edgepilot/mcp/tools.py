# edgepilot/mcp/tools.py
from __future__ import annotations

from typing import Dict, Any

from .schemas import (
    SnapshotInput, StreamStartInput, StreamStopInput, RunStartInput, RunEndInput,
    EnqueueInput, ListInput, CancelInput, PolicySetInput, SimulateInput,
)
from ..metrics import get_metrics_service
from ..scheduler import get_scheduler
from ..usage import usage_stats


async def do_metrics_snapshot(params: SnapshotInput) -> Dict[str, Any]:
    svc = get_metrics_service()
    return svc.snapshot(include_processes=params.include_processes, top_n=params.top_n)


async def do_metrics_stream_start(params: StreamStartInput) -> Dict[str, Any]:
    svc = get_metrics_service()
    sid = svc.start_stream(interval=params.interval_sec, include_processes=params.include_processes)
    return {"stream_id": sid}


async def do_metrics_stream_stop(params: StreamStopInput) -> Dict[str, Any]:
    svc = get_metrics_service()
    stopped = svc.stop_stream(params.stream_id)
    return {"stopped": bool(stopped)}


async def do_runs_start(params: RunStartInput) -> Dict[str, Any]:
    svc = get_metrics_service()
    return svc.start_run(user_note=params.user_note or "", sampling_sec=params.sampling_sec)


async def do_runs_end(params: RunEndInput) -> Dict[str, Any]:
    svc = get_metrics_service()
    return await svc.end_run(params.run_id)


async def do_scheduler_enqueue(params: EnqueueInput) -> Dict[str, Any]:
    sch = get_scheduler()
    t = sch.enqueue(**params.model_dump())
    return {"task_id": t.id, "state": t.state}


async def do_scheduler_list(params: ListInput) -> Any:
    sch = get_scheduler()
    rows = sch.list(state=params.state)
    return [ {"id": r.id, "name": r.name, "state": r.state, "priority": r.priority, "command": r.command,
              "started_at": r.started_at.isoformat() if r.started_at else None,
              "ended_at": r.ended_at.isoformat() if r.ended_at else None,
              "pid": r.pid, "log_path": r.log_path } for r in rows ]


async def do_scheduler_cancel(params: CancelInput) -> Dict[str, Any]:
    sch = get_scheduler()
    ok = sch.cancel(params.task_id)
    return {"canceled": bool(ok)}


async def do_scheduler_policy_set(params: PolicySetInput) -> Dict[str, Any]:
    sch = get_scheduler()
    name = sch.policy_set(params.name, params.rules)
    return {"active": name}


async def do_scheduler_simulate(params: SimulateInput) -> Dict[str, Any]:
    sch = get_scheduler()
    return sch.simulate(params.what_if or {})


async def do_usage_stats() -> Dict[str, Any]:
    return usage_stats()
