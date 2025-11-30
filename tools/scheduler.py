"""Unified task scheduler for launching apps, running scripts, and shell commands."""

from __future__ import annotations

import re
import subprocess
import threading
import time
import sys
import platform
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from tools.scheduler_components import (
    CommandResult,
    TaskExecutionError,
    TaskRegistry,
    MacScheduler,
    WindowsScheduler,
    LinuxScheduler,
)


_REGISTRY = TaskRegistry()

# ============================================================================
# Scheduler factory
# ============================================================================

def _get_scheduler() -> "BaseScheduler":
    system = platform.system()
    if system == "Darwin":
        return MacScheduler()
    if system == "Windows":
        return WindowsScheduler()
    return LinuxScheduler()


_SCHEDULER = _get_scheduler()


# ============================================================================
# Helper Functions
# ============================================================================

def _parse_delay(*values: object) -> int:
    """Parse delay from multiple possible inputs."""
    for value in values:
        if value is None:
            continue
        if isinstance(value, (int, float)):
            delay = int(value)
        elif isinstance(value, str):
            match = re.search(r"-?\d+", value)
            delay = int(match.group(0)) if match else (0 if not value.strip() else None)
        else:
            continue
        if delay is not None:
            if delay < 0:
                raise TaskExecutionError("Delay must be >= 0")
            if delay > 0:
                return delay
    return 0


# ============================================================================
# Main Functions (5 core functions)
# ============================================================================

def list_applications(filter_term: str = "") -> List[str]:
    """List installed applications, optionally filtered by search term."""
    return _SCHEDULER.list_applications(filter_term)

def launch_application(app_name: str, delay_seconds: int = 0, chat_id: Optional[str] = None) -> bool:
    """Launch an application with optional delay."""
    delay = int(delay_seconds) if delay_seconds else 0
    if delay < 0:
        raise TaskExecutionError("Delay must be >= 0")
    
    metadata = {"app_name": app_name}
    if chat_id:
        metadata["chat_id"] = chat_id
    record = _REGISTRY.register("open_application", app_name, delay_seconds=delay, metadata=metadata)
    
    def _execute() -> bool:
        _REGISTRY.mark_running(record["task_id"])
        try:
            ok = _SCHEDULER.launch(app_name)
            _REGISTRY.mark_completed(record["task_id"], {"status": "ok"} if ok else {"status": "failed"})
            return ok
        except Exception as exc:
            _REGISTRY.mark_failed(record["task_id"], str(exc))
            return False
    
    if delay > 0:
        def _delayed() -> None:
            time.sleep(delay)
            try:
                if _execute():
                    print(f"✓ Launched {app_name}")
                else:
                    print(f"✗ Could not launch {app_name}")
            except Exception as exc:
                print(f"✗ Launch error: {exc}")
        threading.Thread(target=_delayed, daemon=True).start()
        return True
    
    return _execute()


# Backwards compatibility aliases expected by other modules
list_apps = list_applications
launch = launch_application

def search(app_name: str) -> List[str]:
    """Search for applications by name."""
    return _SCHEDULER.search(app_name)


def run_python_script(path: str, args: Optional[List[str]] = None, cwd: Optional[str] = None, delay_seconds: object = 0, seconds: object = None, delay: object = None, chat_id: Optional[str] = None) -> Dict[str, object]:
    """Run a Python script with optional delay and input arguments."""
    parsed_delay = _parse_delay(delay_seconds, seconds, delay)
    
    script_path = Path(path).expanduser()
    try:
        script_path = script_path.resolve()
    except FileNotFoundError:
        raise TaskExecutionError(f"Path not found: {script_path}")
    
    if script_path.is_dir() or not script_path.exists():
        raise TaskExecutionError(f"Python script path must be a file: {script_path}")
    
    inputs_identified = []
    if args:
        for arg in args:
            if isinstance(arg, str):
                if Path(arg).exists():
                    inputs_identified.append(f"file: {arg}")
                elif re.match(r'^-?\d+(\.\d+)?$', arg):
                    inputs_identified.append(f"number: {arg}")
                elif arg.startswith(('http://', 'https://')):
                    inputs_identified.append(f"url: {arg}")
                else:
                    inputs_identified.append(f"string: {arg}")
    
    metadata = {"args": args or [], "cwd": cwd, "inputs_identified": inputs_identified}
    if chat_id:
        metadata["chat_id"] = chat_id
    record = _REGISTRY.register("run_python_script", str(script_path), delay_seconds=parsed_delay, metadata=metadata)
    
    def _execute() -> CommandResult:
        _REGISTRY.mark_running(record["task_id"])
        try:
            command = [sys.executable, str(script_path)] + (args or [])
            start = time.time()
            completed = subprocess.run(command, cwd=str(Path(cwd).expanduser().resolve()) if cwd else None, capture_output=True, text=True)
            result = CommandResult(action="run_python_script", command=command, cwd=str(Path(cwd).expanduser().resolve()) if cwd else None, started_at=start, finished_at=time.time(), stdout=completed.stdout, stderr=completed.stderr, exit_code=completed.returncode)
            _REGISTRY.mark_completed(record["task_id"], result.to_dict())
            return result
        except Exception as exc:
            _REGISTRY.mark_failed(record["task_id"], str(exc))
            raise
    
    if parsed_delay > 0:
        def _delayed() -> None:
            time.sleep(parsed_delay)
            try:
                _execute()
                print(f"✓ Ran Python script '{script_path.name}'")
            except Exception as exc:
                print(f"✗ Python script error: {exc}")
        threading.Thread(target=_delayed, daemon=True).start()
        return {"status": "scheduled", "task_id": record["task_id"], "run_id": record["task_id"], "action": "run_python_script", "delay_seconds": parsed_delay, "scheduled_for": record["scheduled_for"], "path": str(script_path), "inputs_identified": inputs_identified}
    
    result = _execute()
    return {"task_id": record["task_id"], "run_id": record["task_id"], "status": "completed", "path": str(script_path), "inputs_identified": inputs_identified, **result.to_dict()}


def run_shell_commands(command: str, cwd: Optional[str] = None, delay_seconds: object = 0, seconds: object = None, delay: object = None, chat_id: Optional[str] = None) -> Dict[str, object]:
    """Run a shell command with optional delay."""
    parsed_delay = _parse_delay(delay_seconds, seconds, delay)
    
    cleaned = command.strip()
    if not cleaned:
        raise TaskExecutionError("Shell command must not be empty.")
    
    metadata = {"cwd": cwd}
    if chat_id:
        metadata["chat_id"] = chat_id
    record = _REGISTRY.register("run_shell_commands", cleaned, delay_seconds=parsed_delay, metadata=metadata)
    
    def _execute() -> CommandResult:
        _REGISTRY.mark_running(record["task_id"])
        try:
            start = time.time()
            completed = subprocess.run(cleaned, cwd=str(Path(cwd).expanduser().resolve()) if cwd else None, capture_output=True, text=True, shell=True)
            result = CommandResult(action="run_shell_commands", command=cleaned, cwd=str(Path(cwd).expanduser().resolve()) if cwd else None, started_at=start, finished_at=time.time(), stdout=completed.stdout, stderr=completed.stderr, exit_code=completed.returncode)
            _REGISTRY.mark_completed(record["task_id"], result.to_dict())
            return result
        except Exception as exc:
            _REGISTRY.mark_failed(record["task_id"], str(exc))
            raise
    
    if parsed_delay > 0:
        def _delayed() -> None:
            time.sleep(parsed_delay)
            try:
                _execute()
                print(f"✓ Ran shell command")
            except Exception as exc:
                print(f"✗ Shell command error: {exc}")
        threading.Thread(target=_delayed, daemon=True).start()
        return {"status": "scheduled", "task_id": record["task_id"], "run_id": record["task_id"], "action": "run_shell_commands", "delay_seconds": parsed_delay, "scheduled_for": record["scheduled_for"], "command": cleaned}
    
    result = _execute()
    return {"task_id": record["task_id"], "run_id": record["task_id"], "status": "completed", "command": cleaned, **result.to_dict()}
