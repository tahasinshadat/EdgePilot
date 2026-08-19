"""An in-memory Kubernetes cluster that mutating tools actually change.

Deliberately fake. The Aug-3 research question is how much the *model* varies
between runs, so every other source of variance — scheduling delays, API
latency, cluster flakiness — is removed. Any difference between two runs here
is attributable to the AI, which is the measurement being taken.

Fidelity is the tradeoff and is stated in the write-up, not hidden.

Method names deliberately match the registered tool names, so the runner can
apply a tool call with ``getattr(cluster, tool_name)(**arguments)``.
"""

from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional, Tuple

DeploymentKey = Tuple[str, str]  # (namespace, name)


class UnknownResource(LookupError):
    """Raised when an action names a deployment or node that does not exist.

    Raising rather than silently succeeding matters: a model inventing a
    resource name is exactly the failure mode being measured.
    """


class FakeCluster:
    """Cluster state, the actions applied to it, and a comparable snapshot."""

    # Per-node allocatable capacity, and per-replica requests for a
    # deployment. The Skill requires capacity to be verified before a scale-up,
    # and a fixture with no resource data made that impossible: models
    # correctly asked for "CPU and memory requests/limits" and "request
    # headroom", the fixture had none, and the run stalled at `no_action`. A
    # measurement fixture has to be able to satisfy the preconditions the
    # thing being measured insists on.
    DEFAULT_NODE_CAPACITY = {"cpu_cores": 8, "memory_gb": 32}
    DEFAULT_REQUESTS = {"cpu_cores": 0.5, "memory_gb": 2}

    def __init__(
        self,
        nodes: List[str],
        deployments: Dict[DeploymentKey, int],
        node_capacity: Optional[Dict[str, Any]] = None,
        requests: Optional[Dict[DeploymentKey, Dict[str, Any]]] = None,
    ) -> None:
        self._initial_nodes = list(nodes)
        self._initial_deployments = dict(deployments)
        self._node_capacity = dict(node_capacity or self.DEFAULT_NODE_CAPACITY)
        self._requests = {
            key: dict(requests.get(key, self.DEFAULT_REQUESTS))
            if requests else dict(self.DEFAULT_REQUESTS)
            for key in self._initial_deployments
        }
        self.reset()

    def reset(self) -> None:
        """Restore the starting state, so each repetition begins identically."""

        self._nodes: Dict[str, Dict[str, Any]] = {
            name: {"cordoned": False} for name in self._initial_nodes
        }
        self._deployments: Dict[DeploymentKey, Dict[str, int]] = {
            key: {"replicas": count, "restarts": 0}
            for key, count in self._initial_deployments.items()
        }
        self.actions: List[Tuple[str, Dict[str, Any]]] = []

    # ── Capacity, so a scale-up can be justified ────────────────────────

    def requests(self, namespace: str, deployment_name: str) -> Dict[str, Any]:
        """Per-replica CPU and memory requests for one deployment."""
        self._require_deployment(namespace, deployment_name)
        return dict(self._requests[(namespace, deployment_name)])

    def capacity(self) -> Dict[str, Any]:
        """Total, requested and free capacity across schedulable nodes.

        Cordoned nodes are excluded from the total: that is what cordoning
        means, and it lets a model reason about a scale-up after a cordon.
        """
        schedulable = [n for n, v in self._nodes.items() if not v["cordoned"]]
        total_cpu = len(schedulable) * self._node_capacity["cpu_cores"]
        total_mem = len(schedulable) * self._node_capacity["memory_gb"]

        used_cpu = sum(
            self._requests[key]["cpu_cores"] * values["replicas"]
            for key, values in self._deployments.items()
        )
        used_mem = sum(
            self._requests[key]["memory_gb"] * values["replicas"]
            for key, values in self._deployments.items()
        )

        return {
            "schedulable_nodes": len(schedulable),
            "per_node": dict(self._node_capacity),
            "total_cpu_cores": total_cpu,
            "total_memory_gb": total_mem,
            "requested_cpu_cores": round(used_cpu, 2),
            "requested_memory_gb": round(used_mem, 2),
            "free_cpu_cores": round(total_cpu - used_cpu, 2),
            "free_memory_gb": round(total_mem - used_mem, 2),
        }

    # ── Mutations, named to match the registered tools ──────────────────

    def scale_workload(
        self, namespace: str, deployment_name: str, replicas: int
    ) -> None:
        if replicas < 0:
            raise ValueError("replicas must be >= 0")

        self._require_deployment(namespace, deployment_name)
        self._deployments[(namespace, deployment_name)]["replicas"] = replicas
        self.actions.append(("scale_workload", {
            "namespace": namespace,
            "deployment_name": deployment_name,
            "replicas": replicas,
        }))

    def restart_workload(self, namespace: str, deployment_name: str) -> None:
        self._require_deployment(namespace, deployment_name)
        self._deployments[(namespace, deployment_name)]["restarts"] += 1
        self.actions.append(("restart_workload", {
            "namespace": namespace,
            "deployment_name": deployment_name,
        }))

    def cordon_node(self, node_name: str) -> None:
        if node_name not in self._nodes:
            raise UnknownResource(f"node {node_name!r} does not exist")

        self._nodes[node_name]["cordoned"] = True
        self.actions.append(("cordon_node", {"node_name": node_name}))

    # ── Reads ───────────────────────────────────────────────────────────

    def replicas(self, namespace: str, deployment_name: str) -> int:
        self._require_deployment(namespace, deployment_name)
        return self._deployments[(namespace, deployment_name)]["replicas"]

    def restarts(self, namespace: str, deployment_name: str) -> int:
        self._require_deployment(namespace, deployment_name)
        return self._deployments[(namespace, deployment_name)]["restarts"]

    def is_cordoned(self, node_name: str) -> bool:
        if node_name not in self._nodes:
            raise UnknownResource(f"node {node_name!r} does not exist")

        return self._nodes[node_name]["cordoned"]

    def snapshot(self) -> Dict[str, Any]:
        """A comparable view of state.

        Two clusters that reached the same state compare equal regardless of
        the order of the actions that got them there.
        """

        return {
            "nodes": copy.deepcopy(self._nodes),
            "deployments": {
                f"{namespace}/{name}": copy.deepcopy(values)
                for (namespace, name), values in sorted(self._deployments.items())
            },
        }

    def describe(self) -> str:
        """Plain-text cluster state for the model's context."""

        lines = ["Nodes:"]

        for name, values in self._nodes.items():
            state = "cordoned" if values["cordoned"] else "schedulable"
            lines.append(f"  - {name} ({state})")

        lines.append("Deployments:")

        for (namespace, name), values in sorted(self._deployments.items()):
            requests = self._requests[(namespace, name)]
            lines.append(
                f"  - {namespace}/{name}: {values['replicas']} replicas, "
                f"requests {requests['cpu_cores']} CPU / "
                f"{requests['memory_gb']}Gi per replica"
            )

        capacity = self.capacity()
        lines += [
            "Capacity (schedulable nodes only):",
            f"  - per node: {capacity['per_node']['cpu_cores']} CPU / "
            f"{capacity['per_node']['memory_gb']}Gi",
            f"  - total: {capacity['total_cpu_cores']} CPU / "
            f"{capacity['total_memory_gb']}Gi",
            f"  - requested: {capacity['requested_cpu_cores']} CPU / "
            f"{capacity['requested_memory_gb']}Gi",
            f"  - free: {capacity['free_cpu_cores']} CPU / "
            f"{capacity['free_memory_gb']}Gi",
        ]

        return "\n".join(lines)

    # ── Internal ────────────────────────────────────────────────────────

    def _require_deployment(self, namespace: str, deployment_name: str) -> None:
        if (namespace, deployment_name) not in self._deployments:
            raise UnknownResource(
                f"deployment {deployment_name!r} not found in namespace {namespace!r}"
            )
