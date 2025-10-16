# edgepilot/metrics/gpu_linux.py
from __future__ import annotations

import subprocess
from typing import Dict, Any


def read_nvidia_smi() -> Dict[str, Any]:
    """Return GPU util/memory using nvidia-smi if present. Fail gracefully otherwise."""
    try:
        cmd = [
            "nvidia-smi",
            "--query-gpu=utilization.gpu,memory.used,memory.total",
            "--format=csv,noheader,nounits",
        ]
        out = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL, timeout=2)
        # If multiple GPUs, average util and sum memory used; for v0 keep simple
        utils = []
        mem_used = 0
        mem_total = 0
        for line in out.strip().splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 3:
                utils.append(float(parts[0]))
                mem_used += int(float(parts[1]) * 1024 * 1024)  # MiB -> bytes
                mem_total += int(float(parts[2]) * 1024 * 1024)
        if not utils:
            return {"available": False}
        return {
            "available": True,
            "util_pct": sum(utils) / len(utils),
            "mem_used_bytes": mem_used,
            "mem_total_bytes": mem_total,
        }
    except Exception:
        return {"available": False}
