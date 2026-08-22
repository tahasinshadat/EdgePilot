"""Deterministic synthetic clusters for token-scaling experiments."""

from __future__ import annotations

from typing import Any


SUPPORTED_NODE_COUNTS = (10, 100, 1000)

_GIBIBYTE = 1024**3


def _build_node(index: int) -> dict[str, Any]:
    return {
        "name": f"edgepilot-worker-{index:04d}",
        "ready": True,
        "schedulable": True,
        "allocatable": {
            "cpu_cores": 8.0,
            "memory_bytes": 16 * _GIBIBYTE,
            "pods": 110,
        },
        "requested": {
            "cpu_cores": 2.0,
            "memory_bytes": 4 * _GIBIBYTE,
            "pods": 20,
        },
    }


def build_cluster_fixture(node_count: int) -> dict[str, Any]:
    """Return a reproducible synthetic cluster of a supported size."""

    if node_count not in SUPPORTED_NODE_COUNTS:
        raise ValueError(
            f"unsupported node count {node_count}; "
            f"expected one of {SUPPORTED_NODE_COUNTS}"
        )

    return {
        "node_count": node_count,
        "nodes": [
            _build_node(index)
            for index in range(1, node_count + 1)
        ],
        "deployments": [
            {
                "namespace": "edgepilot-token-eval",
                "name": "edgepilot-token-eval-nginx",
                "replicas": 1,
                "ready_replicas": 1,
            }
        ],
    }
