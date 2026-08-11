# Experiment A Metadata

## Experiment

- Experiment ID: `capacity-identical-claude`
- Prompt ID: `capacity-identical-v1`
- Planned runs: 5
- Date:
- Researcher: Wenshu (Demi) Diao

## Model

- Provider: Anthropic
- Model name:
- Exact model identifier:
- Temperature:
- Maximum output tokens:
- Other model parameters:

Use `not configurable` or `unknown` rather than leaving a field blank.

## EdgePilot

- Git commit: See `edgepilot-commit.txt`
- Kubernetes Skill checksum: See `skill-checksum.txt`
- Semantic cache: Disabled
- Enabled tools:
- Timeout:
- Retry policy:

## Cluster

- Kubernetes context: See `capacity-baseline/context.txt`
- Ground truth: See `capacity-baseline/ground-truth.md`
- Cluster state changed after snapshot: No

## Run Independence

Each run will:

1. Start with a new conversation or cleared conversation history.
2. Use the exact `capacity-identical-v1` prompt.
3. Use the same model configuration.
4. Use the same Kubernetes cluster state.
5. Use no information from previous runs.
6. Save the final response and complete tool trace.


- Active Kubernetes Skill: `skills/kubernetes-control/SKILL.md`
- Active Skill SHA-256: `2e97b73381d8d2c8a91c30bb4e8163c3ae126e3f8cb8e8020c58917022edbd06`
- Additional Claude-specific Skill recorded: Yes, but not loaded by EdgePilot

- Provider ID: `claude`
- Default model: `claude-3-5-haiku-20241022`
- Model selection: `CLAUDE_MODEL`, falling back to the default model
- Active Skill: `skills/kubernetes-control/SKILL.md`
- Semantic-cache lookup: Enabled by application code
- Cache-control endpoint: `POST /api/cache/clear`
- Experiment cache policy: Clear immediately before every run
- Conversation policy: Create a new chat for every run