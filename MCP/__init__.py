"""Model Context Protocol (MCP) integration for EdgePilot."""

from .tool_executor import (
    ToolExecutor,
    execute_tool,
    execute_tool_async,
    execute_tools_batch,
    parse_tool_calls_from_text,
)
from .tool_schemas import (
    MUTATING_TOOLS,
    TOOL_SCHEMAS,
    format_tools_for_claude,
    format_tools_for_gemini,
    format_tools_for_provider,
    get_all_tool_schemas,
    get_tool_schema,
    is_mutating,
)

__all__ = [
    "ToolExecutor",
    "execute_tool",
    "execute_tool_async",
    "execute_tools_batch",
    "parse_tool_calls_from_text",
    "TOOL_SCHEMAS",
    "get_tool_schema",
    "get_all_tool_schemas",
    "format_tools_for_gemini",
    "format_tools_for_claude",
    "format_tools_for_provider",
    "MUTATING_TOOLS",
    "is_mutating",
]
