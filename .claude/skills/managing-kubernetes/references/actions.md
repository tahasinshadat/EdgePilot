# Kubernetes Action Reference

## Read-only capacity evaluation

Tool: `evaluate_kubernetes_workload`

Purpose:

- Inspect whether a workload can fit on available nodes.
- Check CPU, memory, pod slots, readiness, schedulability, and taints.
- Evaluate a particular node when one is provided.

Inputs:

- `cpu_cores`
- `memory_bytes`
- `pods`
- Optional `node`
- Optional `tolerations`

Approval:

- Not required because this operation does not change cluster state.

## Scale a deployment

Tool: `scale_workload`

Inputs:

- `namespace`
- `deployment_name`
- `replicas`

Preconditions:

1. Confirm that the namespace exists.
2. Confirm that the deployment exists.
3. Inspect the current replica count.
4. Ensure replicas is a nonnegative integer.
5. Explain possible availability and capacity effects.
6. Obtain explicit approval.

Verification:

- Read the deployment after scaling.
- Compare desired, current, available, and ready replicas.
- Report success only when the observed state matches the request.

Rollback:

- Scale the deployment back to its previous replica count.

## Restart a deployment

Tool: `restart_workload`

Inputs:

- `namespace`
- `deployment_name`

Preconditions:

1. Confirm that the namespace exists.
2. Confirm that the deployment exists.
3. Inspect deployment and pod health.
4. Explain that pods will be replaced through a rolling restart.
5. Obtain explicit approval.

Verification:

- Confirm that the restart annotation changed.
- Inspect rollout status and replacement pods.
- Check for unavailable or crash-looping pods.

Rollback:

- A restart cannot be undone directly.
- If the replacement pods fail because of a deployment change, roll back
  the deployment revision.

## Cordon a node

Tool: `cordon_node`

Inputs:

- `node_name`

Preconditions:

1. Confirm the node exists.
2. Inspect node readiness and current schedulability.
3. Explain that new pods will not schedule on the node.
4. Explain that existing pods normally remain running.
5. Obtain explicit approval.

Verification:

- Read the node and confirm `unschedulable` is true.

Rollback:

- Uncordon the node using an approved Kubernetes operation.

## Unsupported operations

If an operation is not exposed through an EdgePilot tool:

1. Do not substitute an unrelated tool.
2. Explain that the requested action is unsupported.
3. Offer a read-only diagnostic alternative when possible.
4. Do not construct or execute arbitrary shell commands without explicit
   approval and the applicable EdgePilot safety controls.
