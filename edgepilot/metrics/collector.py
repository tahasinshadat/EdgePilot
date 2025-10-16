# edgepilot/metrics/collector.py
from __future__ import annotations

import asyncio
import json
import os
import platform
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Callable, List
import psutil

from ..config import get_config
from ..db import session_scope, init_db
from ..models import Metric, ProcessMetric, Run
from .gpu_linux import read_nvidia_smi
from .power_macos import read_powermetrics


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Stream:
    interval: float
    include_processes: bool
    task: asyncio.Task


class MetricsService:
    """Collects system and per-process metrics; can snapshot or stream, and persist when a Run is active."""

    def __init__(self):
        self.cfg = get_config()
        self.active_run_id: Optional[str] = None
        self._run_task: Optional[asyncio.Task] = None
        self._streams: Dict[str, Stream] = {}
        init_db()

    # ---------- Core collection ----------

    def _collect_snapshot(self, include_processes: bool = False, top_n: int = 15) -> Dict[str, Any]:
        vm = psutil.virtual_memory()
        swap = psutil.swap_memory()
        cpu_pct = psutil.cpu_percent(interval=None)
        net = psutil.net_io_counters()
        disk = psutil.disk_io_counters()

        snapshot: Dict[str, Any] = {
            "ts": utcnow_iso(),
            "cpu_total_pct": float(cpu_pct),
            "mem_used_bytes": int(vm.used),
            "swap_used_bytes": int(swap.used),
            "net": {"rx_bytes": int(net.bytes_recv), "tx_bytes": int(net.bytes_sent)},
            "disk": {"read_bytes": int(disk.read_bytes), "write_bytes": int(disk.write_bytes)},
            "gpu": {"available": False},
            "power": {"available": False},
        }

        # Battery (cross-platform via psutil)
        try:
            batt = psutil.sensors_battery()
            if batt is not None:
                snapshot["power"] = {"available": True, "battery_pct": float(batt.percent), "plugged": bool(batt.power_plugged)}
        except Exception:
            pass

        # Optional GPU
        if self.cfg.metrics.enable_gpu and platform.system().lower() == "linux":
            gpu = read_nvidia_smi()
            if gpu.get("available"):
                snapshot["gpu"] = {
                    "available": True,
                    "util_pct": float(gpu["util_pct"]),
                    "mem_used_bytes": int(gpu["mem_used_bytes"]),
                    "mem_total_bytes": int(gpu["mem_total_bytes"]),
                }

        # Optional power (macOS)
        if self.cfg.metrics.enable_power and platform.system().lower() == "darwin":
            p = read_powermetrics()
            if p.get("available"):
                snapshot["power"] = {"available": True, **{k: v for k, v in p.items() if k != "available"}}

        # Processes
        procs: List[Dict[str, Any]] = []
        if include_processes:
            for p in psutil.process_iter(attrs=["pid", "name", "cmdline", "num_threads"]):
                try:
                    with p.oneshot():
                        cpu = p.cpu_percent(interval=None)  # since last call
                        mem = p.memory_info().rss
                        io = p.io_counters() if hasattr(p, "io_counters") else None
                        procs.append({
                            "pid": p.pid,
                            "name": p.info.get("name") or "",
                            "cpu_pct": float(cpu),
                            "rss_bytes": int(mem),
                            "io_read_bytes": int(getattr(io, "read_bytes", 0) or 0),
                            "io_write_bytes": int(getattr(io, "write_bytes", 0) or 0),
                            "threads": int(p.info.get("num_threads") or 0),
                            "cmdline": " ".join(p.info.get("cmdline") or [])[:512],
                        })
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            # sort by cpu then mem
            procs.sort(key=lambda x: (x["cpu_pct"], x["rss_bytes"]), reverse=True)
            procs = procs[:top_n]
            snapshot["processes"] = procs

        return snapshot

    # ---------- Public API ----------

    def snapshot(self, include_processes: bool = False, top_n: int = 15) -> Dict[str, Any]:
        snap = self._collect_snapshot(include_processes, top_n)
        # If a run is active, persist summary + processes
        if self.active_run_id:
            self._persist_snapshot(self.active_run_id, snap)
        return snap

    def start_stream(self, interval: float = 2.0, include_processes: bool = False) -> str:
        """Start a background task that simply collects at a cadence; used by MCP to demonstrate streaming ID."""
        async def _loop():
            while True:
                _ = self.snapshot(include_processes=include_processes, top_n=self.cfg.metrics.process_top_n)
                await asyncio.sleep(interval)

        stream_id = f"s-{utcnow_iso()}"
        self._streams[stream_id] = Stream(interval=interval, include_processes=include_processes, task=asyncio.create_task(_loop()))
        return stream_id

    def stop_stream(self, stream_id: str) -> bool:
        st = self._streams.pop(stream_id, None)
        if st:
            st.task.cancel()
            return True
        return False

    # ---------- Runs ----------

    def start_run(self, user_note: str | None = None, sampling_sec: Optional[int] = None) -> Dict[str, Any]:
        if self._run_task:
            # already active
            return {"run_id": self.active_run_id, "started_at": None}
        sampling = sampling_sec or self.cfg.metrics.sample_interval
        with session_scope() as s:
            run = Run(user_note=user_note or "")
            s.add(run)
            s.flush()
            run_id = run.id

        self.active_run_id = run_id

        async def _sample_loop():
            while self.active_run_id == run_id:
                _ = self.snapshot(include_processes=True, top_n=self.cfg.metrics.process_top_n)
                await asyncio.sleep(sampling)

        self._run_task = asyncio.create_task(_sample_loop())
        return {"run_id": run_id, "started_at": utcnow_iso()}

    async def end_run(self, run_id: str) -> Dict[str, Any]:
        if run_id != self.active_run_id:
            # Still attempt to summarize if exists.
            return await self._summarize_run(run_id)

        if self._run_task:
            self._run_task.cancel()
        self._run_task = None
        self.active_run_id = None
        return await self._summarize_run(run_id)

    # ---------- Internals ----------

    def _persist_snapshot(self, run_id: str, snap: Dict[str, Any]) -> None:
        init_db()
        with session_scope() as s:
            m = Metric(
                ts=datetime.fromisoformat(snap["ts"]),
                cpu_total_pct=snap["cpu_total_pct"],
                mem_used_bytes=snap["mem_used_bytes"],
                swap_used_bytes=snap["swap_used_bytes"],
                net_rx_bytes=snap["net"]["rx_bytes"],
                net_tx_bytes=snap["net"]["tx_bytes"],
                disk_read_bytes=snap["disk"]["read_bytes"],
                disk_write_bytes=snap["disk"]["write_bytes"],
                gpu_util_pct=snap.get("gpu", {}).get("util_pct"),
                gpu_mem_used_bytes=snap.get("gpu", {}).get("mem_used_bytes"),
                power_watts=None,
                battery_pct=snap.get("power", {}).get("battery_pct"),
                json_detail=json.dumps({k: v for k, v in snap.items() if k not in {"ts"}})[:65535],
                run_id=run_id,
            )
            s.add(m)
            # Store process top N (not required every time; we store when included)
            for p in snap.get("processes", []):
                s.add(ProcessMetric(
                    ts=m.ts, pid=p["pid"], name=p["name"], cpu_pct=p["cpu_pct"],
                    rss_bytes=p["rss_bytes"], io_read_bytes=p["io_read_bytes"], io_write_bytes=p["io_write_bytes"],
                    threads=p["threads"], cmdline=p.get("cmdline")
                ))

    async def _summarize_run(self, run_id: str) -> Dict[str, Any]:
        from sqlalchemy import select
        init_db()
        with session_scope() as s:
            q = select(Metric).where(Metric.run_id == run_id).order_by(Metric.ts)
            rows = list(s.execute(q).scalars())
            if not rows:
                # Update run status cleanly
                run = s.get(Run, run_id)
                if run:
                    run.status = "ended"
                    run.ended_at = datetime.now(timezone.utc)
                return {"ended_at": utcnow_iso(), "summary": {}, "report_text": "No samples collected."}

            avg_cpu = sum(r.cpu_total_pct for r in rows) / len(rows)
            avg_mem_used = sum(r.mem_used_bytes for r in rows) / len(rows)
            avg_mem_gb = avg_mem_used / (1024**3)
            gpu_detected = any(r.gpu_util_pct is not None for r in rows)
            top_proc_stmt = """
Top processes seen:
- (Sampled) check the process_metrics table for details via the UI/CLI.
"""
            report = f"Average CPU {avg_cpu:.1f}%, Average Memory Used {avg_mem_gb:.1f} GiB. " \
                     f"{'GPU detected.' if gpu_detected else 'No GPU detected.'}\n" + top_proc_stmt

            summary = {
                "avg_cpu_pct": round(avg_cpu, 2),
                "avg_mem_used_gb": round(avg_mem_gb, 2),
                "gpu_detected": gpu_detected,
                "samples": len(rows),
            }

            run = s.get(Run, run_id)
            if run:
                run.status = "ended"
                run.ended_at = datetime.now(timezone.utc)
                run.summary_json = json.dumps(summary)

        return {"ended_at": utcnow_iso(), "summary": summary, "report_text": report}


# Global service singleton
_metrics_service: Optional[MetricsService] = None


def get_metrics_service() -> MetricsService:
    global _metrics_service
    if _metrics_service is None:
        _metrics_service = MetricsService()
    return _metrics_service
