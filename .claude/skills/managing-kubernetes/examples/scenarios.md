# Kubernetes Scenarios

## Excessive pod memory

Problem:

A pod is using approximately 20 GB of memory when its expected usage is
approximately 1 GB.

Workflow:

1. Identify the pod, deployment, and namespace.
2. Inspect current and historical memory metrics.
3. Compare usage with resource requests and limits.
4. Check restarts, OOM events, logs, and sibling replicas.
5. Explain the likely cause and remediation options.
6. If a restart or scaling change is recommended, request approval.
7. Execute only the approved action.
8. Verify pod health and memory usage afterward.

## Unexpected exposed port

Problem:

A pod appears to expose a network port that is not part of its expected
configuration.

Workflow:

1. Inspect the pod, deployment, services, and declared container ports.
2. Compare observed ports with the expected specification.
3. Identify whether the port is reachable through a service or ingress.
4. Report the discrepancy and its possible risk.
5. Do not change networking configuration without explicit approval.
6. Verify configuration and reachability after an approved correction.

## Capacity remediation

Problem:

A workload cannot schedule because the cluster lacks capacity.

Workflow:

1. Evaluate CPU, memory, pod slots, node readiness, and taints.
2. Explain which constraint prevents scheduling.
3. Consider safe options, including another node or deployment scaling.
4. Present the smallest reasonable remediation.
5. Obtain approval for mutations.
6. Execute and verify the approved action.

## Daily maintenance review

Review these areas in sequence:

1. Node readiness and schedulability
2. Pending or failed pods
3. CPU and memory anomalies
4. Restart and OOM patterns
5. Unexpected network exposure
6. Performance differences across replicas or nodes
7. Capacity risks

Produce a prioritized report before proposing any mutation.
