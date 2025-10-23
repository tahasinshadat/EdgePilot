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
        "name": "launch",
        "description": "Launch an application by name, immediately or after a delay. The application name will be searched in Windows Start Menu shortcuts and Microsoft Store apps. You can use simple names like 'chrome', 'minecraft', 'notepad'. If you need to check if an app exists first, use the 'search' tool.",
        "parameters": {
            "type": "object",
            "properties": {
                "app_name": {
                    "type": "string",
                    "description": "Application name to launch (e.g., 'chrome', 'minecraft', 'notepad', 'discord'). The system will search for matching apps in Start Menu and Microsoft Store.",
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
        "description": "Search for installed applications by name. Use this to check if an app is installed or to find the correct app name before launching. Returns a list of matching application names found in Start Menu and Microsoft Store.",
        "parameters": {
            "type": "object",
            "properties": {
                "app_name": {
                    "type": "string",
                    "description": "Application name to search for (e.g., 'game', 'chrome', 'office'). Partial matches are supported.",
                },
            },
            "required": ["app_name"],
        },
    },
    {
        "name": "list_apps",
        "description": "List all installed applications, optionally filtered by a search term. Use this when the user asks 'what apps do I have?' or 'list my games'. Returns a sorted list of all applications found in Start Menu.",
        "parameters": {
            "type": "object",
            "properties": {
                "filter_term": {
                    "type": "string",
                    "description": "Optional search term to filter results (e.g., 'game', 'microsoft'). Leave empty to get all apps.",
                    "default": "",
                },
            },
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
