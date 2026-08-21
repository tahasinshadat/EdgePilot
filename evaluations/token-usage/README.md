# Token-Usage Evaluation

## Research question

How do token usage, latency, cost, and task success differ among:

1. AI without a Kubernetes Skill
2. AI with a Skill and human approval
3. AI with a Skill operating autonomously in an isolated test environment

## Conditions

| Condition | Skill | Human approval |
|---|---|---|
| `no_skill` | Disabled | Not applicable |
| `skill_with_approval` | Enabled | Required |
| `fully_agentic` | Enabled | Automatically approved in an isolated environment |

## Controlled variables

Each comparison must use the same:

- EdgePilot commit
- model and model configuration
- task prompt
- initial cluster state
- enabled tools
- timeout and retry settings
- semantic-cache setting
- scoring rubric

## Measurements

Each run records:

- input, cached-input, and output tokens
- number of model requests and tool calls
- wall-clock latency
- estimated API cost
- task success
- safety success
- cluster size

## Procedure

1. Record the current commit SHA.
2. Reset the test cluster to its documented initial state.
3. Disable the semantic cache unless caching is the variable under study.
4. Run each task once under each of the three conditions.
5. Repeat each condition at least 10 times using fresh conversations.
6. Record every run, including failures, in a copy of `results-template.csv`.
7. Do not modify the rubric after examining the results.
8. Run autonomous mutations only in a disposable or simulated cluster.

## Status

The evaluation format is defined, but the controlled three-condition experiment
has not yet been completed.