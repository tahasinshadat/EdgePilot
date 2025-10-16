# tests/test_scheduler.py
from edgepilot.scheduler.policies import evaluate, PRESETS

def test_policy_evaluate_allows_when_idle():
    snap = {
        "cpu_total_pct": 10.0,
        "mem_used_bytes": 512 * 1024 * 1024,  # 0.5 GB used
        "gpu": {"available": False},
        "power": {"available": True, "battery_pct": 100, "plugged": True},
    }
    task = {"requires_gpu": False, "min_vram_mb": 0, "max_cpu_pct": 90, "max_mem_mb": 0}
    rules = PRESETS["balanced_defaults"].rules
    ok, reasons = evaluate(snap, task, rules)
    assert ok, reasons

def test_policy_blocks_on_high_cpu():
    snap = {"cpu_total_pct": 99.0, "mem_used_bytes": 1024 * 1024 * 1024,
            "gpu": {"available": False}, "power": {"available": True, "battery_pct": 90, "plugged": True}}
    task = {"requires_gpu": False, "min_vram_mb": 0, "max_cpu_pct": 80, "max_mem_mb": 0}
    rules = PRESETS["balanced_defaults"].rules
    ok, reasons = evaluate(snap, task, rules)
    assert not ok and any("CPU" in r for r in reasons)
