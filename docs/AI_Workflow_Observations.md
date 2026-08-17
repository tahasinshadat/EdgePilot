# AI Workflow Evaluation

**Date**: August 2026
**Objective**: Evaluate EdgePilot's AI capabilities in completing both single-turn (Simple) and multi-turn (Complex) Kubernetes workflows. This document acts as the formal data-science deliverable for the AI workflow track.

---

## 1. Experiment Methodology & Hypotheses

### Testing Environment
- **Simulated Cluster**: Local Kubernetes cluster
- **Fault Scenarios injected**:
  1. `crypto_miner.yaml` - A deployment opening an unexpected port (`3333`) and consuming CPU.
  2. `memory_hog.yaml` - A deployment consuming high memory without limits, stressing its host node.

### The Hypotheses
**Simple Workflow Hypothesis**:
> "Given a single-turn question about a cluster anomaly (e.g., 'Is there any network port open by any application?'), the AI will consistently query the cluster state using MCP tools and return the correct port (3333) across 5 repeated trials."

**Multi-turn Workflow Hypothesis**:
> "Given a complex anomaly requiring state mutation (e.g., 'One node is stressed by high memory consumption from two applications — can we migrate one of them to the other node?'), the AI will successfully detect the memory hog, formulate a migration plan, and use the `migrate_workload` tool to force the pod to a new node, effectively resolving the stress."

---

## 2. Quantitative Results

### Experiment A: Simple Workflow (Single-turn)
**Prompt**: *"Is there any network port open by any application?"*

| Model | Success Rate (x/5) | Average Tool Calls | Failures / Hallucinations |
|-------|-------------------|--------------------|---------------------------|
| Gemini | 5 / 5          | 2                  | None                      |
| Claude | [ ] / 5          |                    |                           |

*(Note: Claude tests to be run later).*

### Experiment B: Complex Workflow (Multi-turn Migration)
**Prompt**: *"One node is stressed by high memory consumption from two applications — can we migrate one of them to the other node?"*

| Model | Detects Issue? | Plans Migration? | Migrates Successfully? | Overall Success Rate |
|-------|----------------|------------------|------------------------|----------------------|
| Gemini | Yes            | Yes              | Yes                    | 4 / 5              |
| Claude | Yes/No         | Yes/No           | Yes/No                 | [ ] / 5              |

---

## 3. Qualitative Observations

### 3.1 What was technically hard?
*(Document your observations here. E.g., Was the AI struggling to understand which node was which? Did it fail to parse the `nodeSelector` JSON correctly?)*

- **Observation 1**: The AI occasionally struggled to identify the correct target node when there were multiple healthy nodes, sometimes trying to migrate the workload back to the same node it was already on.
- **Observation 2**: Parsing the exact namespace was tricky; it defaulted to the `default` namespace but sometimes needed an explicit reminder if the app was in a different namespace.

### 3.2 What was not feasible?
*(Document any workflow steps the AI completely failed at, requiring code changes or abandonment).*

- **Finding**: The AI could not reliably perform the migration using only `cordon_node` and `restart_workload`, as Kubernetes scheduling is non-deterministic. The dedicated `migrate_workload` tool was strictly necessary.

### 3.3 Which assumptions broke in practice?
*(Document assumptions made before testing. E.g., "We assumed the AI would check the node's capacity before migrating the pod to it, but it just migrated it blindly.")*

- **Assumption**: We assumed the AI would automatically check the target node's available memory capacity before migrating the workload.
- **Reality**: The AI blindly migrated the workload to the first node it saw without using `evaluate_capacity` unless explicitly prompted to "find a healthy node first."

### 3.4 Which parts needed manual intervention?
*(Document the Human-In-The-Loop safety aspects. Did you have to deny any dangerous actions that the AI hallucinatively attempted?)*

- **Intervention 1**: On one failed trial, the AI attempted to `drain_k8s_node` on the stressed node instead of just migrating the single problematic workload. I had to hit 'Deny' on the Human-in-the-Loop prompt.

---

## 4. Conclusion
Based on the current experiments, EdgePilot's AI capabilities demonstrate strong proficiency in single-turn observability queries (achieving 100% success on the Simple workflow) but require further maturity for complex, multi-turn state mutations. While the introduction of the dedicated `migrate_workload` tool solved the deterministic scheduling problem, the AI still exhibits dangerous failure modes—such as neglecting to verify target node capacity or hallucinatively attempting to drain entire nodes instead of migrating individual pods. Consequently, while EdgePilot is highly valuable as a read-only Kubernetes assistant, any mutating AI workflows must remain gated behind strict Human-In-The-Loop approvals before being considered production-ready.
