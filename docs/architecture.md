# EdgePilot — Architecture

## What it is

An on-premises AI copilot for cluster operations. You ask a question in plain
English. It reads real system state through tools, then either answers or
proposes an action. Anything that changes state stops and asks you first.

Everything runs locally. Cluster data and job records never leave the machine.

## The system

```mermaid
flowchart TB
    User(["User"])

    subgraph Desktop["Desktop app"]
        UI["Electron UI<br/><i>chat, live metrics, approval prompts</i>"]
    end

    subgraph Backend["Backend — FastAPI, runs locally"]
        API["Chat API<br/><i>streams responses</i>"]
        Loop["Agent loop<br/><i>up to 15 rounds of tool calls</i>"]
        Gate{{"Approval gate<br/><i>12 tools need a human yes</i>"}}
        Cache["Semantic cache<br/><i>skips repeat questions</i>"]
    end

    subgraph Models["AI providers"]
        Claude["Claude"]
        Gemini["Gemini"]
    end

    Skill["Skill<br/><i>kubernetes-control:<br/>rules for safe operation</i>"]

    subgraph Tools["Tool registry — 40 tools"]
        K8s["Kubernetes<br/><i>inspect, scale, restart,<br/>cordon, migrate</i>"]
        Slurm["Slurm / HPC<br/><i>job accounting, queue,<br/>rightsizing</i>"]
        Metrics["Metrics<br/><i>CPU, memory, disk,<br/>network, Prometheus</i>"]
        Local["Local machine<br/><i>processes, disk, apps</i>"]
    end

    Systems[("Kubernetes cluster<br/>Slurm cluster<br/>Local host")]

    User <--> UI
    UI <--> API
    API --> Cache
    API --> Loop
    Loop <--> Models
    Skill -.->|"instructions"| Models
    Loop --> Gate
    Gate -->|"approved"| Tools
    Gate -.->|"denied"| Loop
    Tools <--> Systems
    Tools -->|"results"| Loop

    style Gate fill:#F3EDDA,stroke:#8A6D1F,stroke-width:2px
    style Skill fill:#EDE7F6,stroke:#4E2A84
```

## The pieces

| Piece | What it does |
|---|---|
| **Electron UI** | Desktop chat window, live telemetry, approval prompts |
| **FastAPI backend** | Runs locally. Manages chats, calls the model, executes tools |
| **Agent loop** | Model calls a tool → backend runs it → result goes back to the model → repeat until done |
| **Approval gate** | 12 of the 40 tools change state. Each one stops and waits for a human |
| **Skill** | A written set of rules the model follows: verify capacity, explain the change, never guess a name |
| **Tool registry** | 40 tools. 25 read-only, 15 change something |
| **Semantic cache** | Recognises a repeat question and answers without calling the model |
| **Providers** | Claude and Gemini are swappable. GPT is a placeholder |

## Where the data comes from

- **Kubernetes** — live cluster, via the Kubernetes API
- **Prometheus / Grafana** — hardware metrics
- **Slurm** — job accounting and queue state. Built, but **not yet connected to
  real data**; waiting on Northwestern Quest access. Tested against mock data
- **Local host** — CPU, memory, disk, processes
