# Kubernetes Cluster Scheduling Headroom

## CPU Headroom

**Calculation:**
- Allocatable CPU: **8.0 cores**
- Requested CPU: **1.2 cores**
- **Available headroom: 6.8 cores**

**Utilization:** 15.0% of allocatable capacity is requested.

## Memory Headroom

**Calculation:**
- Allocatable memory: **8,218,316,800 bytes** = **7.656 GiB** (binary conversion: 1 GiB = 1,024³ bytes)
- Requested memory: **438,304,768 bytes** = **418.25 MiB**
- **Available headroom: 7,780,012,032 bytes** = **7.238 GiB**

**Utilization:** 5.33% of allocatable capacity is requested.

## Cluster Summary

| Resource | Allocatable | Requested | Headroom | % Requested |
|----------|------------|-----------|----------|------------|
| CPU | 8.0 cores | 1.2 cores | 6.8 cores | 15.0% |
| Memory | 7.656 GiB | 418.25 MiB | 7.238 GiB | 5.33% |
| Pod slots | 110 | 15 | 95 | 13.6% |

## Source & Assumptions

- **Source:** Live Kubernetes cluster state (read-only inspection)
- **Scope:** Single node cluster (`edgepilot-control-plane`)
- **Status:** Node is Ready and schedulable with no taints
- **"Available"/"Headroom":** Allocatable minus requested (scheduling-time capacity, not real-time utilization)
- **Units:** CPU in cores, memory in binary GiB/MiB, pods as slot count
- **Pod limits:** The cluster can schedule up to 110 pods; 15 are currently scheduled

The cluster has substantial request-based headroom for both CPU and memory workloads.

This request-based assessment does not guarantee admission, successful scheduling, or live runtime performance.
