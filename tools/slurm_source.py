"""Slurm accounting as normalized resource records.

Reads completed-job accounting from ``sacct`` — or from a CSV export with
the same column names, which is how Northwestern Quest data is expected to
arrive. Both paths converge on :func:`records_from_rows`, so CSV replay is
a genuine rehearsal of the live path rather than a separate code path.

Logging here is deliberately aggregate-only: no job ID, user or account is
written above DEBUG, because the dataset is anonymized under a data-use
agreement.
"""

from __future__ import annotations

import csv
import logging
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .resource_records import NodeSpec, ResourceRecord

logger = logging.getLogger(__name__)

# Slurm reports memory with binary suffixes and no trailing "B".
_MEMORY_SUFFIXES = {
    "K": 1024,
    "M": 1024**2,
    "G": 1024**3,
    "T": 1024**4,
    "P": 1024**5,
}

_OOM_STATES = {"OUT_OF_MEMORY", "OOM"}

SACCT_FIELDS = (
    "JobID,JobName,State,ExitCode,ReqTRES,AllocTRES,MaxRSS,TotalCPU,"
    "Elapsed,NNodes,NodeList,Partition,QOS,Account"
)


def parse_slurm_memory(raw: str) -> int:
    """Convert a Slurm memory quantity (``2048K``, ``1.5G``) to bytes."""

    text = (raw or "").strip()

    if not text:
        return 0

    multiplier = 1
    if text[-1].upper() in _MEMORY_SUFFIXES:
        multiplier = _MEMORY_SUFFIXES[text[-1].upper()]
        text = text[:-1]

    try:
        return int(float(text) * multiplier)
    except ValueError:
        return 0


def parse_slurm_duration(raw: str) -> float:
    """Convert a Slurm duration to seconds.

    Handles ``DD-HH:MM:SS``, ``HH:MM:SS`` and ``MM:SS.mmm``.
    """

    text = (raw or "").strip()

    if not text:
        return 0.0

    days = 0.0
    if "-" in text:
        day_part, _, text = text.partition("-")
        try:
            days = float(day_part)
        except ValueError:
            return 0.0

    try:
        values = [float(part) for part in text.split(":")]
    except ValueError:
        return 0.0

    if len(values) == 3:
        hours, minutes, seconds = values
    elif len(values) == 2:
        hours = 0.0
        minutes, seconds = values
    elif len(values) == 1:
        hours = minutes = 0.0
        seconds = values[0]
    else:
        return 0.0

    return days * 86400 + hours * 3600 + minutes * 60 + seconds


def parse_tres(raw: str) -> Dict[str, Any]:
    """Parse a Slurm TRES string such as ``cpu=4,mem=32G,gres/gpu:a100=2``.

    Memory is returned in bytes under ``mem``; GPU count is normalized to
    ``gpu`` regardless of whether the GRES was typed, with any GPU model
    surfaced separately as ``gpu_model``.
    """

    parsed: Dict[str, Any] = {}

    for token in (raw or "").split(","):
        key, separator, value = token.partition("=")

        if not separator:
            continue

        key = key.strip()
        value = value.strip()

        if key == "mem":
            parsed["mem"] = parse_slurm_memory(value)
            continue

        if key.startswith("gres/gpu"):
            _, _, model = key.partition(":")

            if model:
                parsed["gpu_model"] = model

            key = "gpu"

        try:
            parsed[key] = float(re.sub(r"[^0-9.\-]", "", value) or 0)
        except ValueError:
            continue

    return parsed


def expand_node_list(raw: str) -> List[str]:
    """Expand a Slurm hostlist such as ``qnode[0103-0106]``.

    Handles the bracketed range and comma forms Slurm emits in NodeList.
    """

    text = (raw or "").strip().strip('"')

    if not text or text in {"None assigned", "(null)"}:
        return []

    match = re.match(r"^([^\[]+)\[([^\]]+)\]$", text)

    if not match:
        return [part for part in text.split(",") if part]

    prefix, body = match.groups()
    names: List[str] = []

    for part in body.split(","):
        if "-" in part:
            start, _, end = part.partition("-")
            width = len(start)

            for value in range(int(start), int(end) + 1):
                names.append(f"{prefix}{value:0{width}d}")
        else:
            names.append(f"{prefix}{part}")

    return names


def load_node_specs(csv_path: str) -> Dict[str, NodeSpec]:
    """Load layer-3 node specifications keyed by node name."""

    path = Path(csv_path)

    if not path.exists():
        raise FileNotFoundError(f"Node spec file not found: {csv_path}")

    def as_int(value: Optional[str]) -> int:
        try:
            return int(float(value or 0))
        except ValueError:
            return 0

    specs: Dict[str, NodeSpec] = {}

    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            name = (row.get("NodeName") or "").strip()

            if not name:
                continue

            gpu_count = 0
            gpu_model: Optional[str] = None
            gres = (row.get("Gres") or "").strip()

            if gres.startswith("gpu"):
                parts = gres.split(":")

                if len(parts) == 3:
                    gpu_model = parts[1]
                    gpu_count = as_int(parts[2])
                elif len(parts) == 2:
                    gpu_count = as_int(parts[1])

            specs[name] = NodeSpec(
                name=name,
                cpu_cores=as_int(row.get("CPUs")),
                memory_bytes=as_int(row.get("RealMemory")),
                gpu_count=gpu_count,
                gpu_model=gpu_model,
                gpu_memory_bytes=as_int(row.get("GpuMemory")),
                hardware_class=(row.get("HardwareClass") or "").strip() or None,
                partition=(row.get("Partition") or "").strip() or None,
            )

    logger.info("Loaded %d node specifications", len(specs))

    return specs


def _is_step_row(job_id: str) -> bool:
    """Return True for ``sacct`` step rows such as ``1001.batch``."""

    return "." in job_id


def records_from_rows(
    rows: Iterable[Dict[str, str]],
    node_specs: Optional[Dict[str, NodeSpec]] = None,
) -> List[ResourceRecord]:
    """Normalize ``sacct``-shaped rows into resource records.

    Accepts rows from either ``sacct --parsable2`` or a CSV export with the
    same column names. Step rows (``1001.batch``) are not emitted as
    records; their ``MaxRSS`` folds into the parent job, because that is
    the only place Slurm reports peak memory for a completed job.
    """

    parents: Dict[str, Dict[str, str]] = {}
    step_peak_memory: Dict[str, int] = {}
    order: List[str] = []

    for row in rows:
        job_id = (row.get("JobID") or "").strip()

        if not job_id:
            continue

        memory = parse_slurm_memory(row.get("MaxRSS", ""))
        parent = job_id.split(".", 1)[0]

        if memory:
            step_peak_memory[parent] = max(
                step_peak_memory.get(parent, 0), memory
            )

        if _is_step_row(job_id):
            continue

        if job_id not in parents:
            order.append(job_id)

        parents[job_id] = row

    records: List[ResourceRecord] = []

    for job_id in order:
        row = parents[job_id]

        requested = parse_tres(row.get("ReqTRES", ""))
        allocated = parse_tres(row.get("AllocTRES", ""))

        requested_cpu = float(requested.get("cpu", allocated.get("cpu", 0.0)))
        requested_memory = int(requested.get("mem", allocated.get("mem", 0)))
        requested_gpus = float(requested.get("gpu", allocated.get("gpu", 0.0)))

        elapsed = parse_slurm_duration(row.get("Elapsed", ""))
        total_cpu = parse_slurm_duration(row.get("TotalCPU", ""))

        # Average cores actually consumed — the quantity `seff` reports as
        # CPU efficiency, before dividing by the allocation.
        used_cpu = total_cpu / elapsed if elapsed > 0 else None

        state = (row.get("State") or "UNKNOWN").strip().split(" ")[0]
        nodes = expand_node_list(row.get("NodeList", ""))

        try:
            node_count = int(float(row.get("NNodes") or 1))
        except ValueError:
            node_count = 1

        node_spec = None
        if node_specs and nodes:
            node_spec = node_specs.get(nodes[0])

        records.append(
            ResourceRecord(
                source="slurm",
                record_id=job_id,
                workload_name=(row.get("JobName") or job_id).strip(),
                group=(row.get("Account") or "").strip() or None,
                requested_cpu_cores=requested_cpu,
                requested_memory_bytes=requested_memory,
                requested_gpu_count=requested_gpus,
                instance_count=node_count,
                used_cpu_cores=used_cpu,
                peak_memory_bytes=step_peak_memory.get(job_id),
                state=state,
                failed_oom=state in _OOM_STATES,
                elapsed_seconds=elapsed,
                partition=(row.get("Partition") or "").strip() or None,
                qos=(row.get("QOS") or "").strip() or None,
                nodes=nodes,
                node_spec=node_spec,
                labels={
                    "exit_code": (row.get("ExitCode") or "").strip(),
                    "gpu_model": requested.get("gpu_model"),
                },
            )
        )

    logger.info("Normalized %d Slurm job records", len(records))

    return records


def records_from_csv(
    csv_path: str,
    node_specs: Optional[Dict[str, NodeSpec]] = None,
) -> List[ResourceRecord]:
    """Load resource records from a ``sacct``-shaped CSV export.

    This is the path Quest data is expected to arrive on. TRES columns
    contain commas, so the export must be properly quoted.
    """

    path = Path(csv_path)

    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    with path.open(newline="", encoding="utf-8") as handle:
        return records_from_rows(list(csv.DictReader(handle)), node_specs)


def query_slurm_jobs(
    days_back: int = 7,
    account: Optional[str] = None,
    partition: Optional[str] = None,
) -> Dict[str, Any]:
    """Return recent completed jobs from ``sacct`` as resource records.

    Returns ``{"status": "unavailable"}`` rather than raising when Slurm is
    absent, so a non-cluster machine degrades cleanly.
    """

    command = [
        "sacct",
        "-S",
        f"now-{days_back}days",
        "--format",
        SACCT_FIELDS,
        "--parsable2",
        "--noheader",
        # Keep Slurm from rounding memory units, so parse_slurm_memory is
        # exact rather than reading a pre-rounded "16G".
        "--noconvert",
    ]

    if account:
        command.extend(["-A", account])

    if partition:
        command.extend(["-r", partition])

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except FileNotFoundError:
        return {
            "status": "unavailable",
            "error": (
                "sacct is not available on this machine — Slurm accounting "
                "can only be queried from a cluster login node."
            ),
            "records": [],
        }
    except subprocess.TimeoutExpired:
        return {
            "status": "unavailable",
            "error": "sacct timed out after 120 seconds.",
            "records": [],
        }

    if completed.returncode != 0:
        return {
            "status": "unavailable",
            "error": f"sacct failed: {completed.stderr.strip()}",
            "records": [],
        }

    columns = SACCT_FIELDS.split(",")
    rows = [
        dict(zip(columns, line.split("|")))
        for line in completed.stdout.splitlines()
        if line.strip()
    ]

    return {"status": "ok", "records": records_from_rows(rows)}
