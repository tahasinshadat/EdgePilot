"""Rightsizing analysis over normalized resource records.

Compares what work *requests* against what it *actually consumes* and
recommends corrected CPU, memory and GPU sizing. Deliberately pure: the
engine imports no scheduler client and performs no I/O, so it runs
identically over Slurm accounting and live Kubernetes, and is fully
testable with no cluster.

Scheduler-specific loading lives behind the tool entry points at the bottom
of this module, which import their sources lazily.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Optional

from .resource_records import ResourceRecord

DEFAULT_CPU_TARGET_UTILIZATION = 0.70
DEFAULT_MEMORY_TARGET_UTILIZATION = 0.80
DEFAULT_GPU_TARGET_UTILIZATION = 0.70

# Below this mean utilization a GPU allocation is treated as idle rather
# than merely oversized — the distinction matters because an idle-GPU job
# should move to a CPU-only partition, not just request fewer GPUs.
GPU_IDLE_UTILIZATION = 0.05

# Floors keep recommendations schedulable — work sized from a near-idle
# sample should still get a usable slice, not effectively zero.
_MIN_CPU_CORES = 0.01             # 10m
_MIN_MEMORY_BYTES = 16 * 1024**2  # 16Mi

_MEBIBYTE = 1024**2


def _require_target(target_utilization: float) -> None:
    if target_utilization <= 0:
        raise ValueError("target_utilization must be greater than 0")


def _recommended_cpu_cores(
    observed_cores: float,
    target_utilization: float,
) -> float:
    """Size a CPU request so observed usage lands at *target_utilization*."""

    _require_target(target_utilization)

    return max(round(observed_cores / target_utilization, 2), _MIN_CPU_CORES)


def _recommended_memory_bytes(
    observed_bytes: float,
    target_utilization: float,
) -> int:
    """Size a memory request so *peak* usage lands at *target_utilization*.

    Callers pass observed peak, not mean — memory is not compressible, so
    sizing to the average invites OOM kills.
    """

    _require_target(target_utilization)

    whole_mebibytes = math.ceil((observed_bytes / target_utilization) / _MEBIBYTE)

    return max(whole_mebibytes * _MEBIBYTE, _MIN_MEMORY_BYTES)


def _recommended_gpu_count(
    effective_gpus_used: float,
    target_utilization: float,
) -> int:
    """Size a GPU request from GPU-equivalents actually consumed.

    Unlike CPU and memory there is no floor: a result of ``0`` is the
    meaningful signal that the work never used its GPUs and belongs on a
    CPU-only partition.
    """

    _require_target(target_utilization)

    return math.ceil(effective_gpus_used / target_utilization)


def to_cpu_quantity(cores: float) -> str:
    """Format CPU cores as a Kubernetes quantity string (e.g. ``500m``)."""

    return f"{int(round(cores * 1000))}m"


def to_memory_quantity(byte_count: int) -> str:
    """Format bytes as a Kubernetes quantity string (e.g. ``125Mi``)."""

    return f"{int(round(byte_count / _MEBIBYTE))}Mi"


def _ratio(used: Optional[float], requested: float) -> Optional[float]:
    """Return used/requested, or None when either side is unknown."""

    if used is None or not requested:
        return None

    return used / requested


def _mean_of(values: List[float]) -> Optional[float]:
    """Mean of the measured values, or None when nothing was measured."""

    return sum(values) / len(values) if values else None


def _bounded(
    recommended: float,
    requested: float,
    *,
    allow_increase: bool,
    allow_decrease: bool,
):
    """Clamp a recommendation to the direction the findings actually support.

    Sizing every workload to land exactly on the target would tell a job
    running at 78% utilization to request *more* — noise at best. For GPUs
    it is actively wrong: a GPU at 92% is being used well, not starved, and
    adding GPUs cannot relieve it without data-parallel code changes.

    A workload that requested nothing at all is always advised, since there
    is no existing value to preserve.
    """

    if not requested:
        return recommended

    if recommended > requested and not allow_increase:
        return requested

    if recommended < requested and not allow_decrease:
        return requested

    return recommended


def _rationale(
    *,
    used_cpu: Optional[float],
    peak_memory: Optional[int],
    gpu_utilization: Optional[float],
    requested_cpu: float,
    requested_memory: int,
    requested_gpus: float,
    sample_count: int,
    cpu_target: float,
    memory_target: float,
    failed_oom: bool,
) -> str:
    """Build the human-readable evidence string for a recommendation."""

    parts = [
        f"Observed {used_cpu or 0:.3f} cores and "
        f"{(peak_memory or 0) / _MEBIBYTE:.0f}Mi peak memory across "
        f"{sample_count} run(s), against requests of "
        f"{requested_cpu:.3f} cores and "
        f"{requested_memory / _MEBIBYTE:.0f}Mi."
    ]

    if gpu_utilization is not None and requested_gpus:
        parts.append(
            f"GPU utilization averaged {gpu_utilization:.0%} across "
            f"{requested_gpus:.0f} allocated GPU(s)."
        )

    parts.append(
        f"Sized for {cpu_target:.0%} CPU and {memory_target:.0%} memory "
        f"utilization."
    )

    if failed_oom:
        parts.append(
            "Memory held at the current request because this workload was "
            "OOM-killed."
        )

    return " ".join(parts)


def analyze_records(
    records: Iterable[ResourceRecord],
    *,
    cpu_target_utilization: float = DEFAULT_CPU_TARGET_UTILIZATION,
    memory_target_utilization: float = DEFAULT_MEMORY_TARGET_UTILIZATION,
    gpu_target_utilization: float = DEFAULT_GPU_TARGET_UTILIZATION,
) -> Dict[str, Any]:
    """Compare requested against actual resources for every workload.

    Records sharing a ``group_key`` are aggregated: requests, CPU usage and
    GPU utilization are averaged across runs, memory takes the observed
    **peak**, and an OOM in any run marks the whole workload.
    """

    for target in (
        cpu_target_utilization,
        memory_target_utilization,
        gpu_target_utilization,
    ):
        _require_target(target)

    grouped: Dict[tuple[str, str, str], List[ResourceRecord]] = {}

    for entry in records:
        grouped.setdefault(entry.group_key, []).append(entry)

    workloads: List[Dict[str, Any]] = []

    totals = {
        "requested_cpu_cores": 0.0,
        "requested_memory_bytes": 0,
        "requested_gpu_count": 0.0,
        "used_cpu_cores": 0.0,
        "reclaimable_cpu_cores": 0.0,
        "reclaimable_memory_bytes": 0,
        "reclaimable_gpu_count": 0.0,
    }
    any_usage = False

    for (source, group, name), entries in sorted(grouped.items()):
        sample_count = len(entries)
        instance_count = max(entry.instance_count for entry in entries)

        requested_cpu = (
            sum(entry.requested_cpu_cores for entry in entries) / sample_count
        )
        requested_memory = int(
            sum(entry.requested_memory_bytes for entry in entries)
            / sample_count
        )
        requested_gpus = (
            sum(entry.requested_gpu_count for entry in entries) / sample_count
        )

        used_cpu = _mean_of(
            [e.used_cpu_cores for e in entries if e.used_cpu_cores is not None]
        )
        memory_samples = [
            e.peak_memory_bytes
            for e in entries
            if e.peak_memory_bytes is not None
        ]
        peak_memory = max(memory_samples) if memory_samples else None
        gpu_utilization = _mean_of(
            [
                e.used_gpu_utilization
                for e in entries
                if e.used_gpu_utilization is not None
            ]
        )

        effective_gpus = (
            gpu_utilization * requested_gpus
            if gpu_utilization is not None and requested_gpus
            else None
        )

        failed_oom = any(entry.failed_oom for entry in entries)
        states = sorted({entry.state for entry in entries})

        has_usage = any(
            value is not None
            for value in (used_cpu, peak_memory, gpu_utilization)
        )
        any_usage = any_usage or has_usage

        cpu_ratio = _ratio(used_cpu, requested_cpu)
        memory_ratio = _ratio(peak_memory, requested_memory)

        findings: List[str] = []

        if not requested_cpu:
            findings.append("no_cpu_requests_set")

        if not requested_memory:
            findings.append("no_memory_requests_set")

        if failed_oom:
            findings.append("oom_killed")

        if not has_usage:
            findings.append("usage_unavailable")
            recommendation = None
        else:
            if cpu_ratio is not None:
                if cpu_ratio < cpu_target_utilization:
                    findings.append("cpu_over_requested")
                elif cpu_ratio > 1.0:
                    findings.append("cpu_under_requested")

            if memory_ratio is not None:
                # An OOM-killed workload is under-sized by definition no
                # matter what the sampled peak says — the sample is
                # truncated at the moment the kernel intervened.
                if failed_oom or memory_ratio > 1.0:
                    findings.append("memory_under_requested")
                elif memory_ratio < memory_target_utilization:
                    findings.append("memory_over_requested")

            if gpu_utilization is not None and requested_gpus:
                if gpu_utilization <= GPU_IDLE_UTILIZATION:
                    findings.append("gpu_idle")
                elif gpu_utilization < gpu_target_utilization:
                    findings.append("gpu_over_requested")

            recommended_cpu = _bounded(
                _recommended_cpu_cores(used_cpu or 0.0, cpu_target_utilization),
                requested_cpu,
                allow_increase="cpu_under_requested" in findings,
                allow_decrease="cpu_over_requested" in findings,
            )
            recommended_memory = int(
                _bounded(
                    _recommended_memory_bytes(
                        peak_memory or 0, memory_target_utilization
                    ),
                    requested_memory,
                    allow_increase="memory_under_requested" in findings,
                    allow_decrease="memory_over_requested" in findings,
                )
            )

            if failed_oom:
                recommended_memory = max(recommended_memory, requested_memory)

            recommended_gpus = (
                int(
                    _bounded(
                        _recommended_gpu_count(
                            effective_gpus, gpu_target_utilization
                        ),
                        requested_gpus,
                        # GPU counts are only ever recommended downward.
                        allow_increase=False,
                        allow_decrease=True,
                    )
                )
                if effective_gpus is not None
                else int(requested_gpus)
            )

            recommendation = {
                "cpu_request": to_cpu_quantity(recommended_cpu),
                "memory_request": to_memory_quantity(recommended_memory),
                "cpu_request_cores": recommended_cpu,
                "memory_request_bytes": recommended_memory,
                "gpu_count": recommended_gpus,
                "rationale": _rationale(
                    used_cpu=used_cpu,
                    peak_memory=peak_memory,
                    gpu_utilization=gpu_utilization,
                    requested_cpu=requested_cpu,
                    requested_memory=requested_memory,
                    requested_gpus=requested_gpus,
                    sample_count=sample_count,
                    cpu_target=cpu_target_utilization,
                    memory_target=memory_target_utilization,
                    failed_oom=failed_oom,
                ),
            }

            totals["reclaimable_cpu_cores"] += max(
                (requested_cpu - recommended_cpu) * instance_count, 0.0
            )
            totals["reclaimable_memory_bytes"] += max(
                (requested_memory - recommended_memory) * instance_count, 0
            )
            totals["reclaimable_gpu_count"] += max(
                (requested_gpus - recommended_gpus) * instance_count, 0.0
            )

        totals["requested_cpu_cores"] += requested_cpu * instance_count
        totals["requested_memory_bytes"] += requested_memory * instance_count
        totals["requested_gpu_count"] += requested_gpus * instance_count

        if used_cpu is not None:
            totals["used_cpu_cores"] += used_cpu * instance_count

        workloads.append(
            {
                "source": source,
                "group": group or None,
                "name": name,
                "sample_count": sample_count,
                "instance_count": instance_count,
                "states": states,
                "requests": {
                    "cpu_cores": requested_cpu,
                    "memory_bytes": requested_memory,
                    "gpu_count": requested_gpus,
                },
                "usage": {
                    "cpu_cores": used_cpu,
                    "peak_memory_bytes": peak_memory,
                    "gpu_utilization": gpu_utilization,
                    "effective_gpus_used": effective_gpus,
                },
                "utilization": {
                    "cpu_ratio": cpu_ratio,
                    "memory_ratio": memory_ratio,
                    "gpu_ratio": gpu_utilization,
                },
                "findings": findings,
                "recommendation": recommendation,
            }
        )

    return {
        "status": "ok",
        "usage_available": any_usage,
        "targets": {
            "cpu_utilization": cpu_target_utilization,
            "memory_utilization": memory_target_utilization,
            "gpu_utilization": gpu_target_utilization,
        },
        "summary": {"workload_count": len(workloads), **totals},
        "workloads": workloads,
    }


# ====================================================================== #
# Tool entry points                                                       #
#                                                                         #
# Sources are imported lazily so a machine without the kubernetes client   #
# can still use the Slurm and CSV paths, and vice versa.                   #
# ====================================================================== #


def _load_records(
    *,
    source: str,
    namespace: Optional[str],
    csv_path: Optional[str],
    node_csv_path: Optional[str],
    jobstats_path: Optional[str],
    days_back: int,
) -> tuple[List[ResourceRecord], str, List[str]]:
    """Resolve records from whichever source is selected or reachable."""

    errors: List[str] = []

    if source == "csv" or (source == "auto" and csv_path):
        from .slurm_source import load_node_specs, records_from_csv

        if not csv_path:
            raise ValueError("csv_path is required when source='csv'")

        node_specs = load_node_specs(node_csv_path) if node_csv_path else None
        records = records_from_csv(csv_path, node_specs=node_specs)

        if jobstats_path:
            from .jobstats_source import attach_jobstats, load_jobstats

            attach_jobstats(records, load_jobstats(jobstats_path))

        return records, "csv", errors

    if source in {"slurm", "auto"}:
        from .slurm_source import query_slurm_jobs

        result = query_slurm_jobs(days_back=days_back)

        if result["status"] == "ok":
            return result["records"], "slurm", errors

        errors.append(result["error"])

        if source == "slurm":
            return [], "slurm", errors

    try:
        from .kubernetes_source import records_from_cluster

        return records_from_cluster(namespace=namespace), "kubernetes", errors
    except Exception as exc:  # noqa: BLE001 - surfaced to the caller
        errors.append(str(exc))

        if source != "auto":
            raise

    return [], "none", errors


def recommend_rightsizing(
    *,
    source: str = "auto",
    namespace: str | None = None,
    csv_path: str | None = None,
    node_csv_path: str | None = None,
    jobstats_path: str | None = None,
    days_back: int = 7,
    cpu_target_utilization: float = DEFAULT_CPU_TARGET_UTILIZATION,
    memory_target_utilization: float = DEFAULT_MEMORY_TARGET_UTILIZATION,
    gpu_target_utilization: float = DEFAULT_GPU_TARGET_UTILIZATION,
) -> Dict[str, Any]:
    """Analyze rightsizing for whichever scheduler is selected or reachable."""

    records, resolved, errors = _load_records(
        source=source,
        namespace=namespace,
        csv_path=csv_path,
        node_csv_path=node_csv_path,
        jobstats_path=jobstats_path,
        days_back=days_back,
    )

    if resolved == "none":
        return {
            "status": "unavailable",
            "errors": errors,
            "workloads": [],
            "summary": {"workload_count": 0},
        }

    report = analyze_records(
        records,
        cpu_target_utilization=cpu_target_utilization,
        memory_target_utilization=memory_target_utilization,
        gpu_target_utilization=gpu_target_utilization,
    )
    report["source"] = resolved
    report["errors"] = errors

    return report


def analyze_bottlenecks(
    *,
    source: str = "auto",
    namespace: str | None = None,
    csv_path: str | None = None,
    node_csv_path: str | None = None,
    jobstats_path: str | None = None,
    days_back: int = 7,
) -> Dict[str, Any]:
    """Identify the binding resource constraint for each workload."""

    from .bottlenecks import classify_bottlenecks

    records, resolved, errors = _load_records(
        source=source,
        namespace=namespace,
        csv_path=csv_path,
        node_csv_path=node_csv_path,
        jobstats_path=jobstats_path,
        days_back=days_back,
    )

    if resolved == "none":
        return {
            "status": "unavailable",
            "errors": errors,
            "workloads": [],
            "summary": {"record_count": 0, "top_bottleneck": None},
        }

    report = classify_bottlenecks(records)
    report["source"] = resolved
    report["errors"] = errors

    return report


def analyze_workload_families(
    *,
    source: str = "auto",
    namespace: str | None = None,
    csv_path: str | None = None,
    node_csv_path: str | None = None,
    jobstats_path: str | None = None,
    days_back: int = 7,
    similarity_threshold: float = 0.75,
    anomaly_threshold: float = 3.5,
    min_family_size: int = 4,
    use_embeddings: bool = True,
) -> Dict[str, Any]:
    """Group workloads into families and flag outliers within each.

    Peer-relative counterpart to :func:`recommend_rightsizing`: instead of
    judging a job against a fixed utilization target, it judges the job
    against other jobs like it.
    """

    from .workload_families import (
        analyze_workload_families as _group_and_score,
    )

    records, resolved, errors = _load_records(
        source=source,
        namespace=namespace,
        csv_path=csv_path,
        node_csv_path=node_csv_path,
        jobstats_path=jobstats_path,
        days_back=days_back,
    )

    if resolved == "none":
        return {
            "status": "unavailable",
            "errors": errors,
            "families": [],
            "anomalies": [],
            "summary": {"record_count": 0, "family_count": 0},
        }

    report = _group_and_score(
        records,
        similarity_threshold=similarity_threshold,
        anomaly_threshold=anomaly_threshold,
        min_family_size=min_family_size,
        use_embeddings=use_embeddings,
    )
    report["source"] = resolved
    report["errors"] = errors

    return report


def inspect_cluster_resources(
    *,
    node: str | None = None,
    provider: Any = None,
) -> Dict[str, Any]:
    """Return the Kubernetes node and cluster-level resource snapshot.

    Thin wrapper over ``KubernetesMetricsProvider.gather_metrics`` so the
    existing, well-tested cluster model is reachable from MCP.
    """

    from .providers import KubernetesMetricsProvider

    provider = provider or KubernetesMetricsProvider()
    snapshot = provider.gather_metrics()

    if node is not None:
        snapshot = {
            **snapshot,
            "nodes": [
                entry for entry in snapshot["nodes"] if entry["name"] == node
            ],
        }

    return snapshot
