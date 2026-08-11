# Kubernetes Reliability Evaluation

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