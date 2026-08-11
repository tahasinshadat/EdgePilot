# Capacity Evaluation — Identical Prompt

## Prompt ID

`capacity-identical-v2`

## Prompt

> Inspect this Kubernetes cluster and calculate its current CPU and
> memory scheduling headroom. Report total allocatable CPU minus total
> requested CPU, and total allocatable memory minus total requested
> memory, across all schedulable nodes and relevant namespaces. This is
> not a request to determine whether a particular pod or replica will
> fit, and there are no placement constraints. Show the source values,
> calculations, units, and assumptions. Do not use information from the
> host machine.

## Experiment A

Submit the exact prompt above five times independently.

The wording, punctuation, and capitalization must not be changed between
runs.

## Run IDs

- `capacity-identical-claude-run-01`
- `capacity-identical-claude-run-02`
- `capacity-identical-claude-run-03`
- `capacity-identical-claude-run-04`
- `capacity-identical-claude-run-05`