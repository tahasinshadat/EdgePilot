"""Production-shaped synthetic Kubernetes tools for controlled experiments."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .cluster_fixtures import build_cluster_fixture


class SyntheticKubernetesTools:
    """Execute the experiment's Kubernetes tools against deterministic state."""

    def __init__(self, *, node_count: int) -> None:
        fixture = build_cluster_fixture(node_count)
        self._nodes = fixture["nodes"]
        self._deployment = deepcopy(fixture["deployments"][0])
        self._generation = 1

    def execute(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        handlers = {
            "inspect_kubernetes_cluster": self._inspect_cluster,
            "inspect_kubernetes_deployment": self._inspect_deployment,
            "scale_workload": self._scale_workload,
        }

        handler = handlers.get(tool_name)
        if handler is None:
            return {
                "success": False,
                "error": f"Unknown tool: {tool_name}",
                "available_tools": sorted(handlers),
            }

        try:
            result = handler(arguments)
            return {
                "success": True,
                "tool": tool_name,
                "arguments": arguments,
                "result": result,
            }
        except Exception as error:
            return {
                "success": False,
                "tool": tool_name,
                "arguments": arguments,
                "error": str(error),
                "error_type": type(error).__name__,
            }

    def _inspect_cluster(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        del arguments

        nodes = []
        total_allocatable_cpu = 0.0
        total_requested_cpu = 0.0
        total_allocatable_memory = 0
        total_requested_memory = 0
        total_scheduled_pods = 0

        for fixture_node in self._nodes:
            allocatable = fixture_node["allocatable"]
            requested = fixture_node["requested"]

            allocatable_cpu = float(allocatable["cpu_cores"])
            requested_cpu = float(requested["cpu_cores"])
            allocatable_memory = int(allocatable["memory_bytes"])
            requested_memory = int(requested["memory_bytes"])
            scheduled_pods = int(requested["pods"])

            node = {
                "name": fixture_node["name"],
                "status": {
                    "ready": fixture_node["ready"],
                    "schedulable": fixture_node["schedulable"],
                },
                "taints": [],
                "cpu": {
                    "capacity_cores": allocatable_cpu,
                    "allocatable_cores": allocatable_cpu,
                    "requested_cores": requested_cpu,
                    "available_cores": (
                        allocatable_cpu - requested_cpu
                    ),
                    "limit_cores": requested_cpu,
                    "requested_percent": (
                        requested_cpu / allocatable_cpu * 100
                    ),
                },
                "memory": {
                    "capacity_bytes": allocatable_memory,
                    "allocatable_bytes": allocatable_memory,
                    "requested_bytes": requested_memory,
                    "available_bytes": (
                        allocatable_memory - requested_memory
                    ),
                    "limit_bytes": requested_memory,
                    "requested_percent": (
                        requested_memory
                        / allocatable_memory
                        * 100
                    ),
                },
                "pods": {
                    "capacity": int(allocatable["pods"]),
                    "allocatable": int(allocatable["pods"]),
                    "scheduled": scheduled_pods,
                },
            }
            nodes.append(node)

            total_allocatable_cpu += allocatable_cpu
            total_requested_cpu += requested_cpu
            total_allocatable_memory += allocatable_memory
            total_requested_memory += requested_memory
            total_scheduled_pods += scheduled_pods

        return {
            "source": "kubernetes",
            "node_count": len(nodes),
            "nodes": nodes,
            "cluster": {
                "cpu": {
                    "allocatable_cores": total_allocatable_cpu,
                    "requested_cores": total_requested_cpu,
                    "available_cores": (
                        total_allocatable_cpu - total_requested_cpu
                    ),
                    "limit_cores": total_requested_cpu,
                    "requested_percent": (
                        total_requested_cpu
                        / total_allocatable_cpu
                        * 100
                    ),
                },
                "memory": {
                    "allocatable_bytes": total_allocatable_memory,
                    "requested_bytes": total_requested_memory,
                    "available_bytes": (
                        total_allocatable_memory
                        - total_requested_memory
                    ),
                    "limit_bytes": total_requested_memory,
                    "requested_percent": (
                        total_requested_memory
                        / total_allocatable_memory
                        * 100
                    ),
                },
                "scheduled_pods": total_scheduled_pods,
            },
        }

    def _inspect_deployment(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        namespace = arguments.get("namespace")
        deployment_name = arguments.get("deployment_name")

        if not namespace:
            raise ValueError("namespace is required")
        if not deployment_name:
            raise ValueError("deployment_name is required")
        if not self._is_test_target(namespace, deployment_name):
            raise RuntimeError(
                f"Unable to inspect {namespace}/{deployment_name}: "
                "status=404, reason=Not Found"
            )

        replicas = int(self._deployment["replicas"])
        ready_replicas = int(self._deployment["ready_replicas"])

        return {
            "namespace": namespace,
            "deployment_name": deployment_name,
            "desired_replicas": replicas,
            "ready_replicas": ready_replicas,
            "available_replicas": ready_replicas,
            "updated_replicas": ready_replicas,
            "unavailable_replicas": max(
                replicas - ready_replicas,
                0,
            ),
            "observed_generation": self._generation,
        }

    def _scale_workload(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        namespace = arguments.get("namespace", "default")
        deployment_name = arguments.get("deployment_name")
        replicas = arguments.get("replicas")

        if deployment_name is None or replicas is None:
            raise ValueError(
                "deployment_name and replicas are required"
            )

        replicas = int(replicas)
        if replicas < 0:
            return {
                "success": False,
                "error": "Replicas must be >= 0",
            }

        if not self._is_test_target(namespace, deployment_name):
            return {
                "success": False,
                "error": (
                    "Kubernetes API error scaling deployment: "
                    "Not Found (404)"
                ),
            }

        self._deployment["replicas"] = replicas
        self._deployment["ready_replicas"] = replicas
        self._generation += 1

        return {
            "success": True,
            "message": (
                f"Successfully scaled deployment "
                f"'{deployment_name}' in namespace "
                f"'{namespace}' to {replicas} replicas."
            ),
        }

    @staticmethod
    def _is_test_target(
        namespace: str,
        deployment_name: str,
    ) -> bool:
        return (
            namespace == "edgepilot-token-eval"
            and deployment_name
            == "edgepilot-token-eval-nginx"
        )
