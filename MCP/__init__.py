"""Model Context Protocol (MCP) integration for EdgePilot."""

from .tool_executor import ToolExecutor, execute_tool, parse_tool_calls_from_text
from .tool_schemas import (
    TOOL_SCHEMAS,
    format_tools_for_claude,
    format_tools_for_gemini,
    get_all_tool_schemas,
    get_tool_schema,
)

__all__ = [
    "ToolExecutor",
    "execute_tool",
    "parse_tool_calls_from_text",
    "TOOL_SCHEMAS",
    "get_tool_schema",
    "get_all_tool_schemas",
    "format_tools_for_gemini",
    "format_tools_for_claude",
]
