"""EdgePilot command-line interface for asking questions and managing tasks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import typer

from core.interface import ask_question, os_profile, schedule_operation, summarize_tasks

cli = typer.Typer(add_completion=False, help="Interact with EdgePilot from your terminal.")


def _load_context(context_file: Optional[Path]) -> Optional[Dict[str, Any]]:
    if not context_file:
        return None
    data = json.loads(context_file.read_text())
    if not isinstance(data, dict):
        raise typer.BadParameter("Context file must contain a JSON object.")
    return data


def _ask(
    query: str,
    provider: Optional[str],
    response_format: str,
    context_file: Optional[Path],
    system_prompt: Optional[str],
    context_window: int,
) -> Dict[str, Any]:
    context = _load_context(context_file)
    return ask_question(
        query,
        provider=provider,
        response_format=response_format,
        context=context,
        system_prompt=system_prompt,
        context_window=context_window,
    )


@cli.command("ask")
def ask_command(
    query: str = typer.Argument(..., help="Plain-language question to ask EdgePilot."),
    provider: Optional[str] = typer.Option(None, "--provider", "-p", help="Optional provider name."),
    response_format: str = typer.Option("text", "--format", "-f", help="Response format: text or json."),
    context_file: Optional[Path] = typer.Option(None, "--context-file", "-c", help="Optional JSON file with additional context."),
    system_prompt: Optional[str] = typer.Option(None, "--system-prompt", help="Override the default system prompt."),
    context_window: int = typer.Option(5, "--context-window", help="Number of prior items to include in context."),
) -> None:
    """Ask EdgePilot a question and print the response."""
    result = _ask(query, provider, response_format, context_file, system_prompt, context_window)
    if response_format.lower() == "json":
        typer.echo(json.dumps(result, indent=2))
    else:
        typer.echo(f"Answer ({result['provider']}):\n{result['answer']}")


def _schedule(
    action: str,
    command: Optional[str],
    script_path: Optional[Path],
    args: Optional[List[str]],
    cwd: Optional[Path],
    delay_seconds: int,
) -> Dict[str, Any]:
    payload = {
        "command": command,
        "script_path": str(script_path) if script_path else None,
        "args": args or [],
        "cwd": str(cwd) if cwd else None,
        "delay_seconds": delay_seconds,
        "application": command,
    }
    return schedule_operation(action, payload)


@cli.command("schedule")
def schedule_command(
    action: str = typer.Option(..., "--action", "-a", help="Action to run: run_shell, run_python, or launch."),
    command: Optional[str] = typer.Option(None, "--command", help="Shell command or application name."),
    script_path: Optional[Path] = typer.Option(None, "--script", "-s", help="Python script to execute."),
    args: Optional[List[str]] = typer.Option(None, "--arg", help="Arguments for the Python script.", show_default=False),
    cwd: Optional[Path] = typer.Option(None, "--cwd", help="Working directory for shell/python actions."),
    delay_seconds: int = typer.Option(0, "--delay", "-d", help="Delay in seconds before running."),
) -> None:
    """Schedule a new task using the built-in scheduler."""
    result = _schedule(action, command, script_path, args, cwd, delay_seconds)
    typer.echo(json.dumps(result, indent=2))


def _status(action: Optional[str], limit: int) -> List[Dict[str, Any]]:
    return summarize_tasks(action, limit)


@cli.command("status")
def status_command(
    action: Optional[str] = typer.Option(None, "--action", "-a", help="Filter by action (run_shell, run_python, launch)."),
    limit: int = typer.Option(5, "--limit", "-l", help="Maximum number of tasks to show."),
) -> None:
    """Show recent scheduled tasks."""
    tasks = _status(action, limit)
    if not tasks:
        typer.echo("No tasks recorded yet.")
        return
    typer.echo(json.dumps(tasks, indent=2))


def _handle_repl_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return True
    if stripped in {"exit", "quit"}:
        return False
    if stripped.startswith("ask "):
        result = _ask(stripped[4:], None, "text", None, None, 5)
        typer.echo(f"Answer ({result['provider']}):\n{result['answer']}")
        return True
    if stripped == "status":
        tasks = _status(None, 5)
        typer.echo(json.dumps(tasks, indent=2) if tasks else "No tasks recorded yet.")
        return True
    if stripped.startswith("schedule"):
        typer.echo("Interactive scheduling wizard. Press Enter to skip optional prompts.")
        action = typer.prompt("Action (run_shell/run_python/launch)", default="run_shell")
        delay = typer.prompt("Delay seconds", default="0")
        command = typer.prompt("Command or application name", default="")
        script = typer.prompt("Python script path (optional)", default="")
        args_raw = typer.prompt("Script arguments separated by space (optional)", default="")
        cwd = typer.prompt("Working directory (optional)", default="")
        result = _schedule(
            action,
            command or None,
            Path(script) if script else None,
            args_raw.split() if args_raw else [],
            Path(cwd) if cwd else None,
            int(delay or 0),
        )
        typer.echo(json.dumps(result, indent=2))
        return True
    if stripped == "help":
        typer.echo("Commands: ask <question>, schedule, status, quit")
        return True
    typer.echo("Unknown command. Type 'help' for options.")
    return True


@cli.command("start")
def start_command() -> None:
    """Start an interactive REPL for EdgePilot."""
    typer.echo(f"EdgePilot CLI ready on {os_profile()}. Type 'help' for commands, 'quit' to exit.")
    try:
        while True:
            line = typer.prompt("edgepilot>")
            if not _handle_repl_line(line):
                break
    except (KeyboardInterrupt, EOFError):
        typer.echo("\nGoodbye!")


@cli.command("activate")
def activate_alias() -> None:
    """Alias for start_command to mirror the request wording."""
    start_command()


if __name__ == "__main__":
    cli()
