"""Tool executor for MCP function calling."""

from __future__ import annotations

import json
from typing import Any, Dict

from tools import (
    end_task,
    evaluate_capacity,
    gather_metrics,
    launch,
    list_apps,
    list_recent_tasks as list_recent_task_records,
    list_tasks as list_task_records,
    list_tasks_by_metadata as list_tasks_by_metadata_record,
    report_edge_status,
    run_python as launcher_run_python,
    run_shell as launcher_run_shell,
    search,
    suggest_capacity_window,
    get_task as get_task_record,
    get_latest_task as get_latest_task_record,
    get_latest_task_any as get_latest_task_any_record,
)


class ToolExecutor:
    """Execute tool calls from LLM responses."""

    def __init__(self):
        """Initialize the tool executor with available tools."""
        self.tools = {
            "gather_metrics": self._execute_gather_metrics,
            "report_edge_status": self._execute_report_edge_status,
            "evaluate_capacity": self._execute_evaluate_capacity,
            "suggest_capacity_window": self._execute_suggest_capacity_window,
            "launch": self._execute_launch,
            "search": self._execute_search,
            "list_apps": self._execute_list_apps,
            "end_task": self._execute_end_task,
            "run_shell": self._execute_run_shell,
            "run_python": self._execute_run_python,
            "get_task_status": self._execute_get_task_status,
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

    def _execute_report_edge_status(self, args: Dict[str, Any]) -> Dict[str, Any]:
        window = args.get("window", "1h")
        top_k = args.get("top_k", 5)
        return report_edge_status(window=window, top_k=top_k)

    def _execute_evaluate_capacity(self, args: Dict[str, Any]) -> Dict[str, Any]:
        requirements = args.get("requirements") or {}
        if not isinstance(requirements, dict):
            raise ValueError("requirements must be an object")
        duration = args.get("duration", "45m")
        host = args.get("host")
        return evaluate_capacity(requirements, duration=duration, host=host)

    def _execute_suggest_capacity_window(self, args: Dict[str, Any]) -> Dict[str, Any]:
        requirements = args.get("requirements") or {}
        if not isinstance(requirements, dict):
            raise ValueError("requirements must be an object")
        duration = args.get("duration", "45m")
        horizon_hours = int(args.get("horizon_hours", 24) or 24)
        host = args.get("host")
        return suggest_capacity_window(
            requirements,
            duration=duration,
            horizon_hours=horizon_hours,
            host=host,
        )

    def _execute_launch(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Execute launch tool to start an application."""
        app_name = args.get("app_name")
        if not app_name:
            raise ValueError("app_name parameter is required")

        delay_seconds = args.get("delay_seconds", 0)
        chat_id = args.get("chat_id")

        # Use launcher.py's launch function
        success = launch(app_name, delay_seconds, chat_id=chat_id)
        task_record = get_latest_task_any_record("open_application")

        if success:
            if delay_seconds > 0:
                message = f"Scheduled '{app_name}' to launch in {delay_seconds} seconds"
            else:
                message = f"Launched '{app_name}'"

            payload = {
                "success": True,
                "message": message,
                "app_name": app_name,
                "delay_seconds": delay_seconds,
            }
            if task_record:
                payload["task"] = task_record
            return payload
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

    def _execute_run_shell(self, args: Dict[str, Any]) -> Dict[str, Any]:
        command = args.get("command")
        if not isinstance(command, str) or not command.strip():
            raise ValueError("command parameter is required")
        cwd = args.get("cwd")
        chat_id = args.get("chat_id")
        result = launcher_run_shell(
            command,
            cwd=cwd,
            delay_seconds=args.get("delay_seconds"),
            seconds=args.get("seconds"),
            delay=args.get("delay"),
            chat_id=chat_id,
        )
        return result

    def _execute_run_python(self, args: Dict[str, Any]) -> Dict[str, Any]:
        path = args.get("path")
        if not isinstance(path, str) or not path.strip():
            raise ValueError("path parameter is required")
        script_args = args.get("args")
        if script_args is not None and not isinstance(script_args, list):
            raise ValueError("args must be a list when provided")
        cwd = args.get("cwd")
        chat_id = args.get("chat_id")
        result = launcher_run_python(
            path,
            args=script_args,
            cwd=cwd,
            delay_seconds=args.get("delay_seconds"),
            seconds=args.get("seconds"),
            delay=args.get("delay"),
            chat_id=chat_id,
        )
        return result

    def _execute_get_task_status(self, args: Dict[str, Any]) -> Dict[str, Any]:
        task_id = args.get("task_id") or args.get("run_id")
        identifier = args.get("identifier")
        # Allow passing the run/task id via identifier for backwards compatibility
        if not task_id and isinstance(identifier, str):
            normalized_identifier = identifier.strip()
            if ":" in normalized_identifier:
                prefix = normalized_identifier.split(":", 1)[0]
                if prefix in {"run_python", "run_shell", "open_application"}:
                    task_id = normalized_identifier

        if task_id:
            record = get_task_record(task_id)
            if record:
                return record
            return {
                "status": "not_found",
                "task_id": task_id,
            }

        action = args.get("action")
        path = args.get("path")
        command = args.get("command")

        if not action:
            if path:
                action = "run_python"
            elif command:
                action = "run_shell"
            elif identifier:
                action = "open_application"

        if action and action not in {"run_python", "run_shell", "open_application"}:
            raise ValueError("action must be 'run_python', 'run_shell', or 'open_application'")

        limit = int(args.get("limit") or 1)

        if action == "open_application" and identifier:
            meta_records = list_tasks_by_metadata_record(action, "app_name", identifier, limit=limit)
            if limit > 1:
                return {
                    "status": "ok" if meta_records else "not_found",
                    "action": action,
                    "records": meta_records,
                    "limit": limit,
                }
            if meta_records:
                return meta_records[0]

        target = identifier or path or command
        if isinstance(target, str):
            target = target.strip()
            if not target:
                target = None

        if target:
            if limit > 1:
                records = list_task_records(action, target, limit=limit)
                return {
                    "status": "ok" if records else "not_found",
                    "action": action,
                    "target": target,
                    "records": records,
                    "limit": limit,
                }

            record = get_latest_task_record(action, target)
            if record:
                return record
            return {
                "status": "not_found",
                "action": action,
                "target": target,
            }

        if limit > 1:
            records = list_recent_task_records(action, limit=limit)
            return {
                "status": "ok" if records else "not_found",
                "action": action,
                "records": records,
                "limit": limit,
            }

        record = get_latest_task_any_record(action)
        if record:
            return record
        return {
            "status": "not_found",
            "action": action,
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
