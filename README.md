# EdgePilot - AI Copilot Console

EdgePilot is an **on-premises AI copilot** that combines a lightweight FastAPI backend with an Electron desktop UI. It features **full MCP (Model Context Protocol) integration**, enabling Gemini to autonomously monitor your system, launch applications with scheduling, and manage processes through natural language.

## Highlights
- **🤖 MCP Integration** - Gemini can autonomously call tools for system monitoring, app launching, and process management
- **📊 Real-time Metrics** - CPU, memory, disk, network monitoring with process-level details and executable paths
- **🚀 Smart App Launcher** - Launch applications by name with delay support using Windows Start Menu search
- **🎯 Smart Tool Calling** - LLM automatically decides when to gather metrics, launch apps, or end processes
- **🖥️ Desktop UI** - Electron-based chat interface with dark theme
- **🔌 Provider Abstraction** - Pluggable system supporting Gemini (with tools), Claude, and GPT
- **💾 Local Persistence** - JSON-based chat history and usage analytics (privacy-first)
- **⚡ Lightweight** - Clean codebase focused on core functionality

## Quick Start

### 1. Setup & Installation
```bash
# Install dependencies
pip install -r requirements.txt

# Configure your API key
# Edit env/.env and add: GEMINI_API_KEY=your_key_here

# Install Electron UI (one-time, requires Node.js 18+)
cd ui && npm install && cd ..
```

### 2. Run EdgePilot
```bash
# Launch the full application (API + Electron UI)
python main.py

# Or run API only:
python main.py serve --host 127.0.0.1 --port 8000
```

### 3. Test Tools
```bash
# Test all MCP tools integration
python test_tools.py

# Test launcher directly
python tools/launcher.py
```

## Command-Line Interface (CLI)
The CLI lets you ask questions, schedule jobs, and inspect the queue without opening the UI.

```bash
# Start an interactive REPL (works on macOS, Linux, and Windows)
python -m edgepilot_cli start

# One-shot questions
python -m edgepilot_cli ask "Can I run a heavy build right now?"
python -m edgepilot_cli ask "List my last few jobs" --format json

# Queue new work
python -m edgepilot_cli schedule --action run_shell --command "echo hello" --delay 5
python -m edgepilot_cli schedule --action launch --command "Calculator"

# Inspect the scheduler
python -m edgepilot_cli status --limit 10
```

Additional commands:
- `edgepilot_cli activate` – alias for the interactive REPL
- `edgepilot_cli ask --context-file context.json` – include JSON context or change the system prompt

EdgePilot automatically detects your OS and picks the right application launcher or shell runner.

## Local REST API
Run the backend (`python -m main serve --host 127.0.0.1`) and interact with the new endpoints:

- `POST /api/ask` — submit natural-language questions via JSON payloads.  
  Example:
  ```bash
  curl -X POST http://127.0.0.1:8000/api/ask \
    -H "Content-Type: application/json" \
    -d '{"query": "Is it safe to start a GPU job?", "response_format": "json"}'
  ```
- `POST /api/schedule` — queue new shell/python/launch tasks.
  ```bash
  curl -X POST http://127.0.0.1:8000/api/schedule \
    -H "Content-Type: application/json" \
    -d '{"action":"run_shell","command":"echo from API","delay_seconds":0}'
  ```
- `GET /api/tasks` — list recent scheduled tasks or filter by action.

The API binds to localhost by default, rejects malformed payloads with HTTP 400, and never writes request bodies to logs.

### 4. Try It Out!
Open the UI and try these prompts with **Gemini**:

**System Monitoring:**
- "What's my current CPU and memory usage?"
- "Show me the top 5 processes using the most CPU"

**Application Discovery:**
- "What apps do I have installed?"
- "Do I have Discord installed?"
- "List all my games"

**Application Launching:**
- "Launch notepad"
- "Open Chrome in 30 seconds"
- "Start Minecraft in 1 minute"

**Process Control:**
- "Close all Chrome instances"
- "End the notepad process"

### Optional: Enable Prometheus Metrics
EdgePilot can pull historical metrics from Prometheus when `PROM_URL` is set. A helper script downloads Prometheus, prepares a default config, installs node_exporter, and prints the commands to launch both services:

```bash
chmod +x scripts/bootstrap_prometheus.sh
./scripts/bootstrap_prometheus.sh   # follow the start instructions it prints
```

After the script runs it updates `env/.env` with sensible defaults (`PROM_URL=http://localhost:9090`, `PROM_TIMEOUT_SEC=15`) and adds a `node` scrape job. You can launch/stop the metrics stack in the background at any time:
```bash
./scripts/bootstrap_prometheus.sh start   # starts Prometheus + node_exporter (logs in ~/.edgepilot/logs)
./scripts/bootstrap_prometheus.sh status  # check running pids
./scripts/bootstrap_prometheus.sh stop    # stop both services
```

Finally, restart the EdgePilot backend so it picks up the new environment variables. Queries like `report_edge_status(window="6h")` will then read from Prometheus instead of the local fallback.

## Environment Configuration
Edit `env/.env`:
```bash
GEMINI_API_KEY=your_gemini_key        # Required for MCP tools
ANTHROPIC_API_KEY=your_claude_key     # Optional
OPENAI_API_KEY=your_openai_key        # Optional
DEFAULT_PROVIDER=gemini               # Use gemini for tool calling
```

## Project Layout
```
EdgePilot/
├── README.md
├── requirements.txt
├── test_tools.py            # MCP tools integration test
├── main.py                  # FastAPI backend + CLI entry point
├── ui/                      # Electron desktop application
│   ├── index.html           # UI markup
│   ├── renderer.js          # Frontend logic
│   ├── styles.css           # Dark theme styling
│   ├── main.js              # Electron main process
│   └── package.json         # Node.js dependencies
├── providers/               # LLM provider adapters
│   ├── base.py              # BaseLLM protocol + ToolCall classes
│   ├── gemini.py            # Gemini with function calling
│   ├── claude.py            # Claude adapter
│   └── gpt.py               # GPT placeholder
├── tools/                   # System utilities exposed as tools
│   ├── __init__.py          # Export metrics, scheduler, process helpers
│   ├── metrics.py           # psutil + Prometheus-backed host reporting
│   ├── scheduler.py         # Task registry + app launcher + shell/python runner
│   └── end_task.py          # Process termination
├── MCP/                     # Model Context Protocol integration
│   ├── tool_schemas.py      # Function calling schemas for all 5 tools
│   ├── tool_executor.py     # Tool execution engine
│   └── README.md            # Full MCP documentation
├── env/.env                 # API keys and configuration
├── scripts/
│   └── bootstrap_prometheus.sh  # Installs Prometheus + node_exporter and updates env/config
└── data/                    # JSON persistence + blueprints
    ├── chat_history.json    # Chat sessions
    ├── usage_metrics.json   # API usage tracking
    ├── tool_call_history.json  # Tool execution logs
    ├── ring.edgepilot.json      # Metrics entity definitions
    └── blueprint.edge_status.json # Edge status reporting plan
```

## API Overview
- `GET /api/providers` – enumerate providers and configuration status
- `GET /api/chats` – list chat sessions with summary metadata
- `POST /api/chats` – create a new chat session
- `GET /api/chats/{chat_id}` – fetch full conversation history
- `POST /api/chats/{chat_id}/messages` – send a prompt and get LLM response (with tool calling)
- `GET /api/metrics` – retrieve current system metrics snapshot
- `POST /api/ask` – answer natural-language questions with shared assistant logic
- `POST /api/schedule` – queue shell/python/launch tasks
- `GET /api/tasks` – show the scheduler queue/status

## MCP (Model Context Protocol)

EdgePilot includes full MCP integration with **5 powerful tools** using launcher.py for intelligent app launching:

### Available Tools

#### 1. **gather_metrics** - System Monitoring
Collects comprehensive system metrics including CPU, memory, disk, network, battery, and all running processes with executable paths.

```python
# LLM can call this automatically when user asks about system status
gather_metrics(top_n=10, all_processes=False)
```

#### 2. **launch** - Application Launcher with Scheduling
Launch applications by name with optional delay. Uses Windows Start Menu search and Microsoft Store app discovery.

```python
# LLM calls this when user wants to launch an app
launch(app_name="chrome", delay_seconds=0)
launch(app_name="minecraft", delay_seconds=30)  # Launch in 30 seconds
```

**Features:**
- Searches Windows Start Menu shortcuts
- Finds Microsoft Store/UWP apps
- Supports delayed execution with threading
- Simple app names (no paths needed)

#### 3. **search** - Application Discovery
Search for installed applications by name. Returns list of matching apps found in Start Menu and Microsoft Store.

```python
# LLM calls this to check if an app is installed
search(app_name="discord")  # Returns: ["Discord"]
search(app_name="game")     # Returns: ["Game Bar", "Steam", ...]
```

#### 4. **list_apps** - Browse Installed Applications
List all installed applications with optional filtering. Perfect for "what apps do I have?" queries.

```python
# LLM calls this to browse available apps
list_apps(filter_term="")       # Returns all apps
list_apps(filter_term="game")   # Returns only apps with "game" in name
```

#### 5. **end_task** - Process Termination
Terminates processes by name, path, or command line identifier.

```python
# LLM calls this when user wants to close an app
end_task(identifier="chrome", force=False)
end_task(identifier="notepad", force=True)
```

### How It Works
1. User sends a message in natural language
2. Gemini analyzes the request and decides which tools to call
3. Tools are executed automatically (e.g., launching apps, gathering metrics)
4. Results are fed back to Gemini
5. Gemini formulates a human-readable response

**Example 1: System Monitoring**
```
User: "Show me what's using the most CPU"
→ Gemini calls gather_metrics(top_n=3)
→ Receives: {processes: [{name: "chrome.exe", cpu: 15.2%, ...}]}
→ Responds: "Chrome is using the most CPU at 15.2%..."
```

**Example 2: Scheduled App Launch**
```
User: "Launch Minecraft in 30 seconds"
→ Gemini calls launch(app_name="minecraft", delay_seconds=30)
→ Receives: {success: true, message: "Scheduled 'minecraft' to launch in 30 seconds"}
→ Responds: "I've scheduled Minecraft to launch in 30 seconds!"
```

**Example 3: App Discovery**
```
User: "What games do I have?"
→ Gemini calls list_apps(filter_term="game")
→ Receives: {count: 3, apps: ["Game Bar", "Steam", "Minecraft"]}
→ Responds: "You have 3 games installed: Game Bar, Steam, and Minecraft"
```

### Adding Your Own Tools
See `MCP/README.md` for the complete guide. It's a simple 5-step process:
1. Create tool function in `tools/`
2. Export it in `tools/__init__.py`
3. Add schema to `MCP/tool_schemas.py`
4. Add executor in `MCP/tool_executor.py`
5. Restart and test!

## Testing & Utilities
```bash
# Test all MCP tools integration
python test_tools.py

# Test launcher directly (launches notepad, chrome, minecraft)
python tools/launcher.py

# Run modules directly
python -c "from tools import gather_metrics; print(gather_metrics(top_n=5))"
python -c "from tools import search; print(search('chrome'))"
python -c "from tools import list_apps; print(list_apps('game'))"
```

## Extending Providers
1. Add a module under `providers/` implementing the `BaseLLM` protocol
2. Register it in `providers/__init__.py`
3. Add environment variables for API keys/models
4. For tool support, implement `enable_tools()` and parse `tool_calls` in responses

## Key Features Powered by launcher.py

EdgePilot's application launching is powered by `launcher.py`, which provides:

1. **Windows Start Menu Search** - Searches .lnk shortcuts in user and system Start Menu locations
2. **Microsoft Store Apps** - Discovers and launches UWP/Store apps via PowerShell
3. **Delayed Execution** - Background threading for scheduled launches
4. **Intelligent Fallback** - Falls back to Windows `start` command for built-in apps
5. **Simple API** - Just 3 core functions: `launch()`, `search()`, `list_apps()`

The LLM can use simple app names like "chrome", "minecraft", or "notepad" without needing full paths!

## Documentation
- **`README.md`** (this file) - Quick start and overview
- **`MCP/README.md`** - Complete MCP integration guide
- **`tools/launcher.py`** - Application launcher implementation with detailed documentation

## License
MIT License - See LICENSE file for details
