# Kubernetes Skill: Hello World Walkthrough

## Purpose

This walkthrough demonstrates how EdgePilot uses the Kubernetes Skill to inspect a cluster, obtain measured resource data, and produce an evidence-based answer.

## Test environment

The walkthrough was performed using the following environment:

| Component | Configuration |
|---|---|
| Host operating system | macOS 14.4.1 |
| Python | 3.12.4 |
| Kubernetes environment | Kind |
| Kubernetes context | `kind-edgepilot` |
| kubectl client | v1.34.1 |
| Cluster size | 1 control-plane node |
| Node | `edgepilot-control-plane` |
| Kubernetes node version | v1.36.1 |
| Node operating system | Debian GNU/Linux 13 (trixie) |
| EdgePilot commit | `dcc5e15` |

The cluster was confirmed reachable with `kubectl get nodes` before the walkthrough. No kubeconfig contents, credentials, tokens, certificates, or API keys were recorded.

## User prompt

> How much CPU and memory request headroom is available in the Kubernetes cluster?

## Expected behavior

EdgePilot should:

1. Recognize this as a cluster-wide Kubernetes capacity question.
2. Load the `kubernetes-control` Skill.
3. Call the read-only `inspect_kubernetes_cluster` tool.
4. Read allocatable CPU and memory and existing workload requests.
5. Calculate allocatable resources minus existing requests.
6. Label the result as **request headroom**, not real-time free resources.
7. Avoid claiming that additional workloads will definitely be scheduled.
8. Return the measured CPU and memory values with an appropriate limitation statement.

## Independent ground truth

The expected answer was calculated directly from Kubernetes before asking EdgePilot.

| Resource | Allocatable | Existing requests | Request headroom |
|---|---:|---:|---:|
| CPU | 8 cores (`8000m`) | `1200m` | `6800m` (6.8 cores) |
| Memory | `8025700 Ki` | `418 Mi` (`428032 Ki`) | `7597668 Ki` (approximately 7419.6 MiB or 7.25 GiB) |

Calculations:

```text
CPU request headroom = 8000m - 1200m = 6800m
Memory request headroom = 8025700 Ki - (418 × 1024 Ki)
                        = 7597668 Ki
                        ≈ 7419.6 MiB
                        ≈ 7.25 GiB
```

These values describe schedulable headroom based on Kubernetes resource requests. They do not represent real-time unused CPU or memory.

## Observed tool call and result

Two initial attempts were recorded.

### Attempt 1: Cluster-wide question with Claude

Claude was asked the original user prompt. It made zero tool calls and requested a namespace and resource information from the user instead of inspecting the cluster.

Key result:

```json
{
  "provider": "claude",
  "used_remote_provider": true,
   "tokens": {
    "prompt": 1145,
    "response": 126,
    "tool_calls": 0
  }
}
```

This attempt failed because a namespace is not required for a cluster-wide capacity question and the model did not call `inspect_kubernetes_cluster`.

### Attempt 2: Explicit tool instruction with Claude

Claude was explicitly instructed to inspect all namespaces using `inspect_kubernetes_cluster`. Its response contained an XML-like textual representation of a function call, but EdgePilot did not receive a structured tool call.

Key result:

```json
{
  "provider": "claude",
  "used_remote_provider": true,
  "tokens": {
    "prompt": 1167,
    "response": 161,
    "tool_calls": 0
  }
}
```

The response included:

```text
<invoke name="inspect_kubernetes_cluster">
<parameter name="namespace">all</parameter>
</invoke>
```

Because `tool_calls` remained zero, the cluster was not inspected and no CPU or memory request-headroom values were returned.

### Gemini availability check

A Gemini attempt fell back to the offline provider because a Gemini API key was not configured. The offline answer reported host utilization rather than Kubernetes request headroom, so it was excluded as an invalid model result.

## Verified answer

Neither model attempt produced a tool-backed Kubernetes answer, so no model-generated measurements could be verified against the ground truth.

| Check | Expected | Observed | Result |
|---|---|---|---|
| Load and follow the Kubernetes Skill | Yes | Not directly observable from the CLI result | Inconclusive |
| Call `inspect_kubernetes_cluster` | Yes | Zero structured tool calls | Fail |
| Report CPU request headroom | 6.8 cores | Not reported | Fail |
| Report memory request headroom | Approximately 7.25 GiB | Not reported | Fail |
| Distinguish requests from utilization | Yes | First Claude response did not provide either measurement | Fail |
| Avoid requiring a namespace for a cluster-wide question | Yes | Claude requested namespace information | Fail |

The Kubernetes ground truth was independently verified, but the EdgePilot response was not successful. This failed run should be retained as experimental evidence rather than presented as a successful demonstration. A successful Hello World run remains pending until a provider with working structured tool calling is configured.

## Sequence diagram

The solid workflow below represents the intended path. The observed Claude run stopped before structured tool execution.

```mermaid
sequenceDiagram
    participant U as User
    participant A as AI provider
    participant S as Kubernetes Skill
    participant T as EdgePilot tool executor
    participant K as Kubernetes cluster

    U->>A: Ask for CPU and memory request headroom
    A->>S: Load kubernetes-control instructions
    S-->>A: Require read-only cluster inspection
    alt Intended workflow
        A->>T: Structured inspect_kubernetes_cluster call
        T->>K: Read allocatable resources and Pod requests
        K-->>T: Return measured cluster state
        T-->>A: Return CPU and memory values
        A-->>U: Report verified request headroom
    else Observed Claude workflow
        A-->>U: Ask for unnecessary details or print textual tool markup
        Note over T,K: No structured tool call; cluster not inspected
    end
```

## Limitations

- The environment contains one Kind control-plane node and does not represent a production cluster.
- Kubernetes measurements are a point-in-time snapshot and may change as Pods start, stop, or change requests.
- Request headroom is allocatable capacity minus declared Pod requests; it is not real-time unused CPU or memory.
- Claude was the only configured remote provider during this walkthrough.
- Gemini could not be evaluated because its API key was not configured.
- Two Claude attempts are sufficient to identify failures but not to estimate a reliable failure rate.
- The CLI path was tested; behavior through the Electron UI may differ and should be measured separately.
- No conclusion about cross-model reliability can be made until multiple configured providers are tested under identical conditions.
