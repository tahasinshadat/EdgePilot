# edgepilot/mcp/schemas.py
from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Optional, List, Any, Dict


class SnapshotInput(BaseModel):
    include_processes: bool = Field(default=False)
    top_n: int = Field(default=15, ge=1, le=100)


class StreamStartInput(BaseModel):
    interval_sec: float = Field(default=2.0, gt=0)
    include_processes: bool = Field(default=False)


class StreamStopInput(BaseModel):
    stream_id: str


class RunStartInput(BaseModel):
    user_note: Optional[str] = None
    sampling_sec: Optional[int] = Field(default=None, gt=0)


class RunEndInput(BaseModel):
    run_id: str


class EnqueueInput(BaseModel):
    name: str
    command: str
    requires_gpu: bool = False
    est_runtime_sec: Optional[int] = None
    priority: int = 5
    deadline_ts: Optional[str] = None
    max_cpu_pct: int = 90
    max_mem_mb: int = 0
    min_vram_mb: int = 0


class ListInput(BaseModel):
    state: Optional[str] = "any"


class CancelInput(BaseModel):
    task_id: str


class PolicySetInput(BaseModel):
    name: str
    rules: Dict[str, Any]


class SimulateInput(BaseModel):
    what_if: Optional[Dict[str, Any]] = None
