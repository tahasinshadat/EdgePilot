"""The contract between resource sources and the analysis engines.

Three types mirror the three linked data layers requested in the Quest
data-use proposal:

* :class:`UsageSample`    — layer 1, per-interval Jobstats time-series
* :class:`ResourceRecord` — layer 2, sacct accounting for one unit of work
* :class:`NodeSpec`       — layer 3, hardware specs for the nodes work ran on

Sources normalize into these; the engines consume only these. Nothing here
imports a scheduler client or performs I/O.

``None`` consistently means *not measured*, never zero. The engines report
a missing measurement rather than estimating it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class UsageSample:
    """One interval of observed usage for a single unit of work.

    ``offset_seconds`` is measured from job start, which keeps samples
    usable after timestamps are anonymized.
    """

    offset_seconds: float
    cpu_cores: Optional[float] = None
    memory_bytes: Optional[int] = None
    gpu_utilization: Optional[float] = None      # fraction 0.0-1.0
    gpu_memory_bytes: Optional[int] = None
    node: Optional[str] = None


@dataclass
class NodeSpec:
    """Hardware specification for a compute node."""

    name: str
    cpu_cores: int = 0
    memory_bytes: int = 0
    gpu_count: int = 0
    gpu_model: Optional[str] = None
    gpu_memory_bytes: int = 0
    hardware_class: Optional[str] = None
    partition: Optional[str] = None

    @property
    def memory_bytes_per_core(self) -> Optional[float]:
        """Memory-to-core ratio, the signal for node-class fit."""

        if not self.cpu_cores:
            return None

        return self.memory_bytes / self.cpu_cores


@dataclass
class ResourceRecord:
    """One unit of scheduled work, normalized across schedulers.

    Attributes
    ----------
    workload_name:
        Stable name shared by repeated runs — a Slurm ``JobName`` or a
        Kubernetes Deployment name. Records sharing
        ``(source, group, workload_name)`` are aggregated together.
    group:
        Namespace, account, or partition. Anonymized upstream.
    instance_count:
        Nodes for a Slurm job, Pods for a Kubernetes workload.
    used_cpu_cores / peak_memory_bytes / used_gpu_utilization:
        ``None`` means *not measured*.
    samples:
        Layer-1 time-series, when available. Sources that provide samples
        should also populate the scalar summaries derived from them.
    """

    source: str
    workload_name: str
    requested_cpu_cores: float
    requested_memory_bytes: int

    group: Optional[str] = None
    record_id: Optional[str] = None
    instance_count: int = 1

    requested_gpu_count: float = 0.0

    used_cpu_cores: Optional[float] = None
    peak_cpu_cores: Optional[float] = None
    peak_memory_bytes: Optional[int] = None
    used_gpu_utilization: Optional[float] = None
    peak_gpu_memory_bytes: Optional[int] = None

    state: str = "UNKNOWN"
    failed_oom: bool = False
    elapsed_seconds: Optional[float] = None

    partition: Optional[str] = None
    qos: Optional[str] = None
    nodes: List[str] = field(default_factory=list)
    node_spec: Optional[NodeSpec] = None
    samples: List[UsageSample] = field(default_factory=list)

    containers: List[str] = field(default_factory=list)
    labels: Dict[str, Any] = field(default_factory=dict)

    @property
    def group_key(self) -> tuple[str, str, str]:
        """Key used to aggregate repeated runs of the same workload."""

        return (self.source, self.group or "", self.workload_name)

    @property
    def effective_gpus_used(self) -> Optional[float]:
        """GPU-equivalents actually consumed.

        Four GPUs at 10% mean utilization is 0.4 effective GPUs — the
        quantity a corrected GPU request should be sized from.
        """

        if self.used_gpu_utilization is None or not self.requested_gpu_count:
            return None

        return self.used_gpu_utilization * self.requested_gpu_count
