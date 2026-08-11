# Kubernetes Reliability Evaluation Methodology

## Research question

How reliably does EdgePilot inspect Kubernetes workloads and report
application network ports?

## Hypothesis

For a fixed Kubernetes cluster state, a model will achieve the same
success rate across five identical prompts and five semantically
equivalent prompt variations.

## Independent variables

- Model
- Prompt phrasing

## Controlled variables

- Cluster state
- Kubernetes Skill version
- EdgePilot commit
- Model configuration
- Enabled tools
- Timeout and retry policy
- Semantic cache disabled
- Scoring rubric

## Pilot experiment

1. Deploy a known Kubernetes scenario.
2. Record ground truth using `kubectl`.
3. Clear EdgePilot's semantic cache.
4. Submit the same prompt five times independently.
5. Save each response and tool trace.
6. Reset or verify cluster state between runs.
7. Score every run using the predefined rubric.

The scoring rubric and numerical tolerances were frozen after the pipeline
validation pilot and before Experiment A. The pilot was excluded from the
experiment statistics.


## Capacity Reliability Evaluation

### Research Question

Can EdgePilot consistently inspect a Kubernetes cluster and accurately
calculate its remaining CPU and memory capacity?

### Hypothesis

Given the same cluster state and exact same prompt, EdgePilot will select
the correct Kubernetes tools and return a numerically accurate capacity
calculation in all five runs.

### Capacity Definition

Available CPU is:

    total allocatable CPU - total requested CPU

Available memory is:

    total allocatable memory - total requested memory
    
### Resource Scope

The capacity calculation includes:

- Allocatable resources from all schedulable nodes
- Resource requests from scheduled, non-terminated pods
- Workloads from all namespaces

The calculation excludes:

- Completed and failed pods
- Resource limits
- Live resource utilization
- Resources from the machine hosting EdgePilot

### Unit Normalization

CPU values are converted to millicores before calculation:

- `1 CPU` = `1000m`
- `0.5 CPU` = `500m`

Memory values are converted to bytes before calculation:

- `1 Ki` = `1024 bytes`
- `1 Mi` = `1024² bytes`
- `1 Gi` = `1024³ bytes`
- `1 K` = `1000 bytes`
- `1 M` = `1000² bytes`
- `1 G` = `1000³ bytes`

Binary and decimal memory units must not be treated as interchangeable.

### Success Criteria

A run is evaluated separately for:

1. Correct Kubernetes tool selection
2. Successful command execution
3. Correct resource scope
4. Correct CPU calculation
5. Correct memory calculation
6. A final conclusion supported by the calculated values

Operational success does not imply numerical success.

### Controlled Variables

The following remain unchanged across the five identical-prompt runs:

- Kubernetes cluster state
- Exact prompt
- Model and model version
- Model configuration
- Kubernetes Skill version
- EdgePilot commit
- Enabled tools
- Timeout and retry policy
- Semantic cache state
- Scoring rubric
- Ground-truth calculation method