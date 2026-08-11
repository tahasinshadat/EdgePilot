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