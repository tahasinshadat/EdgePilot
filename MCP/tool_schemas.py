"""Tool schemas for MCP function calling integration."""

from __future__ import annotations

from typing import Any, Dict, List

# Tool schemas following the function calling format for LLMs
TOOL_SCHEMAS: List[Dict[str, Any]] = [
    {
        "name": "gather_metrics",
        "description": "Collect comprehensive system metrics including CPU, memory, disk, network, battery, and process information. Use this to understand the current system state, identify resource bottlenecks, or monitor running applications.",
        "parameters": {
            "type": "object",
            "properties": {
                "top_n": {
                    "type": "integer",
                    "description": "Number of top processes by CPU usage to include. Defaults to 10. Ignored if all_processes is True.",
                    "default": 10,
                },
                "all_processes": {
                    "type": "boolean",
                    "description": "If True, include all running processes instead of just top N. Use this when you need complete process information.",
                    "default": False,
                },
            },
        },
    },
    {
        "name": "report_edge_status",
        "description": "Summarize host utilization over a recent window using Prometheus when available, otherwise fall back to local psutil data.",
        "parameters": {
            "type": "object",
            "properties": {
                "window": {
                    "type": "string",
                    "description": "Prometheus time window to evaluate (e.g., '1h', '6h'). Defaults to 1h.",
                    "default": "1h",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Number of top processes or rank entries to include when applicable.",
                    "default": 5,
                },
            },
        },
    },
    {
        "name": "evaluate_capacity",
        "description": "Assess whether the host (or a Prometheus instance) currently has enough headroom for a workload.",
        "parameters": {
            "type": "object",
            "properties": {
                "requirements": {
                    "type": "object",
                    "description": "Workload requirements (e.g., {'cpu_pct': 40, 'mem_bytes': 2147483648}).",
                },
                "duration": {
                    "type": "string",
                    "description": "Intended runtime duration for the workload (Prometheus reference). Defaults to '45m'.",
                    "default": "45m",
                },
                "host": {
                    "type": "string",
                    "description": "Optional Prometheus instance label to check. Leave empty to evaluate all instances.",
                },
            },
            "required": ["requirements"],
        },
    },
    {
        "name": "suggest_capacity_window",
        "description": "Suggest upcoming windows when resource headroom is likely sufficient for a workload.",
        "parameters": {
            "type": "object",
            "properties": {
                "requirements": {
                    "type": "object",
                    "description": "Workload requirements (e.g., {'cpu_pct': 30, 'mem_bytes': 1073741824}).",
                },
                "duration": {
                    "type": "string",
                    "description": "Desired runtime duration (e.g., '1h'). Defaults to '45m'.",
                    "default": "45m",
                },
                "horizon_hours": {
                    "type": "integer",
                    "description": "How far ahead to look when suggesting windows. Defaults to 24 hours.",
                    "default": 24,
                },
                "host": {
                    "type": "string",
                    "description": "Optional Prometheus instance label to focus on.",
                },
            },
            "required": ["requirements"],
        },
    },
    {
        "name": "launch",
        "description": "Launch an application by name, immediately or after a delay. Cross-platform: on Windows we search Start Menu shortcuts and Microsoft Store apps; on macOS we resolve .app bundles and fall back to 'open -a <name>'; on Linux we scan .desktop files in standard locations (including Flatpak/Snap) and fall back to $PATH. Use simple names like 'chrome', 'safari', 'calculator', 'notepad'. If you need to check if an app exists first, use the 'search' tool.",
        "parameters": {
            "type": "object",
            "properties": {
                "app_name": {
                    "type": "string",
                    "description": "Application name to launch (e.g., 'chrome', 'safari', 'calculator', 'discord'). The system searches Windows Start Menu/Store, macOS .app bundles, and Linux .desktop entries; if not found, it may try the name on $PATH.",
                },
                "delay_seconds": {
                    "type": "number",
                    "description": "Number of seconds to wait before launching. Default is 0 (launch immediately). Examples: 30 for '30 seconds', 120 for '2 minutes'.",
                    "default": 0,
                },
            },
            "required": ["app_name"],
        },
    },
    {
        "name": "search",
        "description": "Search for installed applications by name. Cross-platform: searches Windows Start Menu/Microsoft Store, macOS .app bundles, and Linux .desktop entries (including Flatpak/Snap). Returns friendly application names that you can pass to 'launch'.",
        "parameters": {
            "type": "object",
            "properties": {
                "app_name": {
                    "type": "string",
                    "description": "Application name to search for (e.g., 'term', 'chrome', 'office'). Partial matches are supported.",
                },
            },
            "required": ["app_name"],
        },
    },
    {
        "name": "list_apps",
        "description": "List all installed applications, optionally filtered by a search term. Cross-platform: enumerates Windows Start Menu, macOS .app bundles, and Linux .desktop entries. Returns a sorted list of friendly application names.",
        "parameters": {
            "type": "object",
            "properties": {
                "filter_term": {
                    "type": "string",
                    "description": "Optional search term to filter results (e.g., 'term', 'microsoft'). Leave empty to get all apps.",
                    "default": "",
                },
            },
        },
    },
    {
        "name": "run_shell",
        "description": "Execute a shell command on the local machine and return stdout/stderr. Use with caution for admin tasks or quick diagnostics.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Command to execute (e.g., 'ls -la', 'df -h')."
                },
                "cwd": {
                    "type": "string",
                    "description": "Optional working directory for the command."
                },
                "delay_seconds": {
                    "type": "number",
                    "description": "Number of seconds to wait before running the command. Example: 30 for '30 seconds'.",
                    "default": 0,
                },
                "seconds": {
                    "type": "number",
                    "description": "Alias for delay_seconds. Use when a model extracts 'seconds' from the request.",
                },
                "delay": {
                    "type": "string",
                    "description": "Natural language delay value (e.g., 'in 45 seconds', 'after 2 minutes').",
                },
            },
            "required": ["command"]
        }
    },
    {
        "name": "run_python",
        "description": "Execute a Python script using the scheduler runtime. Provide the script path and optional arguments.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute path to the Python script."
                },
                "args": {
                    "type": "array",
                    "items": {
                        "type": "string"
                    },
                    "description": "Optional list of command-line arguments for the script.",
                    "default": []
                },
                "cwd": {
                    "type": "string",
                    "description": "Optional working directory."
                },
                "delay_seconds": {
                    "type": "number",
                    "description": "Number of seconds to wait before running the script. Example: 30 for '30 seconds'.",
                    "default": 0,
                },
                "seconds": {
                    "type": "number",
                    "description": "Alias for delay_seconds. Use when a model extracts 'seconds' from input.",
                },
                "delay": {
                    "type": "string",
                    "description": "Natural language delay value (e.g., 'after 2 minutes').",
                },
            },
            "required": ["path"]
        }
    },
    {
        "name": "get_task_status",
        "description": "Retrieve the latest status or output for a previously scheduled action (e.g., delayed Python script or shell command). Use this to answer follow-up questions such as 'what was the output?'.",
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Unique task identifier returned when the action was scheduled.",
                },
                "action": {
                    "type": "string",
                    "enum": ["run_python", "run_shell", "open_application"],
                    "description": "Type of action to look up. If omitted, defaults to 'run_python' when a path is provided or 'run_shell' when a command is provided.",
                },
                "path": {
                    "type": "string",
                    "description": "Path to the Python script whose status or output you want. Used for run_python actions.",
                },
                "command": {
                    "type": "string",
                    "description": "Shell command string to check. Used for run_shell actions.",
                },
                "identifier": {
                    "type": "string",
                    "description": "Generic identifier when neither path nor command apply.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Optional number of historical records to return (most recent first). Defaults to 1.",
                    "minimum": 1,
                    "default": 1,
                },
            },
            "required": [],
        },
    },
    {
        "name": "end_task",
        "description": "Terminate running processes matching the identifier. The identifier can be part of the process name, executable path, or command line. Use this to stop applications, kill hung processes, or clean up resources.",
        "parameters": {
            "type": "object",
            "properties": {
                "identifier": {
                    "type": "string",
                    "description": "Process identifier to match. Can be part of the process name (e.g., 'notepad'), executable path (e.g., 'C:\\Program Files\\App\\'), or command line arguments. Matching is case-insensitive.",
                },
                "force": {
                    "type": "boolean",
                    "description": "If True, forcefully kill processes (SIGKILL). If False, gracefully terminate (SIGTERM). Default is False.",
                    "default": False,
                },
            },
            "required": ["identifier"],
        },
    },
]


def get_tool_schema(tool_name: str) -> Dict[str, Any] | None:
    """Get schema for a specific tool by name."""
    for schema in TOOL_SCHEMAS:
        if schema["name"] == tool_name:
            return schema
    return None


def get_all_tool_schemas() -> List[Dict[str, Any]]:
    """Get all available tool schemas."""
    return TOOL_SCHEMAS.copy()


def format_tools_for_gemini() -> List[Dict[str, Any]]:
    """
    Format tool schemas for Gemini function calling API.

    Gemini expects a different format than the standard function calling schema.
    """
    gemini_tools = []
    for schema in TOOL_SCHEMAS:
        gemini_tool = {
            "name": schema["name"],
            "description": schema["description"],
            "parameters": schema["parameters"],
        }
        gemini_tools.append(gemini_tool)
    return gemini_tools


def format_tools_for_claude() -> List[Dict[str, Any]]:
    """
    Format tool schemas for Claude function calling API.

    Claude uses a specific tool format.
    """
    claude_tools = []
    for schema in TOOL_SCHEMAS:
        claude_tool = {
            "name": schema["name"],
            "description": schema["description"],
            "input_schema": schema["parameters"],
        }
        claude_tools.append(claude_tool)
    return claude_tools
