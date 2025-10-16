# tests/test_metrics.py
from edgepilot.metrics import get_metrics_service

def test_snapshot_has_core_fields():
    svc = get_metrics_service()
    snap = svc.snapshot(include_processes=True, top_n=5)
    assert "cpu_total_pct" in snap
    assert "mem_used_bytes" in snap
    assert "net" in snap and "rx_bytes" in snap["net"]
    assert "disk" in snap and "read_bytes" in snap["disk"]
    assert isinstance(snap.get("processes", []), list)
