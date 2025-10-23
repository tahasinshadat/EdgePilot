# EdgePilot - AI Copilot Console

EdgePilot is an **on-premises AI copilot** that combines a lightweight FastAPI backend with an Electron desktop UI. It features **full MCP (Model Context Protocol) integration**, enabling Gemini to autonomously monitor your system, launch applications, and manage processes through natural language.

## Highlights
- **🤖 MCP Integration** - Gemini can autonomously call tools for system monitoring, app launching, and process management
- **📊 Real-time Metrics** - CPU, memory, disk, network monitoring with process-level details and executable paths
- **🎯 Smart Tool Calling** - LLM automatically decides when to gather metrics, schedule tasks, or end processes
- **🖥️ Browser UI** - Dark, minimal chat interface served at `http://127.0.0.1:8000/app/`
- **🔌 Provider Abstraction** - Pluggable system supporting Gemini (with tools), Claude, and GPT
- **💾 Local Persistence** - JSON-based chat history and usage analytics (privacy-first)
- **🚀 Scalable Architecture** - Add new tools in minutes with simple 5-step process

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
# Test all tool calls and see their outputs
python main.py tools test-tools

# Verify metrics collection
python main.py tools metrics --top-n 5 --pretty
```

### 4. Try It Out!
Open the UI and try these prompts with **Gemini**:

**System Monitoring:**
- "What's my current CPU and memory usage?"
- "Show me the top 5 processes using the most CPU"

**Task Management:**
- "Launch notepad"
- "Open the calculator"

**Process Control:**
- "Close all Chrome instances"
- "Show me all Python processes with their paths"

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
├── main.py                  # FastAPI backend + CLI entry point
├── ui/                      # Electron desktop application
│   ├── index.html           # UI markup
│   ├── renderer.js          # Frontend logic
│   ├── styles.css           # Dark theme styling
│   └── main.js              # Electron main process
├── providers/               # LLM provider adapters
│   ├── base.py              # BaseLLM protocol + ToolCall classes
│   ├── gemini.py            # Gemini with function calling
│   ├── claude.py            # Claude adapter
│   └── gpt.py               # GPT placeholder
├── tools/                   # System utilities exposed as tools
│   ├── metrics.py           # System monitoring (CPU, memory, processes)
│   ├── app_search.py        # Smart application search
│   ├── schedule_task.py     # Application launcher with smart search
│   └── end_task.py          # Process termination
├── MCP/                     # Model Context Protocol integration
│   ├── tool_schemas.py      # Function calling schemas for all 4 tools
│   ├── tool_executor.py     # Tool execution engine
│   └── README.md            # Full MCP documentation
├── test/                    # Test suite
│   └── test.py              # Integration tests
├── env/.env                 # API keys and configuration
└── data/                    # JSON persistence
    ├── chat_history.json    # Chat sessions
    ├── usage_metrics.json   # API usage tracking
    └── tool_call_history.json  # Tool execution logs
```

## API Overview
- `GET /api/providers` – enumerate providers and configuration status
- `GET /api/chats` – list chat sessions with summary metadata
- `POST /api/chats` – create a new chat session
- `GET /api/chats/{chat_id}` – fetch full conversation history
- `POST /api/chats/{chat_id}/messages` – send a prompt and get LLM response (with tool calling)
- `GET /api/metrics` – retrieve current system metrics snapshot

## MCP (Model Context Protocol)

EdgePilot includes full MCP integration with **4 powerful tools**:

### Available Tools

#### 1. **gather_metrics** - System Monitoring
Collects comprehensive system metrics including CPU, memory, disk, network, battery, and all running processes with executable paths.

```python
# LLM can call this automatically when user asks about system status
gather_metrics(top_n=10, all_processes=False)
```

#### 2. **search_applications** - Application Search
Searches for applications installed on the system by name, returning matching apps with paths and relevance scores.

```python
# LLM calls this when user asks to find or launch an app
search_applications(query="minecraft", max_results=10)
```

#### 3. **schedule_task** - Application Launcher
Launches applications by path or command name with optional arguments, working directory, and smart search.

```python
# LLM calls this when user wants to launch an app
schedule_task(application="notepad", args=[], delay_seconds=0, cwd=None, search=True)
```

#### 4. **end_task** - Process Termination
Terminates processes by name, path, or command line identifier.

```python
# LLM calls this when user wants to close an app
end_task(identifier="chrome", force=False)
```

### How It Works
1. User sends a message in natural language
2. Gemini analyzes the request and decides if tools are needed
3. Tools are executed automatically (e.g., gathering metrics)
4. Results are fed back to Gemini
5. Gemini formulates a human-readable response

**Example:**
```
User: "Show me what's using the most CPU"
→ Gemini calls gather_metrics(top_n=3)
→ Receives: [{name: "chrome.exe", cpu: 15.2%, path: "C:\...\chrome.exe"}, ...]
→ Responds: "Chrome is using the most CPU at 15.2%..."
```

### Adding Your Own Tools
See `MCP/README.md` for the complete guide. It's a simple 5-step process:
1. Create tool function in `tools/`
2. Export it in `tools/__init__.py`
3. Add schema to `MCP/tool_schemas.py`
4. Add executor in `MCP/tool_executor.py`
5. Restart and test!

## CLI Tools & Utilities
```bash
# Test all tool calls with sample data
python main.py tools test-tools

# Dump metrics manually
python main.py tools metrics --top-n 5 --pretty

# Or run modules directly
python tools/metrics.py --all --pretty
python tools/app_search.py chrome --pretty

# Run integration tests
python test/test.py
```

## Extending Providers
1. Add a module under `providers/` implementing the `BaseLLM` protocol
2. Register it in `providers/__init__.py`
3. Add environment variables for API keys/models
4. For tool support, implement `enable_tools()` and parse `tool_calls` in responses

## Documentation
- **`README.md`** (this file) - Quick start and overview
- **`MCP/README.md`** - Complete MCP integration guide
- **`IMPLEMENTATION_SUMMARY.md`** - Technical implementation details

## License
MIT License - See LICENSE file for details
