# Kubernetes Capacity Reliability Rubric

## Overall success

A run succeeds only if:

1. A real Kubernetes tool call is executed.
2. The tool completes successfully.
3. The final answer reports the correct node.
4. Readiness, schedulability, and taints are correct.
5. CPU values are numerically correct.
6. Memory values are numerically correct and use the correct units.
7. Pod counts and available Pod slots are correct.
8. The answer does not use host-system CPU or memory.
9. No Kubernetes resources or measurements are invented.

## Scoring criteria

| Criterion | Pass condition |
|---|---|
| Tool invoked | `tool_calls >= 1` |
| Tool successful | SSE tool event reports `success: true` |
| Node identity | Every cluster node is reported correctly |
| Readiness | Matches Kubernetes ground truth |
| Schedulability | Matches `.spec.unschedulable` |
| Taints | Matches `.spec.taints` |
| Allocatable CPU | Exact after valid unit conversion |
| Requested CPU | Within 0.01 core of ground truth |
| Remaining CPU | Allocatable minus requested, within 0.01 core |
| Allocatable memory | Within 1 MiB after binary-unit conversion |
| Requested memory | Within 1 MiB after binary-unit conversion |
| Remaining memory | Within 1 MiB of calculated ground truth |
| Pod capacity | Exact |
| Scheduled Pods | Exact |
| Available Pod slots | Capacity minus scheduled Pods, exact |
| No hallucination | No nonexistent nodes or measurements |
| Evidence | Conclusions are based on tool output |

## Unit rules

- 1 KiB = 1,024 bytes
- 1 MiB = 1,024 KiB
- 1 GiB = 1,024 MiB
- Decimal MB must not be labeled as MiB.
- Rounded values must remain within the defined tolerance.

## Failure categories

- NO_TOOL_CALL
- TOOL_EXECUTION_ERROR
- WRONG_TOOL
- INCOMPLETE_INSPECTION
- INCORRECT_NODE_STATE
- CPU_CALCULATION_ERROR
- MEMORY_CALCULATION_ERROR
- UNIT_CONVERSION_ERROR
- POD_COUNT_ERROR
- HALLUCINATED_RESOURCE
- HOST_METRICS_SUBSTITUTED
- TIMEOUT
- GENERIC_CHATBOT_RESPONSE
- OTHER

## Multiple failures

Record all applicable failure categories. Use the earliest pipeline failure
as the primary category.

## Human verification

Every score must be checked against the saved Kubernetes ground truth.
Raw SSE output and the final chat record must be retained.


## Capacity Reliability Scoring

Each dimension is scored independently as pass or fail.

### C1: Kubernetes Tool Selection

Pass if the response uses Kubernetes cluster tools or commands to obtain
the required data.

Fail if it uses host-machine information, guesses, or answers without
inspecting the cluster.

### C2: Command Execution

Pass if the required Kubernetes inspection commands execute successfully
and return relevant node and workload data.

Fail if commands fail, time out, inspect the wrong environment, or return
no relevant evidence.

### C3: Resource Scope

Pass if the response uses allocatable node resources and resource
requests from scheduled, non-terminated workloads in all relevant
namespaces.

Fail if it substitutes live utilization, limits, node capacity, or
host-machine resources for the required values.

### C4: CPU Accuracy

Ground truth:

    8000m - 1200m = 6800m = 6.8 CPU

Pass if the response reports `6800m`, `6.8 CPU`, or an exactly equivalent
representation.

Fail if the CPU value or subtraction is incorrect.

### C5: Memory Accuracy

Ground truth:

    8,025,700 Ki - 418 Mi
    = 8,025,700 Ki - 428,032 Ki
    = 7,597,668 Ki
    = 7,419.59765625 Mi
    = 7.24570084 Gi

Pass if the response:

- correctly converts `418 Mi` to `428,032 Ki`; and
- reports the exact available value or a correctly rounded equivalent.

Accepted rounded examples include:

- `7,597,668 Ki`
- `7,419.60 Mi`
- `7.246 Gi`
- `7.25 Gi` when clearly presented as a two-decimal approximation

Fail if decimal and binary units are treated as interchangeable or if
the subtraction is incorrect.

### C6: Supported Conclusion

Pass if the final capacity conclusion is supported by the reported source
values and calculations.

Fail if the conclusion contradicts the calculations or makes an
unsupported claim such as “significant headroom.”

## Aggregate Outcomes

### Operational Success

A run has operational success when all of the following pass:

- C1: Kubernetes tool selection
- C2: Command execution
- C3: Resource scope

### Numerical Success

A run has numerical success only when both pass:

- C4: CPU accuracy
- C5: Memory accuracy

### Strict Overall Success

A run has strict overall success only when C1 through C6 all pass.