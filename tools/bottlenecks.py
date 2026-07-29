"""Bottleneck classification over normalized resource records.

Answers "which resource actually limits this work?", as distinct from
rightsizing's "is this work the right size?". A job can be simultaneously
over-requested on CPU and bottlenecked on memory; the two analyses are
reported separately because they imply different remedies — change the
request, change the node class, or change the code.

Pure: no I/O, no scheduler imports.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, Iterable, List, Optional

from .resource_records import ResourceRecord

# A resource is "saturated" above this fraction of its allocation, and has
# "slack" below the low-water mark. Both are parameters on the public entry
# point; these are only the documented defaults.
DEFAULT_SATURATION = 0.80
DEFAULT_SLACK = 0.50
DEFAULT_GPU_IDLE = 0.05

# A node whose memory-per-core ratio far exceeds what the work used is a
# placement problem, not a sizing problem.
NODE_CLASS_OVERSIZE_FACTOR = 4.0


def _ratio(used: Optional[float], requested: float) -> Optional[float]:
    if used is None or not requested:
        return None

    return used / requested


def _classify_one(
    entry: ResourceRecord,
    *,
    saturation: float,
    slack: float,
    gpu_idle: float,
) -> Dict[str, Any]:
    """Return the bottleneck verdict and supporting notes for one record."""

    cpu_ratio = _ratio(entry.used_cpu_cores, entry.requested_cpu_cores)
    memory_ratio = _ratio(
        entry.peak_memory_bytes, entry.requested_memory_bytes
    )
    gpu_ratio = entry.used_gpu_utilization

    notes: List[str] = []

    # An allocated-but-idle GPU outranks every other finding: it is both
    # the largest waste and the easiest to act on.
    if entry.requested_gpu_count and gpu_ratio is not None:
        if gpu_ratio <= gpu_idle:
            return {
                "bottleneck": "gpu_idle",
                "notes": notes,
                "ratios": {
                    "cpu": cpu_ratio,
                    "memory": memory_ratio,
                    "gpu": gpu_ratio,
                },
            }

    # An OOM kill is definitive evidence of a memory constraint, and
    # outranks the sampled peak, which is truncated at the kill.
    if entry.failed_oom:
        bottleneck = "memory_bound"
    elif cpu_ratio is None and memory_ratio is None and gpu_ratio is None:
        bottleneck = "unknown"
    else:
        cpu_saturated = cpu_ratio is not None and cpu_ratio >= saturation
        memory_saturated = (
            memory_ratio is not None and memory_ratio >= saturation
        )
        gpu_saturated = gpu_ratio is not None and gpu_ratio >= saturation

        cpu_slack = cpu_ratio is not None and cpu_ratio < slack
        memory_slack = memory_ratio is not None and memory_ratio < slack

        if memory_saturated and not cpu_saturated:
            bottleneck = "memory_bound"
        elif cpu_saturated and not memory_saturated:
            bottleneck = "cpu_bound"
        elif gpu_saturated:
            bottleneck = "gpu_bound"
        elif cpu_saturated and memory_saturated:
            bottleneck = "cpu_and_memory_bound"
        elif cpu_slack and memory_slack:
            bottleneck = "oversized"
        else:
            bottleneck = "well_matched"

    # Placement checks — only meaningful when layer-3 node specs are joined.
    node_spec = entry.node_spec

    if node_spec is not None and entry.peak_memory_bytes is not None:
        memory_per_core = node_spec.memory_bytes_per_core

        if memory_per_core and entry.requested_cpu_cores:
            used_per_core = entry.peak_memory_bytes / entry.requested_cpu_cores

            if used_per_core * NODE_CLASS_OVERSIZE_FACTOR < memory_per_core:
                notes.append("node_class_oversized")

    if node_spec is not None and not entry.requested_gpu_count:
        if node_spec.gpu_count:
            notes.append("gpu_node_used_without_gpu_request")

    return {
        "bottleneck": bottleneck,
        "notes": notes,
        "ratios": {
            "cpu": cpu_ratio,
            "memory": memory_ratio,
            "gpu": gpu_ratio,
        },
    }


def classify_bottlenecks(
    records: Iterable[ResourceRecord],
    *,
    saturation: float = DEFAULT_SATURATION,
    slack: float = DEFAULT_SLACK,
    gpu_idle: float = DEFAULT_GPU_IDLE,
) -> Dict[str, Any]:
    """Classify the binding constraint for each record and roll up totals."""

    workloads: List[Dict[str, Any]] = []
    counts: Counter = Counter()
    by_partition: Dict[str, Counter] = {}

    for entry in records:
        verdict = _classify_one(
            entry,
            saturation=saturation,
            slack=slack,
            gpu_idle=gpu_idle,
        )

        counts[verdict["bottleneck"]] += 1

        partition = entry.partition or "unknown"
        by_partition.setdefault(partition, Counter())[
            verdict["bottleneck"]
        ] += 1

        workloads.append(
            {
                "source": entry.source,
                "group": entry.group,
                "name": entry.workload_name,
                "partition": entry.partition,
                "state": entry.state,
                **verdict,
            }
        )

    top = counts.most_common(1)

    return {
        "status": "ok",
        "thresholds": {
            "saturation": saturation,
            "slack": slack,
            "gpu_idle": gpu_idle,
        },
        "summary": {
            "record_count": len(workloads),
            "by_bottleneck": dict(counts),
            "by_partition": {
                name: dict(counter) for name, counter in by_partition.items()
            },
            "top_bottleneck": top[0][0] if top else None,
        },
        "workloads": workloads,
    }
