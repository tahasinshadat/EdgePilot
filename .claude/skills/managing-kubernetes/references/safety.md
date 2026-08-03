# Kubernetes Safety Rules

## Read-only actions

Read-only inspection may proceed without mutation approval.

Examples:

- Listing nodes
- Inspecting deployment state
- Reading pod status
- Evaluating capacity
- Reading historical metrics
- Examining events and logs

## Mutating actions

The following require explicit approval:

- Scaling workloads
- Restarting workloads
- Cordoning or draining nodes
- Deleting Kubernetes resources
- Applying or patching configurations
- Changing resource requests or limits
- Changing services, ports, or network policies
- Executing arbitrary shell commands

## Approval requirements

Before requesting approval, state:

- Kubernetes context
- Namespace
- Resource type
- Resource name
- Exact proposed operation
- Important arguments, such as replica count
- Expected impact
- Rollback or recovery procedure

A valid approval must refer to the proposed operation. A general response
such as "do whatever is needed" should not authorize multiple mutations.

If the proposed arguments change, request approval again.

## Production protection

If the current context appears to be production:

1. Clearly identify it as production.
2. Require explicit confirmation that the user intends to affect production.
3. Prefer the smallest reversible action.
4. Avoid simultaneous mutations.
5. Verify each action before proposing another.

## Failure handling

- Stop when authentication or authorization fails.
- Stop when the target is ambiguous.
- Stop when the resource changes between inspection and execution.
- Do not repeatedly retry a mutation without approval.
- Report partial success accurately.
- Preserve the Kubernetes error without exposing secrets.
