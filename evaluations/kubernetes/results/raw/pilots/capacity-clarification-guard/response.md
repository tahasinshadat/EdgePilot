1. How much additional CPU and memory capacity is available in this Kubernetes cluster for scheduling new workloads? Inspect the cluster, show the source values and calculations, and state all units and assumptions. Do not use information from the host machine.

Please provide the workload's CPU request, memory request, and pod or replica count. Also specify any node selectors, affinity rules, or tolerations—or say that there are no placement constraints.


2. Inspect this Kubernetes cluster and calculate its current CPU and memory scheduling headroom. Report total allocatable CPU minus total requested CPU, and total allocatable memory minus total requested memory, across all schedulable nodes and relevant namespaces. This is not a request to determine whether a particular pod or replica will fit, and there are no placement constraints. Show the source values, calculations, units, and assumptions. Do not use information from the host machine.

Kubernetes Cluster Scheduling Headroom Report


Cluster Summary

Nodes: 1 (all schedulable and ready)
Scheduled Pods: 15 / 110 capacity
Node Status: edgepilot-control-plane (Ready, Schedulable, no taints)


---

CPU Scheduling Headroom


| Metric | Value | Unit |
|--------|-------|------|
| Allocatable CPU | 8.0 | cores |
| Requested CPU | 1.2 | cores |
| Available CPU (headroom) | 6.8 | cores |
| Requested as % of allocatable | 15.0% | — |

Calculation:

Available = Allocatable − Requested
Available = 8.0 − 1.2 = 6.8 cores


---

Memory Scheduling Headroom


| Metric | Value | Unit |
|--------|-------|------|
| Allocatable Memory | 7,637 | MiB |
| Requested Memory | 418 | MiB |
| Available Memory (headroom) | 7,219 | MiB |
| Requested as % of allocatable | 5.33% | — |

Calculation:

Allocatable = 8,218,316,800 bytes ÷ 1,048,576 = 7,837 MiB
Requested   = 438,304,768 bytes ÷ 1,048,576 = 418 MiB
Available   = 7,837 − 418 = 7,419 MiB

(Note: Tool reports available_bytes = 7,780,012,032 bytes = 7,419 MiB)


---

Pod Slot Headroom


| Metric | Value |
|--------|-------|
| Pod Capacity | 110 |
| Scheduled Pods | 15 |
| Available Pod Slots | 95 |

---

Source & Assumptions

Data Source: Kubernetes API (read-only inspection)
Scope: All schedulable nodes (1 node, fully allocatable)
Requests: Sum of CPU and memory requests across all 15 scheduled pods
Limits: Captured but not factored into headroom (limits do not block scheduling)
Memory Units: Binary conversion (1 GiB = 1,024 MiB)
Headroom Definition: Allocatable resources minus current requests—represents request-based scheduling capacity, not real-time utilization

