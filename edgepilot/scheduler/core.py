# edgepilot/scheduler/core.py
from __future__ import annotations

import asyncio
import json
import heapq
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select, update

from ..config import get_config
from ..db import session_scope, init_db
from ..metrics import get_metrics_service
from ..models import Task, ScheduleEvent, Policy
from .policies import PRESETS, evaluate
from .runner import start_subprocess, TaskHandle


def utcnow():
    return datetime.now(timezone.utc)


@dataclass(order=True)
class QueueItem:
    priority: int
    ts: float
    task_id: str = field(compare=False)


class Scheduler:
    """Simple local scheduler with policy checks."""
    def __init__(self):
        self.cfg = get_config()
        self.metrics = get_metrics_service()
        self._handles: Dict[str, TaskHandle] = {}
        self._queue: List[QueueItem] = []
        self._bg_task: Optional[asyncio.Task] = None
        self._active: bool = False
        init_db()
        self._load_existing_queue()

    def _load_existing_queue(self):
        with session_scope() as s:
            q = select(Task).where(Task.state == "queued")
            for t in s.execute(q).scalars():
                self._push_queue(t)

    def _push_queue(self, t: Task):
        heapq.heappush(self._queue, QueueItem(priority=t.priority, ts=t.created_at.timestamp(), task_id=t.id))

    # ---------- Public control ----------

    def start(self):
        if self._bg_task:
            return
        self._active = True

        async def _loop():
            while self._active:
                try:
                    await self._tick()
                except Exception:
                    # Don't die silently; continue
                    await asyncio.sleep(self.cfg.scheduler.queue_check_interval)
                await asyncio.sleep(self.cfg.scheduler.queue_check_interval)

        self._bg_task = asyncio.create_task(_loop())

    def stop(self):
        self._active = False
        if self._bg_task:
            self._bg_task.cancel()
            self._bg_task = None

    # ---------- API ----------

    def enqueue(self, **payload) -> Task:
        init_db()
        with session_scope() as s:
            t = Task(
                name=payload.get("name", "task"),
                command=payload["command"],
                est_runtime_sec=payload.get("est_runtime_sec"),
                requires_gpu=bool(payload.get("requires_gpu", False)),
                min_vram_mb=int(payload.get("min_vram_mb", 0) or 0),
                max_cpu_pct=int(payload.get("max_cpu_pct", 100) or 100),
                max_mem_mb=int(payload.get("max_mem_mb", 0) or 0),
                priority=int(payload.get("priority", 5) or 5),
                deadline_ts=payload.get("deadline_ts"),
                state="queued",
            )
            s.add(t)
            s.flush()
            s.add(ScheduleEvent(kind="enqueued", task_id=t.id, note=t.name))
            s.commit()
            self._push_queue(t)
            return t

    def list(self, state: Optional[str] = None) -> List[Task]:
        with session_scope() as s:
            q = select(Task)
            if state and state != "any":
                q = q.where(Task.state == state)
            return list(s.execute(q.order_by(Task.created_at)).scalars())

    def cancel(self, task_id: str) -> bool:
        with session_scope() as s:
            t = s.get(Task, task_id)
            if not t:
                return False
            if t.state == "queued":
                t.state = "canceled"
                s.add(ScheduleEvent(kind="canceled", task_id=t.id, note="Canceled while queued"))
                return True
            if t.state == "running":
                # Best-effort terminate
                ok = False
                handle = self._handles.get(task_id)
                if handle and handle.popen.poll() is None:
                    try:
                        handle.popen.terminate()
                        ok = True
                    except Exception:
                        ok = False
                t.state = "canceled"
                s.add(ScheduleEvent(kind="canceled", task_id=t.id, note="Terminated"))
                return ok
        return False

    def policy_set(self, name: str, rules: Dict) -> str:
        with session_scope() as s:
            # Deactivate old
            s.execute(update(Policy).values(active=False))
            # Upsert
            p = s.query(Policy).filter(Policy.name == name).one_or_none()
            if p:
                p.json_rules = json.dumps(rules)
                p.active = True
            else:
                p = Policy(name=name, json_rules=json.dumps(rules), active=True)
            s.add(p)
        return name

    def simulate(self, what_if: Dict[str, any] | None = None) -> Dict[str, any]:
        """Very simple simulation: for queued tasks, return now or after 15m if can't start."""
        snap = self.metrics.snapshot(include_processes=False)
        rules = self._active_rules()
        plan = []
        for t in self.list(state="queued"):
            can, reasons = evaluate(snap, _task_as_dict(t), rules)
            plan.append({
                "task_id": t.id,
                "start_at": datetime.now(timezone.utc).isoformat() if can else None,
                "why": "Ok to start now" if can else "; ".join(reasons) or "Policy conditions not met",
            })
        return {"plan": plan}

    # ---------- Internals ----------

    async def _tick(self):
        # Launch new tasks if capacity available
        running = sum(1 for h in self._handles.values() if h.popen.poll() is None)
        while running < self.cfg.scheduler.max_parallel and self._queue:
            t = await self._maybe_start_next()
            if not t:
                break
            running += 1

        # Poll running tasks
        to_remove = []
        with session_scope() as s:
            for tid, handle in list(self._handles.items()):
                rc = handle.popen.poll()
                if rc is not None:
                    # finished
                    t = s.get(Task, tid)
                    if t:
                        t.state = "done" if rc == 0 else "failed"
                        t.return_code = rc
                        t.ended_at = utcnow()
                        s.add(ScheduleEvent(kind="finished" if rc == 0 else "failed", task_id=tid, note=f"rc={rc}"))
                    to_remove.append(tid)
        for tid in to_remove:
            self._handles.pop(tid, None)

    async def _maybe_start_next(self) -> Optional[Task]:
        if not self._queue:
            return None
        item = heapq.heappop(self._queue)
        with session_scope() as s:
            t = s.get(Task, item.task_id)
            if not t or t.state != "queued":
                return None
            snap = self.metrics.snapshot(include_processes=False)
            rules = self._active_rules()
            can, reasons = evaluate(snap, _task_as_dict(t), rules)
            if not can:
                # Push back with slight priority penalty to avoid starvation
                t.priority += 1
                self._push_queue(t)
                s.add(ScheduleEvent(kind="deferred", task_id=t.id, note="; ".join(reasons)))
                return None

            # Start
            log_dir = get_config().storage.log_path
            handle = start_subprocess(t.id, t.command, log_dir)
            self._handles[t.id] = handle
            t.state = "running"
            t.started_at = utcnow()
            t.pid = handle.popen.pid
            t.log_path = str(handle.log_path)
            s.add(ScheduleEvent(kind="started", task_id=t.id, note=t.command))
            return t

    def _active_rules(self) -> Dict:
        with session_scope() as s:
            p = s.query(Policy).filter(Policy.active == True).one_or_none()
            if p:
                return json.loads(p.json_rules)
        # seed default preset if nothing
        rules = PRESETS[self.cfg.scheduler.default_policy].rules
        self.policy_set(self.cfg.scheduler.default_policy, rules)
        return rules


# Singleton
_scheduler: Optional[Scheduler] = None


def get_scheduler() -> Scheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = Scheduler()
        if _scheduler.cfg.scheduler.enable_auto_start:
            _scheduler.start()
    return _scheduler


def _task_as_dict(t: Task) -> Dict[str, any]:
    return {
        "requires_gpu": t.requires_gpu,
        "min_vram_mb": t.min_vram_mb,
        "max_cpu_pct": t.max_cpu_pct,
        "max_mem_mb": t.max_mem_mb,
        "priority": t.priority,
    }
