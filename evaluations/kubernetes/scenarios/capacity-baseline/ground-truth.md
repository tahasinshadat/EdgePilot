# Capacity Baseline Ground Truth

## Snapshot

The cluster state was captured at the time recorded in
`captured-at-utc.txt`.

The results below were derived independently from `kubectl describe
nodes`. They were calculated before evaluating EdgePilot responses.

## Included Nodes

- `edgepilot-control-plane`

## CPU

Node allocatable CPU:

    8 CPU = 8000m

Scheduled workload CPU requests:

    1200m

Available CPU:

    8000m - 1200m = 6800m

Therefore, the cluster has:

    6800m = 6.8 CPU

available for additional requested workloads.

## Memory

Node allocatable memory:

    8,025,700 Ki

Scheduled workload memory requests:

    418 Mi

Normalize the requested memory to Ki:

    418 Mi × 1024 = 428,032 Ki

Available memory:

    8,025,700 Ki - 428,032 Ki = 7,597,668 Ki

Equivalent values:

    7,597,668 Ki
    7,419.59765625 Mi
    7.24570084 Gi

Therefore, the cluster has approximately:

    7.2457 Gi

of memory available for additional requested workloads.

## Expected Answer

A numerically correct EdgePilot response must report:

- Available CPU: `6800m` or `6.8 CPU`
- Available memory: `7,597,668 Ki`, approximately `7,419.60 Mi`,
  or approximately `7.2457 Gi`

Equivalent values are accepted only when they use the correct binary
unit conversions.

## Important Distinction

This result measures Kubernetes scheduling capacity based on resource
requests. It does not represent current CPU or memory utilization.