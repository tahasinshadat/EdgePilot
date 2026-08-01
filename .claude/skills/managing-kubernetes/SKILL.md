---
name: managing-kubernetes
description: Inspects Kubernetes capacity and safely performs approved deployment scaling, rolling restarts, and node cordoning for EdgePilot. Use when diagnosing Kubernetes resource problems, investigating workload health, or proposing cluster remediation.
---

# Managing Kubernetes

Use EdgePilot's Kubernetes tools to inspect cluster capacity, diagnose
workload problems, propose remediation, obtain approval, execute the
approved action, and verify the result.

## Required workflow

1. Identify the current Kubernetes context.
2. Identify the namespace, resource type, and resource name.
3. Inspect current state before recommending a change.
4. Explain the proposed action and its expected impact.
5. Request explicit approval for every mutating action.
6. Execute only the action and arguments the user approved.
7. Inspect the resource again to verify the outcome.
8. Report the result, remaining risks, and rollback procedure.

## Available operations

Read [references/actions.md](references/actions.md) for supported
EdgePilot tools and their required arguments.

Read [references/safety.md](references/safety.md) before performing any
operation that changes Kubernetes state.

For representative workflows, read
[examples/scenarios.md](examples/scenarios.md).

## Rules

- Prefer read-only inspection before mutation.
- Never invent a namespace, workload name, node name, or replica count.
- Never silently use the `default` namespace when the target is ambiguous.
- Treat scale, restart, cordon, drain, delete, and configuration updates
  as mutating operations.
- Every mutating operation requires explicit human approval.
- Approval for one action does not authorize another action.
- Verify every mutation by reading the resulting cluster state.
- Do not claim success based only on a successful API response.
- If verification fails, report the result as unverified.
- Never expose kubeconfig contents, credentials, tokens, or certificates.
