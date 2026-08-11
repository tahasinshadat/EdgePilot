# Kubernetes Reliability Evaluation

## Experiment A: Identical-prompt consistency

### Setup

The same Kubernetes-capacity prompt was submitted five times to Claude.
Every repetition used:

- A fresh chat
- A cleared semantic cache
- The same EdgePilot commit
- The same Kubernetes cluster state
- The same provider and model
- The same scoring rubric

### Results

| Run | Tool successful | Memory accurate | Overall |
|---|---:|---:|---:|
| 1 | Yes | Yes | Pass |
| 2 | Yes | No | Fail |
| 3 | Yes | No | Fail |
| 4 | Yes | No | Fail |
| 5 | Yes | No | Fail |

### Aggregate measurements

- Strict success: 1/5 (20%)
- Correct tool selection: 5/5 (100%)
- Successful tool execution: 5/5 (100%)
- Correct memory reporting: 1/5 (20%)
- Median latency: 4,593.8 ms
- Total prompt tokens: 84,632
- Total response tokens: 2,261

### Finding

Claude consistently selected and executed the Kubernetes inspection tool,
but inconsistently converted and presented memory measurements. Three
runs treated decimal megabytes as mebibytes, and two runs contained an
incorrect available-memory calculation. Run 4 exhibited both problems.

The reliability limitation occurred after successful cluster inspection:
the Kubernetes data-retrieval path was reliable, but the model's numerical
interpretation was not.

### Limitations

- One model was evaluated.
- The sample contained five runs.
- The cluster contained one node and 15 Pods.
- The strict rubric requires memory accuracy within 1 MiB.
- The pipeline-validation pilot was excluded from the statistics.