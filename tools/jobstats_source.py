"""Per-interval job time-series (layer 1 of the Quest dataset).

Jobstats-style samples reveal usage *shape*, which accounting summaries
cannot: a job averaging 4 cores may have used 16 for five minutes and 1 for
three hours. Attaching samples to a record replaces its scalar summaries
with statistics derived from the series.

The exact Quest export schema is not yet fixed. :data:`FIELD_ALIASES` is the
single place to remap column names when it is.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from statistics import mean
from typing import Any, Dict, Iterable, List, Optional, Sequence

from .resource_records import ResourceRecord, UsageSample

logger = logging.getLogger(__name__)

# Remap here when the Quest export schema is confirmed.
FIELD_ALIASES = {
    "offset": ("offset", "offset_seconds", "t", "timestamp"),
    "cpu_cores": ("cpu_cores", "cpus", "cpu"),
    "memory_bytes": ("memory_bytes", "mem", "rss"),
    "gpu_utilization": ("gpu_utilization", "gpu_util", "gpu"),
    "gpu_memory_bytes": ("gpu_memory_bytes", "gpu_mem"),
}


def _first_present(row: Dict[str, Any], names: Sequence[str]) -> Any:
    for name in names:
        if name in row and row[name] is not None:
            return row[name]

    return None


def _as_fraction(value: Any) -> Optional[float]:
    """Normalize a GPU utilization reading to a 0.0-1.0 fraction.

    Jobstats reports percentages; values above 1 are divided by 100.
    """

    if value is None:
        return None

    number = float(value)

    return number / 100.0 if number > 1.0 else number


def _percentile(values: Sequence[float], fraction: float) -> float:
    """Nearest-rank percentile — no interpolation, no numpy dependency."""

    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, round(fraction * len(ordered)) - 1))

    return ordered[index]


def load_jobstats(path: str) -> Dict[str, List[UsageSample]]:
    """Load per-job time-series keyed by job ID."""

    source = Path(path)

    if not source.exists():
        raise FileNotFoundError(f"Jobstats file not found: {path}")

    payload = json.loads(source.read_text(encoding="utf-8"))
    series: Dict[str, List[UsageSample]] = {}

    for job in payload.get("jobs", []):
        job_id = str(job.get("job_id", "")).strip()

        if not job_id:
            continue

        nodes = job.get("nodes") or []
        samples: List[UsageSample] = []

        for row in job.get("samples", []):
            cpu = _first_present(row, FIELD_ALIASES["cpu_cores"])
            memory = _first_present(row, FIELD_ALIASES["memory_bytes"])
            gpu_memory = _first_present(row, FIELD_ALIASES["gpu_memory_bytes"])

            samples.append(
                UsageSample(
                    offset_seconds=float(
                        _first_present(row, FIELD_ALIASES["offset"]) or 0
                    ),
                    cpu_cores=float(cpu) if cpu is not None else None,
                    memory_bytes=int(memory) if memory is not None else None,
                    gpu_utilization=_as_fraction(
                        _first_present(row, FIELD_ALIASES["gpu_utilization"])
                    ),
                    gpu_memory_bytes=(
                        int(gpu_memory) if gpu_memory is not None else None
                    ),
                    node=nodes[0] if nodes else None,
                )
            )

        series[job_id] = samples

    logger.info("Loaded time-series for %d jobs", len(series))

    return series


def summarize_samples(samples: Iterable[UsageSample]) -> Dict[str, Any]:
    """Derive mean / p95 / peak statistics from a usage series."""

    samples = list(samples)

    def stats(values: List[float]) -> tuple:
        if not values:
            return (None, None, None)

        return (mean(values), _percentile(values, 0.95), max(values))

    cpu_mean, cpu_p95, cpu_peak = stats(
        [s.cpu_cores for s in samples if s.cpu_cores is not None]
    )
    memory_mean, memory_p95, memory_peak = stats(
        [s.memory_bytes for s in samples if s.memory_bytes is not None]
    )
    gpu_mean, gpu_p95, gpu_peak = stats(
        [s.gpu_utilization for s in samples if s.gpu_utilization is not None]
    )
    _, _, gpu_memory_peak = stats(
        [s.gpu_memory_bytes for s in samples if s.gpu_memory_bytes is not None]
    )

    return {
        "sample_count": len(samples),
        "cpu_mean": cpu_mean,
        "cpu_p95": cpu_p95,
        "cpu_peak": cpu_peak,
        "memory_mean": memory_mean,
        "memory_p95": memory_p95,
        "memory_peak": memory_peak,
        "gpu_mean": gpu_mean,
        "gpu_p95": gpu_p95,
        "gpu_peak": gpu_peak,
        "gpu_memory_peak": gpu_memory_peak,
    }


def attach_jobstats(
    records: Iterable[ResourceRecord],
    series: Dict[str, List[UsageSample]],
) -> List[ResourceRecord]:
    """Attach time-series to records and refresh their scalar summaries.

    Measured series are strictly better evidence than accounting summaries,
    so they replace ``used_cpu_cores``, ``peak_memory_bytes`` and the GPU
    fields. Records with no matching series are left untouched.
    """

    records = list(records)
    matched = 0

    for record in records:
        samples = series.get(str(record.record_id or ""))

        if not samples:
            continue

        matched += 1
        record.samples = samples

        summary = summarize_samples(samples)

        if summary["cpu_mean"] is not None:
            record.used_cpu_cores = summary["cpu_mean"]
            record.peak_cpu_cores = summary["cpu_peak"]

        if summary["memory_peak"] is not None:
            record.peak_memory_bytes = int(summary["memory_peak"])

        if summary["gpu_mean"] is not None:
            record.used_gpu_utilization = summary["gpu_mean"]

        if summary["gpu_memory_peak"] is not None:
            record.peak_gpu_memory_bytes = int(summary["gpu_memory_peak"])

    logger.info("Attached time-series to %d records", matched)

    return records
