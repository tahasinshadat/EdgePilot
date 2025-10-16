# edgepilot/mcp/server.py
from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

from mcp.server.fastmcp import FastMCP  # Tool may not exist in newer mcp
try:
    from mcp.server.fastmcp import Tool  # type: ignore
    HAS_TOOL_CLASS = True
except Exception:  # pragma: no cover
    Tool = None
    HAS_TOOL_CLASS = False

from .schemas import (
    SnapshotInput, StreamStartInput, StreamStopInput, RunStartInput, RunEndInput,
    EnqueueInput, ListInput, CancelInput, PolicySetInput, SimulateInput,
)
from .tools import (
    do_metrics_snapshot, do_metrics_stream_start, do_metrics_stream_stop,
    do_runs_start, do_runs_end,
    do_scheduler_enqueue, do_scheduler_list, do_scheduler_cancel, do_scheduler_policy_set, do_scheduler_simulate,
    do_usage_stats,
)
from ..db import init_db


def build_server() -> FastMCP:
    # Newer mcp.FastMCP only takes the server name
    server = FastMCP("edgepilot-mcp")

    if HAS_TOOL_CLASS:
        # ----- Older API path (Tool class available) -----
        server.add_tool(Tool(
            name="metrics.snapshot",
            description="Return a single system snapshot. Optional include top-N processes.",
            input_model=SnapshotInput,
            func=do_metrics_snapshot,
        ))
        server.add_tool(Tool(
            name="metrics.stream_start",
            description="Start metrics streaming at a given interval (seconds). Returns a stream_id.",
            input_model=StreamStartInput,
            func=do_metrics_stream_start,
        ))
        server.add_tool(Tool(
            name="metrics.stream_stop",
            description="Stop a running metrics stream by stream_id.",
            input_model=StreamStopInput,
            func=do_metrics_stream_stop,
        ))
        server.add_tool(Tool(
            name="runs.start",
            description="Create a Run and begin higher-frequency sampling.",
            input_model=RunStartInput,
            func=do_runs_start,
        ))
        server.add_tool(Tool(
            name="runs.end",
            description="Stop sampling for the Run, produce a short metrics report, and store it.",
            input_model=RunEndInput,
            func=do_runs_end,
        ))
        server.add_tool(Tool(
            name="scheduler.enqueue",
            description="Queue a local task (shell command).",
            input_model=EnqueueInput,
            func=do_scheduler_enqueue,
        ))
        server.add_tool(Tool(
            name="scheduler.list",
            description="List tasks and states. state=any for all.",
            input_model=ListInput,
            func=do_scheduler_list,
        ))
        server.add_tool(Tool(
            name="scheduler.cancel",
            description="Cancel a queued or running task.",
            input_model=CancelInput,
            func=do_scheduler_cancel,
        ))
        server.add_tool(Tool(
            name="scheduler.policy_set",
            description="Activate/modify policy rules (simple JSON).",
            input_model=PolicySetInput,
            func=do_scheduler_policy_set,
        ))
        server.add_tool(Tool(
            name="scheduler.simulate",
            description="Given current metrics + queue, return a proposed start time for each task and reasoning.",
            input_model=SimulateInput,
            func=do_scheduler_simulate,
        ))
        server.add_tool(Tool(
            name="usage.stats",
            description="Return LLM usage metrics/counters.",
            input_model=None,
            func=do_usage_stats,
        ))
        return server

    # ----- Newer API path (decorator style, no Tool class) -----
    @server.tool(name="metrics.snapshot",
                 description="Return a single system snapshot. Optional include top-N processes.")
    async def _metrics_snapshot(include_processes: bool = False, top_n: int = 15):
        return await do_metrics_snapshot(SnapshotInput(include_processes=include_processes, top_n=top_n))

    @server.tool(name="metrics.stream_start",
                 description="Start metrics streaming at a given interval (seconds). Returns a stream_id.")
    async def _metrics_stream_start(interval_sec: float = 2.0, include_processes: bool = False):
        return await do_metrics_stream_start(StreamStartInput(interval_sec=interval_sec, include_processes=include_processes))

    @server.tool(name="metrics.stream_stop",
                 description="Stop a running metrics stream by stream_id.")
    async def _metrics_stream_stop(stream_id: str):
        return await do_metrics_stream_stop(StreamStopInput(stream_id=stream_id))

    @server.tool(name="runs.start",
                 description="Create a Run and begin higher-frequency sampling.")
    async def _runs_start(user_note: Optional[str] = None, sampling_sec: Optional[int] = None):
        return await do_runs_start(RunStartInput(user_note=user_note, sampling_sec=sampling_sec))

    @server.tool(name="runs.end",
                 description="Stop sampling for the Run, produce a short metrics report, and store it.")
    async def _runs_end(run_id: str):
        return await do_runs_end(RunEndInput(run_id=run_id))

    @server.tool(name="scheduler.enqueue",
                 description="Queue a local task (shell command).")
    async def _scheduler_enqueue(
        name: str, command: str, requires_gpu: bool = False, est_runtime_sec: Optional[int] = None,
        priority: int = 5, deadline_ts: Optional[str] = None, max_cpu_pct: int = 90,
        max_mem_mb: int = 0, min_vram_mb: int = 0
    ):
        return await do_scheduler_enqueue(EnqueueInput(
            name=name, command=command, requires_gpu=requires_gpu, est_runtime_sec=est_runtime_sec,
            priority=priority, deadline_ts=deadline_ts, max_cpu_pct=max_cpu_pct,
            max_mem_mb=max_mem_mb, min_vram_mb=min_vram_mb
        ))

    @server.tool(name="scheduler.list", description="List tasks and states. state=any for all.")
    async def _scheduler_list(state: str = "any"):
        return await do_scheduler_list(ListInput(state=state))

    @server.tool(name="scheduler.cancel", description="Cancel a queued or running task.")
    async def _scheduler_cancel(task_id: str):
        return await do_scheduler_cancel(CancelInput(task_id=task_id))

    @server.tool(name="scheduler.policy_set", description="Activate/modify policy rules (simple JSON).")
    async def _scheduler_policy_set(name: str, rules: Dict[str, Any]):
        return await do_scheduler_policy_set(PolicySetInput(name=name, rules=rules))

    @server.tool(name="scheduler.simulate",
                 description="Given current metrics + queue, return a proposed start time for each task and reasoning.")
    async def _scheduler_simulate(what_if: Optional[Dict[str, Any]] = None):
        return await do_scheduler_simulate(SimulateInput(what_if=what_if))

    @server.tool(name="usage.stats", description="Return LLM usage metrics/counters.")
    async def _usage_stats():
        return await do_usage_stats()

    return server


def run_mcp():
    init_db()
    server = build_server()
    from mcp.server.stdio import stdio_server
    asyncio.run(server.run(stdio_server()))


if __name__ == "__main__":
    run_mcp()
