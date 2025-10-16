# EdgePilot™ — Your AI Copilot for System Health, Scheduling, and Optimization

EdgePilot is a lightweight, on‑prem AI copilot that understands a host (or small edge cluster) and helps you decide:

- **Can I run this job now?**
- **What’s bottlenecking my pipeline?**
- **When should I schedule tasks for the best energy profile?**

It exposes **system metrics** and a **local task scheduler** via the **Model Context Protocol (MCP)**, so any MCP‑capable LLM can read live data and justify decisions. A simple **Streamlit UI** and **Typer CLI** are included.

> **Everything runs locally** on macOS and Linux. Optional cloud providers (Claude/Gemini) are supported, but the default is local **Ollama**.

---

## Architecture

The repository reflects the “EdgePilot Architecture” diagram:

- **Frontend**: Streamlit UI + Typer CLI
- **Backend**: FastAPI, Metrics Service, MCP server, Scheduler, SQLite storage
- **MCP Tools**:
  - `metrics.snapshot`, `metrics.stream_start`, `metrics.stream_stop`
  - `runs.start`, `runs.end`
  - `scheduler.enqueue`, `scheduler.list`, `scheduler.cancel`, `scheduler.policy_set`, `scheduler.simulate`
  - `usage.stats`

---

## Quick Start (macOS & Linux)

### 0) Prereqs

- Python **3.11+**
- (Optional) [Ollama](https://ollama.ai) with a local model (e.g., `llama3.2:3b`):
  ```bash
  brew install ollama   # macOS
  # or see Linux install on ollama.ai
  ollama pull llama3.2:3b
    1) Install EdgePilot
    git clone . edgepilot
    cd edgepilot
    make setup

2) First‑run setup
edgepilot wizard


Choose provider (Ollama recommended)

Accept defaults or customize ports/paths

If on macOS, you may allow power metrics (optional; uses pmset non‑privileged call by default)

3) Run services

In separate terminals:

# API
edgepilot api

# MCP server (stdio transport)
edgepilot mcp

# UI
edgepilot ui


API runs at http://127.0.0.1:8000

UI runs at http://127.0.0.1:8501