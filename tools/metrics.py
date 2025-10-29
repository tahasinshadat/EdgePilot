"""System and Prometheus-backed metric helpers for EdgePilot."""

from __future__ import annotations

import json
import math
import os
import platform
import socket
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import httpx
import psutil

PROM_URL = os.getenv("PROM_URL")
PROM_TIMEOUT = float(os.getenv("PROM_TIMEOUT_SEC", "15"))
ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
RING_PATH = DATA_DIR / "ring.edgepilot.json"
BLUEPRINT_DIR = DATA_DIR


class PrometheusUnavailable(RuntimeError):
    """Raised when Prometheus metrics cannot be fetched."""


class PrometheusClient:
    """Lightweight helper for synchronous Prometheus queries."""

    def __init__(self, base_url: Optional[str] = None, *, timeout: float = PROM_TIMEOUT) -> None:
        self.base_url = base_url
        self.timeout = timeout

    @property
    def available(self) -> bool:
        return bool(self.base_url)

    def _require_url(self) -> str:
        if not self.base_url:
            raise PrometheusUnavailable("PROM_URL environment variable is not configured.")
        return self.base_url

    def query(self, promql: str) -> List[Dict[str, Any]]:
        url = f"{self._require_url().rstrip('/')}/api/v1/query"
        try:
            response = httpx.get(url, params={"query": promql}, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as exc:
            raise PrometheusUnavailable(f"Prometheus request failed: {exc}") from exc
        if data.get("status") != "success":
            raise PrometheusUnavailable(f"Prometheus returned non-success status: {data}")
        return data["data"]["result"]

    def avg_over_time(self, base_query: str, window: str, resolution: str = "1m") -> float:
        query = f"avg_over_time(({base_query})[{window}:])"
        return _avg_vector(self.query(query))

    def topk_over_time(self, base_query: str, window: str, k: int, resolution: str = "1m") -> List[Dict[str, Any]]:
        query = f"topk({k}, avg_over_time(({base_query})[{window}:{resolution}]))"
        return self.query(query)

    def fetch_scalar_map(self, query: str, *, label: str = "instance") -> Dict[str, float]:
        result = self.query(query)
        output: Dict[str, float] = {}
        for row in result:
            metric = row.get("metric", {})
            key = metric.get(label)
            if not key:
                continue
            try:
                value = float(row["value"][1])
            except (KeyError, TypeError, ValueError):
                continue
            if math.isfinite(value):
                output[key] = value
        return output


PROM = PrometheusClient(PROM_URL)

_JSON_CACHE: Dict[Path, Tuple[float, Any]] = {}


def _load_json_config(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(path)
    mtime = path.stat().st_mtime
    cached = _JSON_CACHE.get(path)
    if cached and cached[0] == mtime:
        return cached[1]
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    _JSON_CACHE[path] = (mtime, data)
    return data


def _load_ring() -> Dict[str, Any]:
    return _load_json_config(RING_PATH)


def _blueprint_path(name: str) -> Path:
    filename = f"blueprint.{name}.json"
    return BLUEPRINT_DIR / filename


def _load_blueprint(report: str) -> Dict[str, Any]:
    path = _blueprint_path(report)
    return _load_json_config(path)


def _find_entity(ring: Dict[str, Any], entity_name: str) -> Dict[str, Any]:
    for entity in ring.get("entities", []):
        if entity.get("name") == entity_name:
            return entity
    raise KeyError(f"Entity '{entity_name}' not defined in ring.")


def _find_attribute(entity: Dict[str, Any], attribute_name: str) -> Dict[str, Any]:
    for attribute in entity.get("attributes", []):
        if attribute.get("name") == attribute_name:
            return attribute
    raise KeyError(f"Attribute '{entity.get('name')}.{attribute_name}' not defined in ring.")


def _maybe_apply_datasource(client: PrometheusClient, ring: Optional[Dict[str, Any]]) -> None:
    if client.base_url:
        return
    if not ring:
        return
    datasource = ring.get("datasource") or {}
    if datasource.get("type") == "prometheus" and datasource.get("base_url"):
        client.base_url = datasource["base_url"]


def _avg_vector(result: Iterable[Dict[str, Any]]) -> float:
    values: List[float] = []
    for row in result:
        raw_value = row.get("value", [None, None])[1]
        try:
            candidate = float(raw_value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(candidate):
            values.append(candidate)
    return (sum(values) / len(values)) if values else float("nan")


def _pretty_container_name(metric: Dict[str, Any]) -> str:
    identifier = metric.get("id") or metric.get("container") or "unknown"
    return identifier.split("/")[-1][:32]


def _offpeak_local_iso() -> str:
    now = datetime.now().astimezone()
    candidate = now.replace(hour=1, minute=0, second=0, microsecond=0)
    if now.hour >= 1:
        candidate += timedelta(days=1)
    return candidate.isoformat()


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


def _process_snapshot(limit: Optional[int] = 10) -> List[Dict[str, float | int | str]]:
    procs = []
    for proc in psutil.process_iter(attrs=["pid", "name", "cpu_percent", "memory_info"]):
        with proc.oneshot():
            info = proc.info
            rss = info["memory_info"].rss if info.get("memory_info") else 0
            cpu_pct = info.get("cpu_percent") or 0.0
            procs.append(
                {
                    "pid": info["pid"],
                    "name": info.get("name") or "unknown",
                    "cpu_percent": float(cpu_pct),
                    "rss_bytes": rss,
                }
            )
    procs.sort(key=lambda item: item["cpu_percent"], reverse=True)
    if limit is None or limit <= 0:
        return procs
    return procs[:limit]


def gather_metrics(top_n: int = 10, all_processes: bool = False) -> Dict[str, Any]:
    """Collect local host metrics via psutil."""
    cpu_percent = psutil.cpu_percent(interval=0.1)
    virtual_mem = psutil.virtual_memory()
    swap = psutil.swap_memory()
    disk_io = psutil.disk_io_counters()
    disk_usage = psutil.disk_usage("/")
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
        "disk_io": {
            "read_bytes": disk_io.read_bytes if disk_io else 0,
            "write_bytes": disk_io.write_bytes if disk_io else 0,
        },
        "filesystem": {
            "mount": "/",
            "total": disk_usage.total,
            "used": disk_usage.used,
            "free": disk_usage.free,
            "percent": disk_usage.percent,
        },
        "network": {
            "bytes_sent": net.bytes_sent if net else 0,
            "bytes_recv": net.bytes_recv if net else 0,
        },
        "battery": _battery_info(),
        "gpu": _gpu_info(),
        "top_processes": _process_snapshot(None if all_processes else top_n),
    }
    return metrics


def report_edge_status(window: str = "1h", top_k: int = 5, *, client: PrometheusClient | None = None) -> Dict[str, Any]:
    """Return the edge status facts using Prometheus if available."""
    client = client or PROM
    source = "prometheus"
    facts: List[str] = []
    ring: Optional[Dict[str, Any]] = None
    blueprint: Optional[Dict[str, Any]] = None
    try:
        ring = _load_ring()
        blueprint = _load_blueprint("edge_status")
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        ring = None
        blueprint = None

    _maybe_apply_datasource(client, ring)

    if client.available and ring and blueprint:
        try:
            for plan in blueprint.get("plans", []):
                entity = _find_entity(ring, plan["entity"])
                attribute = _find_attribute(entity, plan["attribute"])
                base_query = attribute.get("promql")
                if not base_query:
                    raise KeyError(f"Attribute {plan['entity']}.{plan['attribute']} missing promql.")

                template = plan.get("template")
                if template == "TREND":
                    value = client.avg_over_time(base_query, window)
                    facts.append(plan["statement"].format(range=window, value=value))
                elif template == "RANKING":
                    k_value = int(plan.get("k") or top_k)
                    rows = client.topk_over_time(base_query, window, k_value)
                    items = [
                        f"{_pretty_container_name(row.get('metric', {}))}={float(row['value'][1]):.3f}"
                        for row in rows
                        if _is_finite_value(row.get("value"))
                    ]
                    facts.append(plan["statement"].format(k=k_value, items=", ".join(items) or "none"))
                elif template == "THRESHOLD":
                    operator = plan.get("operator")
                    value = plan.get("value")
                    if operator is None or value is None:
                        raise KeyError("THRESHOLD plan must define 'operator' and 'value'.")
                    query = f"{base_query} {operator} {value}"
                    rows = client.query(query)
                    if not rows:
                        facts.append(plan["statement"].format(items="none"))
                    else:
                        labels = []
                        for row in rows:
                            metric = row.get("metric", {})
                            label = "/".join(
                                filter(
                                    None,
                                    [
                                        metric.get("instance"),
                                        metric.get("mountpoint"),
                                        metric.get("device"),
                                    ],
                                )
                            )
                            labels.append(label or "unknown")
                        facts.append(plan["statement"].format(items=", ".join(labels)))
                else:
                    raise ValueError(f"Unknown plan template '{template}'")
        except (PrometheusUnavailable, KeyError, ValueError):
            source = "local"
            facts = []
    else:
        source = "local"

    if not facts:
        process_limit = max(top_k, _max_process_limit(ring)) or top_k
        snapshot = gather_metrics(top_n=process_limit)
        local_facts = _facts_from_local(snapshot, ring, blueprint, window=window, top_k=top_k)
        if local_facts:
            facts.extend(local_facts)
        else:
            cpu = snapshot["cpu"]["percent"]
            mem_available = snapshot["memory"]["available"] / (1024**3)
            disk_percent = snapshot["filesystem"]["percent"]
            top_processes = ", ".join(
                f"{proc['name']}({proc['cpu_percent']:.1f}% CPU)" for proc in snapshot["top_processes"][:top_k]
            )
            facts.extend(
                [
                    f"Instant CPU usage is {cpu:.1f}% across {snapshot['cpu']['cores_logical']} logical cores.",
                    f"Approximately {mem_available:.1f} GiB memory remains available.",
                    f"Root filesystem utilization is {disk_percent:.1f}%.",
                    f"Top {top_k} processes by CPU right now: {top_processes or 'none'}",
                ]
            )
    return {"status": "ok", "window": window, "top_k": top_k, "facts": facts, "source": source}


def evaluate_capacity(
    requirements: Dict[str, float],
    *,
    duration: str = "45m",
    host: Optional[str] = None,
    client: PrometheusClient | None = None,
) -> Dict[str, Any]:
    """Determine whether the workload can run now."""
    client = client or PROM
    results: List[Dict[str, Any]] = []
    source = "prometheus"

    need_cpu = float(requirements.get("cpu_pct", 0) or 0)
    need_mem = float(requirements.get("mem_bytes", 0) or 0)
    need_disk = float(requirements.get("disk_free_bytes", 0) or 0)

    if not client.available:
        try:
            ring = _load_ring()
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            ring = None
        _maybe_apply_datasource(client, ring)

    if client.available:
        try:
            cpu_headroom = client.fetch_scalar_map(
                '100 - (100 * (1 - avg by (instance) (rate(node_cpu_seconds_total{mode="idle"}[5m]))))'
            )
            mem_free = client.fetch_scalar_map("node_memory_MemAvailable_bytes")
            disk_free = client.fetch_scalar_map(
                'max by (instance) (node_filesystem_free_bytes{fstype!~"tmpfs|overlay"})'
            )
            instances = [host] if host else sorted(set(cpu_headroom) | set(mem_free) | set(disk_free))
            for instance in instances:
                reasons: List[str] = []
                cpu_now = cpu_headroom.get(instance, 0.0)
                mem_now = mem_free.get(instance, 0.0)
                disk_now = disk_free.get(instance, 0.0)
                can_run = True
                if cpu_now < need_cpu:
                    can_run = False
                    reasons.append(f"CPU headroom {cpu_now:.1f}% < need {need_cpu:.1f}%")
                if mem_now < need_mem:
                    can_run = False
                    reasons.append(f"Mem free {int(mem_now)} < need {int(need_mem)}")
                if disk_now < need_disk:
                    can_run = False
                    reasons.append(f"Disk free {int(disk_now)} < need {int(need_disk)}")
                results.append(
                    {
                        "instance": instance or host or "unknown",
                        "can_run_now": can_run,
                        "reasons": reasons,
                        "headroom_now": {
                            "cpu_pct": cpu_now,
                            "mem_bytes": mem_now,
                            "disk_free_bytes": disk_now,
                        },
                        "requested": {
                            "duration": duration,
                            "cpu_pct": need_cpu,
                            "mem_bytes": need_mem,
                            "disk_free_bytes": need_disk,
                        },
                    }
                )
        except PrometheusUnavailable:
            source = "local"
            results = []
    else:
        source = "local"

    if not results:
        snapshot = gather_metrics()
        hostname = host or socket.gethostname()
        cpu_headroom = max(0.0, 100.0 - snapshot["cpu"]["percent"])
        mem_available = snapshot["memory"]["available"]
        disk_free = snapshot["filesystem"]["free"]
        reasons: List[str] = []
        can_run = True
        if cpu_headroom < need_cpu:
            can_run = False
            reasons.append(f"CPU headroom {cpu_headroom:.1f}% < need {need_cpu:.1f}%")
        if mem_available < need_mem:
            can_run = False
            reasons.append(f"Mem free {int(mem_available)} < need {int(need_mem)}")
        if disk_free < need_disk:
            can_run = False
            reasons.append(f"Disk free {int(disk_free)} < need {int(need_disk)}")
        results.append(
            {
                "instance": hostname,
                "can_run_now": can_run,
                "reasons": reasons,
                "headroom_now": {
                    "cpu_pct": cpu_headroom,
                    "mem_bytes": mem_available,
                    "disk_free_bytes": disk_free,
                },
                "requested": {
                    "duration": duration,
                    "cpu_pct": need_cpu,
                    "mem_bytes": need_mem,
                    "disk_free_bytes": need_disk,
                },
            }
        )
    return {"status": "ok", "results": results, "source": source}


def suggest_capacity_window(
    requirements: Dict[str, float],
    *,
    duration: str = "45m",
    horizon_hours: int = 24,
    host: Optional[str] = None,
    client: PrometheusClient | None = None,
) -> Dict[str, Any]:
    """Suggest execution windows based on recent utilization."""
    client = client or PROM
    source = "prometheus"
    need_cpu = float(requirements.get("cpu_pct", 0) or 0)
    need_mem = float(requirements.get("mem_bytes", 0) or 0)
    need_disk = float(requirements.get("disk_free_bytes", 0) or 0)
    results: List[Dict[str, Any]] = []

    if not client.available:
        try:
            ring = _load_ring()
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            ring = None
        _maybe_apply_datasource(client, ring)

    if client.available:
        try:
            cpu_busy = client.fetch_scalar_map(
                'quantile_over_time(0.95, (100 * (1 - avg by (instance) '
                '(rate(node_cpu_seconds_total{mode="idle"}[5m]))))[1h:1m])'
            )
            mem_p05 = client.fetch_scalar_map('quantile_over_time(0.05, node_memory_MemAvailable_bytes[1h])')
            disk_p05 = client.fetch_scalar_map(
                'quantile_over_time(0.05, node_filesystem_free_bytes{fstype!~"tmpfs|overlay"}[1h])'
            )
            cpu_headroom = {name: max(0.0, 100.0 - value) for name, value in cpu_busy.items()}
            instances = [host] if host else sorted(set(cpu_headroom) | set(mem_p05) | set(disk_p05))
            for instance in instances:
                windows = []
                cpu_now = cpu_headroom.get(instance, 0.0)
                mem_now = mem_p05.get(instance, 0.0)
                disk_now = disk_p05.get(instance, 0.0)
                if cpu_now >= need_cpu and mem_now >= need_mem and disk_now >= need_disk:
                    windows.append(
                        {
                            "start": "now",
                            "duration": duration,
                            "reason": "p95 headroom sufficient",
                        }
                    )
                windows.append(
                    {
                        "start": _offpeak_local_iso(),
                        "duration": duration,
                        "reason": "typical off-peak (1–4am local)",
                    }
                )
                results.append({"instance": instance or host or "unknown", "windows": windows})
        except PrometheusUnavailable:
            source = "local"
            results = []
    else:
        source = "local"

    if not results:
        snapshot = gather_metrics()
        hostname = host or socket.gethostname()
        cpu_headroom = max(0.0, 100.0 - snapshot["cpu"]["percent"])
        mem_available = snapshot["memory"]["available"]
        disk_free = snapshot["filesystem"]["free"]
        windows = []
        if cpu_headroom >= need_cpu and mem_available >= need_mem and disk_free >= need_disk:
            windows.append({"start": "now", "duration": duration, "reason": "current headroom sufficient"})
        windows.append(
            {
                "start": (_offpeak_local_iso()),
                "duration": duration,
                "reason": "local fallback off-peak estimate",
            }
        )
        results.append({"instance": hostname, "windows": windows})
    return {"status": "ok", "results": results, "source": source, "horizon_hours": horizon_hours}


def _is_finite_value(value: Any) -> bool:
    try:
        val = float(value[1] if isinstance(value, (list, tuple)) else value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(val)


def _extract_field(payload: Dict[str, Any], path: List[str]) -> Any:
    value: Any = payload
    for key in path:
        if isinstance(value, dict):
            value = value.get(key)
        else:
            return None
    return value


def _apply_transform(value: Any, transform: Optional[str]) -> Any:
    if value is None or transform is None:
        return value
    if transform == "bytes_to_gib":
        return float(value) / (1024**3)
    return value


def _format_process_list(processes: List[Dict[str, Any]], *, sort_key: str, limit: int, display: str | None) -> str:
    if not isinstance(processes, list):
        return "none"
    safe_limit = max(1, limit)
    items = sorted(processes, key=lambda proc: float(proc.get(sort_key) or 0.0), reverse=True)[:safe_limit]
    formatted: List[str] = []
    for proc in items:
        name = proc.get("name") or "unknown"
        if display == "memory":
            rss = float(proc.get("rss_bytes") or 0.0)
            if rss >= 1024**3:
                formatted.append(f"{name} ({rss / (1024**3):.2f} GiB RSS)")
            elif rss >= 1024**2:
                formatted.append(f"{name} ({rss / (1024**2):.1f} MiB RSS)")
            else:
                formatted.append(f"{name} ({rss / 1024:.1f} KiB RSS)")
        elif display == "cpu":
            formatted.append(f"{name} ({float(proc.get('cpu_percent') or 0.0):.1f}% CPU)")
        else:
            formatted.append(name)
    return ", ".join(formatted) if formatted else "none"


def _max_process_limit(ring: Optional[Dict[str, Any]]) -> int:
    if not ring:
        return 0
    max_limit = 0
    for entity in ring.get("entities", []):
        for attribute in entity.get("attributes", []):
            fields = attribute.get("fields") or {}
            if isinstance(fields, dict) and any(path == ["top_processes"] for path in fields.values()):
                try:
                    limit = int(attribute.get("limit", 0))
                except (TypeError, ValueError):
                    limit = 0
                max_limit = max(max_limit, limit)
    return max_limit


def _facts_from_local(
    metrics: Dict[str, Any],
    ring: Optional[Dict[str, Any]],
    blueprint: Optional[Dict[str, Any]],
    *,
    window: str,
    top_k: int,
) -> List[str]:
    if not ring or not blueprint:
        return []
    facts: List[str] = []
    for plan in blueprint.get("plans", []):
        try:
            entity = _find_entity(ring, plan["entity"])
            attribute = _find_attribute(entity, plan["attribute"])
        except KeyError:
            continue

        fields_spec = attribute.get("fields")
        if not isinstance(fields_spec, dict):
            continue
        transforms = attribute.get("transforms") or {}
        values: Dict[str, Any] = {}
        for field, path in fields_spec.items():
            if not isinstance(path, list):
                continue
            raw = _extract_field(metrics, path)
            values[field] = _apply_transform(raw, transforms.get(field))

        template = plan.get("template")
        if template == "LOCAL_VALUE":
            if any(v is None for v in values.values()):
                continue
            try:
                facts.append(plan["statement"].format(range=window, **values))
            except KeyError:
                continue
        elif template == "LOCAL_TOP":
            processes = values.get("processes")
            if not isinstance(processes, list):
                continue
            sort_key = attribute.get("sort_key") or "cpu_percent"
            limit = int(attribute.get("limit", top_k) or top_k)
            display = attribute.get("format")
            formatted = _format_process_list(processes, sort_key=sort_key, limit=limit, display=display)
            try:
                facts.append(plan["statement"].format(items=formatted, range=window))
            except KeyError:
                continue
    return facts


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
