# EdgePilot Copilot Console

EdgePilot combines a lightweight FastAPI backend with an Electron desktop UI that launches automatically when you start the app. The backend manages LLM providers, system metrics, and persistence, while the UI delivers a dark, minimal chat experience. You can still run the API on its own via the CLI when needed.

## Highlights
- **Browser UI** served at `http://127.0.0.1:8000/app/`, providing chat, provider switching, and live metrics.
- **FastAPI backend** exposing REST endpoints for chats, usage logging, and system telemetry.
- **Provider abstraction layer** (`providers/`) with a shared `BaseLLM` class and adapters for Gemini, Claude, and GPT.
- **Metrics tooling** (`tools/metrics.py`) returning JSON snapshots for CPU, memory, disk, and network activity.
- **Local persistence** via JSON files in `data/`, keeping chat history and usage analytics on disk.
- **MCP stub** reserved for wiring LLM tool calls later (intentionally unimplemented for now).

## Quick Start

### 1. Desktop App (API + Electron UI)
```bash
cd EdgePilot-Actual
python -m venv .venv
source .venv\Scripts\activate  # Windows
# source .venv/bin/activate  # macOS/Linux
pip install -r requirements.txt
cd ui && npm install  # one-time electron setup (requires Node.js 18+)
cd ..
python main.py  # launches the API and Electron desktop shell
```
Need a different host/port? Run the backend directly with `python main.py serve --host 0.0.0.0 --port 9000`. The electron app reads `BACKEND_URL`, which defaults to `http://127.0.0.1:8000`.

### 2. Environment Configuration
Fill out `env/.env` with any keys you have:
- `GEMINI_API_KEY` (recommended for local testing)
- `ANTHROPIC_API_KEY` (required for Claude)
- `OPENAI_API_KEY` (optional GPT placeholder)
- `DEFAULT_PROVIDER` (defaults to `gemini`)

### 3. Tools & Utilities
- Dump metrics via the CLI: `python main.py tools metrics --top-n 5`
- Or run the module directly: `python tools/metrics.py --pretty`

## Project Layout
```
EdgePilot-Actual/
├── README.md
├── requirements.txt
├── main.py                  # FastAPI backend + CLI entry point
├── frontend/                # Browser UI assets served at /app/ (used inside Electron)
├── providers/               # BaseLLM + individual provider adapters
├── tools/                   # System metrics helper modules
├── ui/                      # Optional Electron application (package.json, etc.)
├── env/.env                 # Environment configuration (API keys, defaults)
├── data/                    # JSON persistence for chats and usage
├── MCP/                     # Reserved for future MCP connector (empty stub)
└── assets/                  # Static assets (unchanged)
```

## API Overview
- `GET /api/providers` – enumerate providers and configuration status.
- `GET /api/chats` – list chat sessions with summary metadata.
- `POST /api/chats` – create a new chat session.
- `GET /api/chats/{chat_id}` – fetch full conversation history.
- `POST /api/chats/{chat_id}/messages` – send a prompt to the selected provider and append the reply.
- `GET /api/metrics` – retrieve the current host metrics snapshot.

## Extending Providers
1. Add a module under `providers/` implementing the `BaseLLM` protocol.
2. Register it in `providers/__init__.py`.
3. Surface the necessary environment variables for API keys/models.
4. Update the UI (browser/Electron) if you want to expose extra provider metadata.

## MCP Stub
`MCP/` is intentionally empty for now. It will eventually host the Model Context Protocol bridge so LLMs can call your tool functions once they are ready.
