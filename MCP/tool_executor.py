"""Tool executor for MCP function calling."""

from __future__ import annotations

import json
from typing import Any, Dict

from tools import end_task, gather_metrics, launch, search, list_apps


class ToolExecutor:
    """Execute tool calls from LLM responses."""

    def __init__(self):
        """Initialize the tool executor with available tools."""
        self.tools = {
            "gather_metrics": self._execute_gather_metrics,
            "launch": self._execute_launch,
            "search": self._execute_search,
            "list_apps": self._execute_list_apps,
            "end_task": self._execute_end_task,
        }

    def execute(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a tool call with the given arguments.

        Parameters
        ----------
        tool_name:
            Name of the tool to execute.
        arguments:
            Dictionary of arguments to pass to the tool.

        Returns
        -------
        Dictionary with the tool execution result and any error information.
        """
        if tool_name not in self.tools:
            return {
                "success": False,
                "error": f"Unknown tool: {tool_name}",
                "available_tools": list(self.tools.keys()),
            }

        try:
            result = self.tools[tool_name](arguments)
            return {
                "success": True,
                "tool": tool_name,
                "arguments": arguments,
                "result": result,
            }
        except Exception as error:
            return {
                "success": False,
                "tool": tool_name,
                "arguments": arguments,
                "error": str(error),
                "error_type": type(error).__name__,
            }

    def _execute_gather_metrics(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Execute gather_metrics tool."""
        top_n = args.get("top_n", 10)
        all_processes = args.get("all_processes", False)
        return gather_metrics(top_n=top_n, all_processes=all_processes)

    def _execute_launch(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Execute launch tool to start an application."""
        app_name = args.get("app_name")
        if not app_name:
            raise ValueError("app_name parameter is required")

        delay_seconds = args.get("delay_seconds", 0)

        # Use launcher.py's launch function
        success = launch(app_name, delay_seconds)

        if success:
            if delay_seconds > 0:
                message = f"Scheduled '{app_name}' to launch in {delay_seconds} seconds"
            else:
                message = f"Launched '{app_name}'"

            return {
                "success": True,
                "message": message,
                "app_name": app_name,
                "delay_seconds": delay_seconds,
            }
        else:
            return {
                "success": False,
                "error": f"Could not find or launch '{app_name}'",
                "app_name": app_name,
            }

    def _execute_end_task(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Execute end_task tool."""
        identifier = args.get("identifier")
        if not identifier:
            raise ValueError("identifier parameter is required")

        force = args.get("force", False)
        exact_path = args.get("exact_path", False)

        return end_task(identifier=identifier, force=force, exact_path=exact_path)

    def _execute_search(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Execute search tool to find installed applications."""
        app_name = args.get("app_name")
        if not app_name:
            raise ValueError("app_name parameter is required")

        results = search(app_name)

        return {
            "query": app_name,
            "found": len(results),
            "apps": results,
        }

    def _execute_list_apps(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Execute list_apps tool to list all installed applications."""
        filter_term = args.get("filter_term", "")

        results = list_apps(filter_term)

        return {
            "filter_term": filter_term,
            "count": len(results),
            "apps": results,
        }


def parse_tool_calls_from_text(text: str) -> list[Dict[str, Any]]:
    """
    Parse tool calls from LLM response text.

    This is a fallback for models that don't support structured function calling.
    It looks for JSON blocks or special markers in the text.

    Parameters
    ----------
    text:
        The LLM response text to parse.

    Returns
    -------
    List of tool call dictionaries with 'name' and 'arguments' keys.
    """
    tool_calls = []

    # Look for JSON code blocks that might contain tool calls
    lines = text.split("\n")
    in_json_block = False
    json_lines = []

    for line in lines:
        if line.strip() == "```json" or line.strip() == "```":
            if in_json_block:
                # End of block, try to parse
                if json_lines:
                    try:
                        data = json.loads("\n".join(json_lines))
                        if isinstance(data, dict) and "tool" in data:
                            tool_calls.append({
                                "name": data["tool"],
                                "arguments": data.get("arguments", {}),
                            })
                        json_lines = []
                    except json.JSONDecodeError:
                        pass
                in_json_block = False
            else:
                in_json_block = True
                json_lines = []
        elif in_json_block:
            json_lines.append(line)

    return tool_calls


# Global tool executor instance
_executor = ToolExecutor()


def execute_tool(tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a tool using the global executor."""
    return _executor.execute(tool_name, arguments)
