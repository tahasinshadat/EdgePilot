"""Group jobs into workload families and flag outliers within them.

Fixed thresholds ("below 70% utilization is wasteful") are blunt: a
simulation that genuinely needs 5% of its cores looks identical to one that
was over-requested by a factor of twenty. Comparing a job against *its own
peers* is a far stronger signal — "this run asked for four times the memory
of the other 37 jobs in its family" needs no arbitrary constant to be
meaningful.

Families are built with a local sentence-embedding model so that
semantically related names group together (``train_net`` with
``train_network``). The model is optional: when it is missing or cannot be
loaded, grouping falls back to normalized exact names and the report says
so. Nothing here calls a hosted LLM, and results are deterministic for a
given input.
"""

from __future__ import annotations

import logging
import re
import statistics
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

import numpy as np

from .resource_records import ResourceRecord

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "all-MiniLM-L6-v2"

DEFAULT_SIMILARITY_THRESHOLD = 0.75

# Iglewicz & Hoaglin's modified z-score. 3.5 is their recommended cutoff;
# the constants make the median absolute deviation a consistent estimator
# of the standard deviation for normally distributed data.
DEFAULT_ANOMALY_THRESHOLD = 3.5
_MAD_SCALE = 0.6745
_MEAN_AD_SCALE = 0.7979

# Below this many members a "median" is not meaningful enough to call
# anything an outlier against.
DEFAULT_MIN_FAMILY_SIZE = 4

ANOMALY_METRICS = (
    "cpu_utilization",
    "memory_utilization",
    "gpu_utilization",
    "peak_memory_bytes",
)

Embedder = Callable[[Sequence[str]], np.ndarray]


# ====================================================================== #
# Descriptors and the optional local model                                #
# ====================================================================== #


def normalized_name(name: str) -> str:
    """Strip run-specific suffixes so repeated runs group together."""

    text = (name or "").strip().lower()
    stripped = re.sub(r"[_\-.]?\d+$", "", text)

    return stripped or text


def build_descriptor(record: ResourceRecord) -> str:
    """Text embedded to group a job by *what it is*.

    Deliberately excludes the resource request. Families are formed from
    workload identity and then judged on what they asked for; folding the
    request into the descriptor would make that comparison circular —
    over-requested jobs would cluster with each other and look normal.
    """

    parts = [record.workload_name or ""]

    if record.group:
        parts.append(f"account {record.group}")

    if record.partition:
        parts.append(f"partition {record.partition}")

    return " ".join(part for part in parts if part)


def load_embedder() -> Optional[Embedder]:
    """Return a local embedding function, or None when unavailable.

    Degrades on both a missing package and a model that cannot be loaded
    (no network on a compute node, for instance), so callers never have to
    special-case an offline machine.
    """

    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        logger.info(
            "sentence-transformers is not installed — workload families "
            "fall back to name grouping."
        )
        return None

    try:
        model = SentenceTransformer(EMBEDDING_MODEL)
    except Exception as exc:  # noqa: BLE001 - any load failure degrades
        logger.warning(
            "Could not load embedding model '%s' (%s) — workload families "
            "fall back to name grouping.",
            EMBEDDING_MODEL,
            exc,
        )
        return None

    def embed(texts: Sequence[str]) -> np.ndarray:
        return np.asarray(
            model.encode(list(texts), normalize_embeddings=True),
            dtype=np.float32,
        )

    return embed


# ====================================================================== #
# Clustering                                                              #
# ====================================================================== #


def _record_key(record: ResourceRecord, index: int) -> str:
    """Stable identifier for a record, even when it carries no id."""

    return str(record.record_id or f"{record.workload_name}#{index}")


def _cluster_by_name(
    records: Sequence[ResourceRecord],
) -> List[List[int]]:
    """Fallback grouping: normalized exact names."""

    buckets: Dict[str, List[int]] = {}

    for index, record in enumerate(records):
        buckets.setdefault(normalized_name(record.workload_name), []).append(
            index
        )

    return [buckets[key] for key in sorted(buckets)]


def _cluster_by_embedding(
    records: Sequence[ResourceRecord],
    embedder: Embedder,
    similarity_threshold: float,
) -> List[List[int]]:
    """Greedy centroid clustering over descriptor embeddings.

    Greedy rather than k-means because the number of workload families is
    not known in advance, and because a single pass over pre-sorted input
    is deterministic — the same jobs always produce the same families.
    """

    vectors = embedder([build_descriptor(record) for record in records])

    if vectors.ndim != 2 or len(vectors) != len(records):
        raise ValueError(
            f"embedder returned {getattr(vectors, 'shape', None)} for "
            f"{len(records)} records; expected a 2-D array with one row each"
        )

    centroids: List[np.ndarray] = []
    members: List[List[int]] = []

    for index, vector in enumerate(vectors):
        best_cluster = -1
        best_score = -1.0

        for cluster, centroid in enumerate(centroids):
            score = float(np.dot(vector, centroid))

            if score > best_score:
                best_cluster, best_score = cluster, score

        if best_cluster >= 0 and best_score >= similarity_threshold:
            members[best_cluster].append(index)
            mean = np.mean(vectors[members[best_cluster]], axis=0)
            norm = float(np.linalg.norm(mean)) or 1.0
            centroids[best_cluster] = mean / norm
        else:
            centroids.append(vector)
            members.append([index])

    return members


def _family_label(
    records: Sequence[ResourceRecord],
    indices: Sequence[int],
) -> str:
    """Name a family after its most common normalized member name."""

    counts: Dict[str, int] = {}

    for index in indices:
        name = normalized_name(records[index].workload_name)
        counts[name] = counts.get(name, 0) + 1

    # Sort by frequency then name so ties resolve deterministically.
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


# ====================================================================== #
# Metrics and outliers                                                    #
# ====================================================================== #


def _ratio(used: Optional[float], requested: float) -> Optional[float]:
    if used is None or not requested:
        return None

    return used / requested


def metric_value(record: ResourceRecord, metric: str) -> Optional[float]:
    """Return one comparable metric for a record, or None if unmeasured."""

    if metric == "cpu_utilization":
        return _ratio(record.used_cpu_cores, record.requested_cpu_cores)

    if metric == "memory_utilization":
        return _ratio(record.peak_memory_bytes, record.requested_memory_bytes)

    if metric == "gpu_utilization":
        return record.used_gpu_utilization

    if metric == "peak_memory_bytes":
        return (
            float(record.peak_memory_bytes)
            if record.peak_memory_bytes is not None
            else None
        )

    raise ValueError(f"Unknown metric: {metric}")


def modified_z_scores(values: Sequence[float]) -> List[float]:
    """Robust outlier scores based on the median absolute deviation.

    The median and MAD are used rather than the mean and standard
    deviation because a handful of extreme jobs — exactly what we are
    hunting — would inflate a standard deviation enough to hide
    themselves.
    """

    if len(values) < 2:
        return [0.0] * len(values)

    median = statistics.median(values)
    deviations = [abs(value - median) for value in values]
    mad = statistics.median(deviations)

    if mad > 0:
        return [_MAD_SCALE * (value - median) / mad for value in values]

    # More than half the family is identical: MAD collapses to zero and the
    # standard formula divides by it. Fall back to the mean deviation.
    mean_deviation = sum(deviations) / len(deviations)

    if mean_deviation == 0:
        return [0.0] * len(values)

    return [
        _MEAN_AD_SCALE * (value - median) / mean_deviation for value in values
    ]


# ====================================================================== #
# Public entry point                                                      #
# ====================================================================== #


def analyze_workload_families(
    records: Iterable[ResourceRecord],
    *,
    similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    anomaly_threshold: float = DEFAULT_ANOMALY_THRESHOLD,
    min_family_size: int = DEFAULT_MIN_FAMILY_SIZE,
    embedder: Optional[Embedder] = None,
    use_embeddings: bool = True,
) -> Dict[str, Any]:
    """Group records into families and flag outliers within each.

    Pass ``embedder`` to supply your own embedding function; otherwise the
    local model is loaded on demand. ``use_embeddings=False`` forces the
    deterministic name-based fallback.
    """

    # Sorting first makes greedy clustering independent of input order, so
    # the same set of jobs always yields the same families.
    records = sorted(
        records,
        key=lambda record: (
            normalized_name(record.workload_name),
            str(record.record_id or ""),
        ),
    )

    if not records:
        return {
            "status": "ok",
            "method": "name",
            "model": None,
            "degraded": False,
            "degraded_reason": None,
            "families": [],
            "anomalies": [],
            "summary": {
                "record_count": 0,
                "family_count": 0,
                "anomaly_count": 0,
            },
        }

    degraded_reason: Optional[str] = None

    if not use_embeddings:
        resolved_embedder = None
        degraded_reason = "embeddings disabled by caller"
    else:
        resolved_embedder = embedder if embedder is not None else load_embedder()

        if resolved_embedder is None:
            degraded_reason = (
                f"local embedding model '{EMBEDDING_MODEL}' unavailable; "
                f"grouped by normalized job name instead"
            )

    if resolved_embedder is None:
        method = "name"
        clusters = _cluster_by_name(records)
    else:
        method = "embedding"
        clusters = _cluster_by_embedding(
            records, resolved_embedder, similarity_threshold
        )

    families: List[Dict[str, Any]] = []
    anomalies: List[Dict[str, Any]] = []

    for cluster_index, indices in enumerate(clusters):
        label = _family_label(records, indices)
        members = [
            _record_key(records[index], index) for index in indices
        ]

        medians: Dict[str, Optional[float]] = {}

        for metric in ANOMALY_METRICS:
            measured = [
                (index, metric_value(records[index], metric))
                for index in indices
            ]
            measured = [
                (index, value) for index, value in measured if value is not None
            ]

            medians[metric] = (
                statistics.median([value for _, value in measured])
                if measured
                else None
            )

            if len(measured) < min_family_size:
                continue

            scores = modified_z_scores([value for _, value in measured])

            for (index, value), score in zip(measured, scores):
                if abs(score) < anomaly_threshold:
                    continue

                record = records[index]
                anomalies.append(
                    {
                        "record_id": _record_key(record, index),
                        "workload_name": record.workload_name,
                        "family": label,
                        "partition": record.partition,
                        "state": record.state,
                        "metric": metric,
                        "value": value,
                        "family_median": medians[metric],
                        "score": round(score, 2),
                        "direction": "high" if score > 0 else "low",
                    }
                )

        families.append(
            {
                "family_id": cluster_index,
                "label": label,
                "size": len(indices),
                "members": members,
                "median": medians,
            }
        )

    anomalies.sort(key=lambda item: (-abs(item["score"]), item["record_id"]))

    return {
        "status": "ok",
        "method": method,
        "model": EMBEDDING_MODEL if method == "embedding" else None,
        "degraded": method != "embedding",
        "degraded_reason": degraded_reason,
        "thresholds": {
            "similarity": similarity_threshold,
            "anomaly_score": anomaly_threshold,
            "min_family_size": min_family_size,
        },
        "families": families,
        "anomalies": anomalies,
        "summary": {
            "record_count": len(records),
            "family_count": len(families),
            "anomaly_count": len(anomalies),
            "largest_family": max(
                (family["size"] for family in families), default=0
            ),
        },
    }
