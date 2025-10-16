# edgepilot/scheduler/policies.py
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Dict, Any, Tuple, List
import psutil


@dataclass
class Policy:
    name: str
    rules: Dict[str, Any] = field(default_factory=dict)


PRESETS: Dict[str, Policy] = {
    "performance": Policy(
        name="performance",
        rules={"battery_min_pct": 10, "cpu_max_pct": 95, "mem_reserve_mb": 512, "gpu_max_util_pct": 95,
               "quiet_hours": {"start": "00:00", "end": "00:00", "allow_if_plugged": True}}
    ),
    "balanced_defaults": Policy(
        name="balanced_defaults",
        rules={"battery_min_pct": 30, "cpu_max_pct": 85, "mem_reserve_mb": 2048, "gpu_max_util_pct": 80,
               "quiet_hours": {"start": "22:00", "end": "07:00", "allow_if_plugged": True}}
    ),
    "sip-battery": Policy(
        name="sip-battery",
        rules={"battery_min_pct": 50, "cpu_max_pct": 70, "mem_reserve_mb": 4096, "gpu_max_util_pct": 60,
               "quiet_hours": {"start": "21:00", "end": "08:00", "allow_if_plugged": False}}
    ),
}


def parse_time(s: str) -> time:
    hh, mm = [int(x) for x in s.split(":")]
    return time(hour=hh, minute=mm)


def in_quiet_hours(quiet: Dict[str, Any]) -> bool:
    if not quiet:
        return False
    now = datetime.now().time()
    start = parse_time(quiet.get("start", "22:00"))
    end = parse_time(quiet.get("end", "07:00"))
    if start < end:
        return start <= now < end
    # Over midnight
    return (now >= start) or (now < end)


def evaluate(snapshot: Dict[str, Any], task: Dict[str, Any], rules: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Return (can_start, reasons[]) based on snapshot/process conditions and policy rules."""
    reasons: List[str] = []

    cpu = float(snapshot.get("cpu_total_pct", 0.0))
    mem_used = int(snapshot.get("mem_used_bytes", 0))
    total = psutil.virtual_memory().total
    mem_free_mb = int((total - mem_used) / (1024 * 1024))
    gpu = snapshot.get("gpu", {})
    power = snapshot.get("power", {})

    # Policy checks
    cpu_max = int(min(rules.get("cpu_max_pct", 100), task.get("max_cpu_pct", 100)))
    if cpu > cpu_max:
        reasons.append(f"CPU {cpu:.0f}% exceeds limit {cpu_max}%")

    mem_reserve = int(max(rules.get("mem_reserve_mb", 0), task.get("max_mem_mb", 0)))
    if mem_free_mb < mem_reserve:
        reasons.append(f"Free memory {mem_free_mb}MB below reserve {mem_reserve}MB")

    # Battery / plugged
    battery_min = int(rules.get("battery_min_pct", 0))
    plugged = bool(power.get("plugged", False))
    batt_pct = float(power.get("battery_pct") or 0)
    if battery_min and not plugged and batt_pct and batt_pct < battery_min:
        reasons.append(f"Battery {batt_pct:.0f}% below minimum {battery_min}%")

    # Quiet hours
    quiet = rules.get("quiet_hours")
    if quiet and in_quiet_hours(quiet) and not (plugged and quiet.get("allow_if_plugged", True)):
        reasons.append("Quiet hours in effect")

    # GPU
    if task.get("requires_gpu"):
        if not gpu.get("available"):
            reasons.append("GPU required but not detected")
        else:
            gpu_util = float(gpu.get("util_pct", 0))
            gpu_limit = float(rules.get("gpu_max_util_pct", 90))
            if gpu_util > gpu_limit:
                reasons.append(f"GPU util {gpu_util:.0f}% exceeds limit {gpu_limit:.0f}%")

            min_vram = int(task.get("min_vram_mb", 0))
            total_bytes = int(gpu.get("mem_total_bytes") or 0)
            used_bytes = int(gpu.get("mem_used_bytes") or 0)
            free_mb = int((total_bytes - used_bytes) / (1024 * 1024)) if total_bytes else 0
            if min_vram and free_mb < min_vram:
                reasons.append(f"GPU free VRAM {free_mb}MB below required {min_vram}MB")

    can = len(reasons) == 0
    return can, reasons
