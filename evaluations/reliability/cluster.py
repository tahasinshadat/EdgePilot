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
from typing import Any, Dict, List, Tuple

DeploymentKey = Tuple[str, str]  # (namespace, name)


class UnknownResource(LookupError):
    """Raised when an action names a deployment or node that does not exist.

    Raising rather than silently succeeding matters: a model inventing a
    resource name is exactly the failure mode being measured.
    """


class FakeCluster:
    """Cluster state, the actions applied to it, and a comparable snapshot."""

    def __init__(
        self,
        nodes: List[str],
        deployments: Dict[DeploymentKey, int],
    ) -> None:
        self._initial_nodes = list(nodes)
        self._initial_deployments = dict(deployments)
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
            lines.append(f"  - {namespace}/{name}: {values['replicas']} replicas")

        return "\n".join(lines)

    # ── Internal ────────────────────────────────────────────────────────

    def _require_deployment(self, namespace: str, deployment_name: str) -> None:
        if (namespace, deployment_name) not in self._deployments:
            raise UnknownResource(
                f"deployment {deployment_name!r} not found in namespace {namespace!r}"
            )
