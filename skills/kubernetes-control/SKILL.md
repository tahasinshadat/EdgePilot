---
name: kubernetes-control
description: Safely inspect and control Kubernetes clusters through EdgePilot. Load this skill for Kubernetes, K8s, cluster capacity, Pod placement, Deployment scaling, rolling restarts, node cordoning, rightsizing, or troubleshooting requests.
---

# Kubernetes Control

Treat Kubernetes control as a staged workflow. Keep observation separate from
mutation and use only EdgePilot's typed Kubernetes tools. Never construct or run
arbitrary kubectl or shell commands.

## Workflow

1. Identify the user's goal and exact Kubernetes target.
2. Observe the relevant live state using read-only tools.
3. Assess whether the evidence supports an action.
4. Explain the proposed mutation, reason, expected effect, and risk.
5. Request human approval.
6. Execute no more than one mutation.
7. Re-observe the target and report the verified result.

Do not claim success from the mutation request alone. A successful API response
only means Kubernetes accepted the request.

## Read-only tools

- Use `inspect_kubernetes_cluster` for node health, capacity, taints, requests,
  limits, and Pod slots.
- Use `evaluate_kubernetes_workload` for workload-placement questions.
- Use `inspect_kubernetes_deployment` before and after scaling or restarting.

Read-only inspection does not require approval.

## Control tools

- Use `scale_workload` only with an exact namespace, Deployment, and replica count.
- Use `restart_workload` only with an exact namespace and Deployment.
- Use `cordon_node` only with an exact node observed in the current cluster.

Every control tool requires human approval. Never replace these tools with
`run_shell_commands` or `run_python_script`.

## Safety rules

- Never guess names, namespaces, nodes, replica counts, or resource requests.
- Do not assume the `default` namespace unless the user confirms it.
- Do not scale from CPU percentage alone.
- Do not restart a busy workload unless it is unhealthy or the user explicitly
  requests the restart.
- Explain that cordoning stops new scheduling but does not evict existing Pods.
- Stop if cluster inspection fails.
- Ask for clarification when a target is ambiguous.
- Describe capacity from `inspect_kubernetes_cluster` as schedulable headroom
  based on Pod resource requests. Do not describe it as real-time CPU or memory
  availability unless live utilization metrics are provided by Prometheus.
