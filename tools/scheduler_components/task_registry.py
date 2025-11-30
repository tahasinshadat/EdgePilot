"""Task registry and command result utilities."""

from __future__ import annotations

import copy
import itertools
import json
import threading
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data"
TASK_HISTORY_FILE = DATA_DIR / "task_history.json"
MAX_TASK_HISTORY = 500


class TaskExecutionError(RuntimeError):
    """Raised when a task fails to execute."""


@dataclass
class CommandResult:
    """Normalized response returned by scheduler operations."""
    action: str
    command: List[str] | str
    cwd: Optional[str]
    started_at: float
    finished_at: float
    stdout: str = ""
    stderr: str = ""
    exit_code: Optional[int] = None
    pid: Optional[int] = None

    @property
    def ok(self) -> bool:
        return self.exit_code is None or self.exit_code == 0

    def to_dict(self) -> Dict[str, object]:
        payload = asdict(self)
        payload["ok"] = self.ok
        return payload


class TaskRegistry:
    """Registry for tracking scheduled operations with persistence."""
    def __init__(self) -> None:
        self._records: Dict[str, Dict[str, Any]] = {}
        self._index: Dict[tuple, List[str]] = {}
        self._recent: List[str] = []
        self._recent_by_action: Dict[str, List[str]] = {}
        self._lock = threading.Lock()
        self._counter = itertools.count(1)
        self._load_from_disk()

    def _load_from_disk(self) -> None:
        if not TASK_HISTORY_FILE.exists():
            return
        try:
            with TASK_HISTORY_FILE.open("r", encoding="utf-8") as fh:
                tasks = json.load(fh).get("tasks", [])
                for record in tasks:
                    if task_id := record.get("task_id"):
                        self._records[task_id] = record
                self._rebuild_indexes()
                self._reset_counter()
        except (json.JSONDecodeError, OSError):
            pass

    def _reset_counter(self) -> None:
        max_id = max((int(str(tid).split(":")[-1]) for tid in self._records if ":" in str(tid)), default=0)
        self._counter = itertools.count(max_id + 1)

    def _rebuild_indexes(self) -> None:
        ordered = sorted(self._records.values(), key=lambda r: r.get("created_at", 0))
        self._index = {}
        self._recent = []
        self._recent_by_action = {}
        for record in ordered:
            if task_id := record.get("task_id"):
                key = (record.get("action"), record.get("target"))
                self._index.setdefault(key, []).append(task_id)
                self._recent.append(task_id)
                self._recent_by_action.setdefault(record.get("action"), []).append(task_id)

    def _persist(self) -> None:
        if len(self._records) > MAX_TASK_HISTORY:
            ordered = sorted(self._records.values(), key=lambda r: r.get("created_at", 0))
            keep = ordered[-MAX_TASK_HISTORY:]
            self._records = {rec["task_id"]: rec for rec in keep if rec.get("task_id")}
            self._rebuild_indexes()
            self._reset_counter()
        ordered = sorted(self._records.values(), key=lambda r: r.get("created_at", 0))
        TASK_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = TASK_HISTORY_FILE.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump({"tasks": ordered}, fh, indent=2)
        tmp.replace(TASK_HISTORY_FILE)

    def register(self, action: str, target: str, *, delay_seconds: int = 0, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        now = time.time()
        task_id = f"{action}:{int(now * 1000)}:{next(self._counter)}"
        record = {
            "task_id": task_id, "action": action, "target": target, "status": "scheduled",
            "created_at": now, "scheduled_for": now + delay_seconds if delay_seconds > 0 else now,
            "delay_seconds": delay_seconds, "started_at": None, "finished_at": None,
            "result": None, "error": None, "metadata": metadata.copy() if metadata else {},
        }
        with self._lock:
            self._records[task_id] = record
            key = (action, target)
            self._index.setdefault(key, []).append(task_id)
            self._recent.append(task_id)
            self._recent_by_action.setdefault(action, []).append(task_id)
            self._persist()
        return copy.deepcopy(record)

    def _update_status(self, task_id: str, status: str, **updates) -> Optional[Dict[str, Any]]:
        with self._lock:
            if record := self._records.get(task_id):
                record["status"] = status
                record.update(updates)
                self._persist()
                return copy.deepcopy(record)
            return None

    def mark_running(self, task_id: str) -> Optional[Dict[str, Any]]:
        return self._update_status(task_id, "running", started_at=time.time())

    def mark_completed(self, task_id: str, result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return self._update_status(task_id, "completed", finished_at=time.time(), result=result, error=None)

    def mark_failed(self, task_id: str, error: str) -> Optional[Dict[str, Any]]:
        return self._update_status(task_id, "failed", finished_at=time.time(), error=error)

    def get(self, task_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return copy.deepcopy(self._records.get(task_id))

    def list_recent(self, action: Optional[str], limit: int) -> List[Dict[str, Any]]:
        if limit <= 0:
            return []
        with self._lock:
            task_ids = self._recent_by_action.get(action, []) if action else self._recent
            if not task_ids:
                return []
            selected = task_ids[-limit:]
            return [copy.deepcopy(self._records[tid]) for tid in reversed(selected)]

    def list_all(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [copy.deepcopy(record) for record in self._records.values()]
