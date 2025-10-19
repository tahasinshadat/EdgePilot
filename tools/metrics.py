"""System metrics helpers exposed to LLM tools."""

from __future__ import annotations

import platform
import time
from pathlib import Path
from typing import Dict, List

import psutil


def _battery_info() -> Dict[str, float | bool | None]:
    battery = psutil.sensors_battery()
    if not battery:
        return {"available": False}
    return {
        "available": True,
        "percent": battery.percent,
        "secs_left": battery.secsleft,
        "power_plugged": battery.power_plugged,
    }


def _gpu_info() -> Dict[str, float | bool | None]:
    # psutil does not expose GPU info; stub for future integrations.
    return {"available": False}


def _process_snapshot(limit: int = 10) -> List[Dict[str, float | int | str]]:
    procs = []
    for proc in psutil.process_iter(attrs=["pid", "name", "cpu_percent", "memory_info"]):
        with proc.oneshot():
            info = proc.info
            rss = info["memory_info"].rss if info.get("memory_info") else 0
            procs.append(
                {
                    "pid": info["pid"],
                    "name": info.get("name") or "unknown",
                    "cpu_percent": info.get("cpu_percent", 0.0),
                    "rss_bytes": rss,
                }
            )
    procs.sort(key=lambda item: item["cpu_percent"], reverse=True)
    return procs[:limit]


def gather_metrics(top_n: int = 10) -> Dict[str, object]:
    """Collect metrics for the dashboard and tool calls."""
    cpu_percent = psutil.cpu_percent(interval=0.1)
    virtual_mem = psutil.virtual_memory()
    swap = psutil.swap_memory()
    disk = psutil.disk_io_counters()
    net = psutil.net_io_counters()

    metrics = {
        "ts": time.time(),
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "python_version": platform.python_version(),
        },
        "cpu": {
            "percent": cpu_percent,
            "cores_logical": psutil.cpu_count(),
            "cores_physical": psutil.cpu_count(logical=False),
        },
        "memory": {
            "total": virtual_mem.total,
            "used": virtual_mem.used,
            "available": virtual_mem.available,
            "percent": virtual_mem.percent,
            "swap_total": swap.total,
            "swap_used": swap.used,
        },
        "disk": {
            "read_bytes": disk.read_bytes if disk else 0,
            "write_bytes": disk.write_bytes if disk else 0,
        },
        "network": {
            "bytes_sent": net.bytes_sent if net else 0,
            "bytes_recv": net.bytes_recv if net else 0,
        },
        "battery": _battery_info(),
        "gpu": _gpu_info(),
        "top_processes": _process_snapshot(top_n),
    }
    return metrics


def ensure_data_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


if __name__ == "__main__":
    import argparse
    import json as _json

    parser = argparse.ArgumentParser(description="EdgePilot metrics snapshot")
    parser.add_argument("--top-n", type=int, default=10, help="Number of processes to include")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")
    args = parser.parse_args()

    data = gather_metrics(top_n=args.top_n)
    indent = 2 if args.pretty else None
    print(_json.dumps(data, indent=indent))
