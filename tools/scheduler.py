"""Unified task scheduler for launching apps, running scripts, and shell commands."""

from __future__ import annotations

import copy
import itertools
import json
import os
import re
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple


ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
TASK_HISTORY_FILE = DATA_DIR / "task_history.json"
MAX_TASK_HISTORY = 500


class TaskExecutionError(RuntimeError):
    """Raised when a task fails to execute."""


@dataclass
class CommandResult:
    """Normalized response returned by scheduler operations."""
    action: str
    command: List[str] | str
    cwd: Optional[str]
    started_at: float
    finished_at: float
    stdout: str = ""
    stderr: str = ""
    exit_code: Optional[int] = None
    pid: Optional[int] = None

    @property
    def ok(self) -> bool:
        return self.exit_code is None or self.exit_code == 0

    def to_dict(self) -> Dict[str, object]:
        payload = asdict(self)
        payload["ok"] = self.ok
        return payload


class _TaskRegistry:
    """Registry for tracking scheduled operations with persistence."""
    def __init__(self) -> None:
        self._records: Dict[str, Dict[str, Any]] = {}
        self._index: Dict[tuple, List[str]] = {}
        self._recent: List[str] = []
        self._recent_by_action: Dict[str, List[str]] = {}
        self._lock = threading.Lock()
        self._counter = itertools.count(1)
        self._load_from_disk()

    def _load_from_disk(self) -> None:
        if not TASK_HISTORY_FILE.exists():
            return
        try:
            with TASK_HISTORY_FILE.open("r", encoding="utf-8") as fh:
                tasks = json.load(fh).get("tasks", [])
                for record in tasks:
                    if task_id := record.get("task_id"):
                        self._records[task_id] = record
                self._rebuild_indexes()
                self._reset_counter()
        except (json.JSONDecodeError, OSError):
            pass

    def _reset_counter(self) -> None:
        max_id = max((int(str(tid).split(":")[-1]) for tid in self._records if ":" in str(tid)), default=0)
        self._counter = itertools.count(max_id + 1)

    def _rebuild_indexes(self) -> None:
        ordered = sorted(self._records.values(), key=lambda r: r.get("created_at", 0))
        self._index = {}
        self._recent = []
        self._recent_by_action = {}
        for record in ordered:
            if task_id := record.get("task_id"):
                key = (record.get("action"), record.get("target"))
                self._index.setdefault(key, []).append(task_id)
                self._recent.append(task_id)
                self._recent_by_action.setdefault(record.get("action"), []).append(task_id)

    def _persist(self) -> None:
        if len(self._records) > MAX_TASK_HISTORY:
            ordered = sorted(self._records.values(), key=lambda r: r.get("created_at", 0))
            keep = ordered[-MAX_TASK_HISTORY:]
            self._records = {rec["task_id"]: rec for rec in keep if rec.get("task_id")}
            self._rebuild_indexes()
            self._reset_counter()
        ordered = sorted(self._records.values(), key=lambda r: r.get("created_at", 0))
        TASK_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = TASK_HISTORY_FILE.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump({"tasks": ordered}, fh, indent=2)
        tmp.replace(TASK_HISTORY_FILE)

    def register(self, action: str, target: str, *, delay_seconds: int = 0, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        now = time.time()
        task_id = f"{action}:{int(now * 1000)}:{next(self._counter)}"
        record = {
            "task_id": task_id, "action": action, "target": target, "status": "scheduled",
            "created_at": now, "scheduled_for": now + delay_seconds if delay_seconds > 0 else now,
            "delay_seconds": delay_seconds, "started_at": None, "finished_at": None,
            "result": None, "error": None, "metadata": metadata.copy() if metadata else {},
        }
        with self._lock:
            self._records[task_id] = record
            key = (action, target)
            self._index.setdefault(key, []).append(task_id)
            self._recent.append(task_id)
            self._recent_by_action.setdefault(action, []).append(task_id)
            self._persist()
        return copy.deepcopy(record)

    def _update_status(self, task_id: str, status: str, **updates) -> Optional[Dict[str, Any]]:
        with self._lock:
            if record := self._records.get(task_id):
                record["status"] = status
                record.update(updates)
                self._persist()
                return copy.deepcopy(record)
            return None

    def mark_running(self, task_id: str) -> Optional[Dict[str, Any]]:
        return self._update_status(task_id, "running", started_at=time.time())

    def mark_completed(self, task_id: str, result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return self._update_status(task_id, "completed", finished_at=time.time(), result=result, error=None)

    def mark_failed(self, task_id: str, error: str) -> Optional[Dict[str, Any]]:
        return self._update_status(task_id, "failed", finished_at=time.time(), error=error)

    def get(self, task_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return copy.deepcopy(self._records.get(task_id))

    def list_latest(self, action: str, target: str, limit: int = 1) -> List[Dict[str, Any]]:
        with self._lock:
            task_ids = self._index.get((action, target), [])
            if not task_ids:
                return []
            selected = task_ids[-limit:] if limit > 0 else task_ids[:]
            return [copy.deepcopy(self._records[tid]) for tid in reversed(selected)]

    def latest_any(self) -> Optional[Dict[str, Any]]:
        with self._lock:
            return copy.deepcopy(self._records[self._recent[-1]]) if self._recent else None

    def latest_for_action(self, action: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            task_ids = self._recent_by_action.get(action, [])
            return copy.deepcopy(self._records[task_ids[-1]]) if task_ids else None

    def list_recent(self, action: Optional[str], limit: int) -> List[Dict[str, Any]]:
        if limit <= 0:
            return []
        with self._lock:
            task_ids = self._recent_by_action.get(action, []) if action else self._recent
            if not task_ids:
                return []
            selected = task_ids[-limit:]
            return [copy.deepcopy(self._records[tid]) for tid in reversed(selected)]

    def find_by_metadata(self, action: Optional[str], key: str, query: str, limit: int) -> List[Dict[str, Any]]:
        normalized = query.strip().lower()
        if not normalized or limit <= 0:
            return []
        with self._lock:
            task_ids = self._recent if not action else self._recent_by_action.get(action, [])
            if not task_ids:
                return []
            matches = []
            for task_id in reversed(task_ids):
                value = self._records[task_id].get("metadata", {}).get(key)
                if isinstance(value, str) and normalized in value.lower():
                    matches.append(copy.deepcopy(self._records[task_id]))
                    if len(matches) >= limit:
                        break
            return matches

    def list_all(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [copy.deepcopy(record) for record in self._records.values()]


_REGISTRY = _TaskRegistry()


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


def _get_mac_apps() -> Dict[str, Path]:
    """Get macOS applications dictionary."""
    mac_aliases = {
        "garageband": "/Applications/GarageBand.app", "garage band": "/Applications/GarageBand.app",
        "music": "/System/Applications/Music.app", "terminal": "/System/Applications/Utilities/Terminal.app",
        "safari": "/Applications/Safari.app", "notes": "/System/Applications/Notes.app",
    }
    search_dirs = [Path("/Applications"), Path("/System/Applications"), Path("/System/Applications/Utilities"), Path.home() / "Applications"]
    apps: Dict[str, Path] = {}
    for alias, target in mac_aliases.items():
        if Path(target).exists():
            apps[alias] = Path(target)
    for directory in search_dirs:
        if directory.exists():
            for bundle in directory.glob("**/*.app"):
                apps.setdefault(bundle.stem.lower(), bundle)
    return apps


def _get_windows_start_menu_paths() -> List[Path]:
    """Get Windows Start Menu paths."""
    paths = []
    user_start = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    if user_start.exists():
        paths.append(user_start)
    all_users_start = Path(os.environ.get("PROGRAMDATA", "C:\\ProgramData")) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    if all_users_start.exists():
        paths.append(all_users_start)
    return paths


# ============================================================================
# Main Functions (4 core functions)
# ============================================================================

def list_applications(filter_term: str = "") -> List[str]:
    """List installed applications, optionally filtered by search term."""
    results: List[str] = []
    filter_lower = filter_term.lower() if filter_term else ""
    
    if sys.platform == "darwin":
        apps = _get_mac_apps()
        results = sorted({path.stem for path in apps.values()})
        if filter_lower:
            results = [name for name in results if filter_lower in name.lower()]
    elif os.name == "nt":
        shortcuts = []
        for start_menu_path in _get_windows_start_menu_paths():
            for _root, _dirs, files in os.walk(start_menu_path):
                for file in files:
                    if file.lower().endswith(".lnk"):
                        app_name = Path(file).stem
                        if not filter_term or filter_lower in app_name.lower():
                            shortcuts.append(app_name)
        results = sorted(set(shortcuts))
    else:
        for base_path in ["/usr/bin", "/usr/local/bin", "/opt"]:
            path = Path(base_path)
            if path.exists():
                for item in path.iterdir():
                    if item.is_file() and os.access(item, os.X_OK):
                        name = item.name
                        if not filter_term or filter_lower in name.lower():
                            results.append(name)
        results = sorted(set(results))
    
    return results


def run_python_script(path: str, args: Optional[List[str]] = None, cwd: Optional[str] = None, delay_seconds: int = 0, chat_id: Optional[str] = None) -> Dict[str, object]:
    """Run a Python script with optional delay and input arguments."""
    delay = int(delay_seconds) if delay_seconds else 0
    if delay < 0:
        raise TaskExecutionError("Delay must be >= 0")
    
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
    record = _REGISTRY.register("run_python", str(script_path), delay_seconds=delay, metadata=metadata)
    
    def _execute() -> CommandResult:
        _REGISTRY.mark_running(record["task_id"])
        try:
            command = [sys.executable, str(script_path)] + (args or [])
            start = time.time()
            completed = subprocess.run(command, cwd=str(Path(cwd).expanduser().resolve()) if cwd else None, capture_output=True, text=True)
            result = CommandResult(action="run_python", command=command, cwd=str(Path(cwd).expanduser().resolve()) if cwd else None, started_at=start, finished_at=time.time(), stdout=completed.stdout, stderr=completed.stderr, exit_code=completed.returncode)
            _REGISTRY.mark_completed(record["task_id"], result.to_dict())
            return result
        except Exception as exc:
            _REGISTRY.mark_failed(record["task_id"], str(exc))
            raise
    
    if delay > 0:
        def _delayed() -> None:
            time.sleep(delay)
            try:
                _execute()
                print(f"✓ Ran Python script '{script_path.name}'")
            except Exception as exc:
                print(f"✗ Python script error: {exc}")
        threading.Thread(target=_delayed, daemon=True).start()
        return {"status": "scheduled", "task_id": record["task_id"], "run_id": record["task_id"], "action": "run_python", "delay_seconds": delay, "scheduled_for": record["scheduled_for"], "path": str(script_path), "inputs_identified": inputs_identified}
    
    result = _execute()
    return {"task_id": record["task_id"], "run_id": record["task_id"], "status": "completed", "path": str(script_path), "inputs_identified": inputs_identified, **result.to_dict()}


def run_shell_applications(command: str, cwd: Optional[str] = None, delay_seconds: int = 0, chat_id: Optional[str] = None) -> Dict[str, object]:
    """Run a shell command with optional delay."""
    delay = int(delay_seconds) if delay_seconds else 0
    if delay < 0:
        raise TaskExecutionError("Delay must be >= 0")
    
    cleaned = command.strip()
    if not cleaned:
        raise TaskExecutionError("Shell command must not be empty.")
    
    metadata = {"cwd": cwd}
    if chat_id:
        metadata["chat_id"] = chat_id
    record = _REGISTRY.register("run_shell", cleaned, delay_seconds=delay, metadata=metadata)
    
    def _execute() -> CommandResult:
        _REGISTRY.mark_running(record["task_id"])
        try:
            start = time.time()
            completed = subprocess.run(cleaned, cwd=str(Path(cwd).expanduser().resolve()) if cwd else None, capture_output=True, text=True, shell=True)
            result = CommandResult(action="run_shell", command=cleaned, cwd=str(Path(cwd).expanduser().resolve()) if cwd else None, started_at=start, finished_at=time.time(), stdout=completed.stdout, stderr=completed.stderr, exit_code=completed.returncode)
            _REGISTRY.mark_completed(record["task_id"], result.to_dict())
            return result
        except Exception as exc:
            _REGISTRY.mark_failed(record["task_id"], str(exc))
            raise
    
    if delay > 0:
        def _delayed() -> None:
            time.sleep(delay)
            try:
                _execute()
                print(f"✓ Ran shell command")
            except Exception as exc:
                print(f"✗ Shell command error: {exc}")
        threading.Thread(target=_delayed, daemon=True).start()
        return {"status": "scheduled", "task_id": record["task_id"], "run_id": record["task_id"], "action": "run_shell", "delay_seconds": delay, "scheduled_for": record["scheduled_for"], "command": cleaned}
    
    result = _execute()
    return {"task_id": record["task_id"], "run_id": record["task_id"], "status": "completed", "command": cleaned, **result.to_dict()}


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
            if sys.platform == "darwin":
                candidate = Path(app_name).expanduser()
                if candidate.suffix.lower() == ".app" and candidate.exists():
                    app_path = candidate
                else:
                    apps = _get_mac_apps()
                    normalized = app_name.strip().lower()
                    app_path = apps.get(normalized) or next((bundle for key, bundle in apps.items() if normalized in key), None)
                    if not app_path:
                        _REGISTRY.mark_failed(record["task_id"], f"Could not find application '{app_name}'")
                        return False
                subprocess.run(["open", str(app_path)], check=True)
                _REGISTRY.mark_completed(record["task_id"], {"path": str(app_path), "status": "ok"})
                return True
            elif os.name == "nt":
                shortcuts = []
                for start_menu_path in _get_windows_start_menu_paths():
                    for root, _dirs, files in os.walk(start_menu_path):
                        for file in files:
                            if file.lower().endswith(".lnk") and app_name.lower() in file.lower():
                                shortcuts.append(os.path.join(root, file))
                
                if shortcuts:
                    os.startfile(shortcuts[0])  # type: ignore[attr-defined]
                    _REGISTRY.mark_completed(record["task_id"], {"path": shortcuts[0], "status": "ok"})
                    return True
                
                try:
                    ps_result = subprocess.run(["powershell", "-Command", "Get-AppxPackage | Select-Object Name, PackageFamilyName"], capture_output=True, text=True, timeout=5)
                    if ps_result.returncode == 0:
                        for line in ps_result.stdout.strip().split("\n")[3:]:
                            parts = line.strip().split(None, 1)
                            if len(parts) == 2 and app_name.lower() in parts[0].lower():
                                store_app = f"shell:AppsFolder\\{parts[1]}!App"
                                subprocess.Popen(["explorer.exe", store_app])  # noqa: S603
                                _REGISTRY.mark_completed(record["task_id"], {"command": store_app, "status": "ok"})
                                return True
                except Exception:
                    pass
                
                subprocess.Popen(["cmd", "/c", "start", "", app_name], shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # noqa: S603
                _REGISTRY.mark_completed(record["task_id"], {"command": app_name, "status": "ok"})
                return True
            else:
                subprocess.Popen([app_name])  # noqa: S603
                _REGISTRY.mark_completed(record["task_id"], {"command": app_name, "status": "ok"})
                return True
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


# ============================================================================
# Backward Compatibility & Utility Functions
# ============================================================================

list_apps = list_applications
launch = launch_application

def run_python(path: str, args: Optional[List[str]] = None, cwd: Optional[str] = None, delay_seconds: object = 0, seconds: object = None, delay: object = None, chat_id: Optional[str] = None) -> Dict[str, object]:
    """Backward compatibility wrapper for run_python_script."""
    return run_python_script(path, args=args, cwd=cwd, delay_seconds=_parse_delay(delay_seconds, seconds, delay), chat_id=chat_id)

def run_shell(command: str, cwd: Optional[str] = None, delay_seconds: object = 0, seconds: object = None, delay: object = None, chat_id: Optional[str] = None) -> Dict[str, object]:
    """Backward compatibility wrapper for run_shell_applications."""
    return run_shell_applications(command, cwd=cwd, delay_seconds=_parse_delay(delay_seconds, seconds, delay), chat_id=chat_id)

def get_task(task_id: str) -> Optional[Dict[str, Any]]:
    return _REGISTRY.get(task_id)

def get_latest_task(action: str, target: str) -> Optional[Dict[str, Any]]:
    records = _REGISTRY.list_latest(action, target, limit=1)
    return records[0] if records else None

def list_tasks(action: str, target: str, limit: int = 5) -> List[Dict[str, Any]]:
    return _REGISTRY.list_latest(action, target, limit=limit)

def list_all_tasks(limit: int = 100, action: Optional[str] = None, status: Optional[str] = None, chat_id: Optional[str] = None) -> List[Dict[str, Any]]:
    records = _REGISTRY.list_all()
    if action:
        records = [rec for rec in records if rec.get("action") == action]
    if status:
        records = [rec for rec in records if str(rec.get("status", "")).lower() == status.lower()]
    if chat_id:
        records = [rec for rec in records if rec.get("metadata", {}).get("chat_id") == chat_id]
    records.sort(key=lambda rec: rec.get("created_at", 0), reverse=True)
    return records[:limit] if limit > 0 else records

def get_latest_task_any(action: Optional[str] = None) -> Optional[Dict[str, Any]]:
    return _REGISTRY.latest_for_action(action) if action else _REGISTRY.latest_any()

def list_recent_tasks(action: Optional[str] = None, limit: int = 5) -> List[Dict[str, Any]]:
    return _REGISTRY.list_recent(action, limit)

def get_latest_task_by_metadata(action: Optional[str], key: str, value: str) -> Optional[Dict[str, Any]]:
    records = _REGISTRY.find_by_metadata(action, key, value, limit=1)
    return records[0] if records else None

def list_tasks_by_metadata(action: Optional[str], key: str, value: str, limit: int = 5) -> List[Dict[str, Any]]:
    return _REGISTRY.find_by_metadata(action, key, value, limit=limit)

def search(app_name: str) -> List[str]:
    """Search for applications by name."""
    results: List[str] = []
    if os.name == "nt":
        for start_menu_path in _get_windows_start_menu_paths():
            for root, _dirs, files in os.walk(start_menu_path):
                for file in files:
                    if file.lower().endswith(".lnk") and app_name.lower() in file.lower():
                        title = Path(os.path.join(root, file)).stem
                        if title not in results:
                            results.append(title)
        try:
            ps_result = subprocess.run(["powershell", "-Command", "Get-AppxPackage | Select-Object Name, PackageFamilyName"], capture_output=True, text=True, timeout=5)
            if ps_result.returncode == 0:
                for line in ps_result.stdout.strip().split("\n")[3:]:
                    parts = line.strip().split(None, 1)
                    if len(parts) == 2 and app_name.lower() in parts[0].lower():
                        results.append(app_name.title())
                        break
        except Exception:
            pass
    if sys.platform == "darwin":
        apps = _get_mac_apps()
        normalized = app_name.strip().lower()
        if normalized in apps:
            results.append(apps[normalized].stem)
        else:
            for key, bundle in apps.items():
                if normalized and normalized in key:
                    results.append(bundle.stem)
                    break
    return results

def _format_task_status(record: Dict[str, object], task_id: str) -> str:
    status = record.get("status", "unknown")
    messages = {
        "not_found": f"The task `{task_id}` was not found. Check the Jobs tab for scheduled work.",
        "scheduled": f"Task `{task_id}` is scheduled" + (f" for {time.strftime('%H:%M:%S', time.localtime(float(record.get('scheduled_for', 0))))}" if record.get("scheduled_for") else "") + ". Track progress in the Jobs tab.",
        "running": f"Task `{task_id}` is currently running. Details are available in the Jobs tab.",
        "failed": f"Task `{task_id}` failed. Open the Jobs tab to view the error.",
        "completed": f"Task `{task_id}` completed. See the Jobs tab for output.",
    }
    return messages.get(status, f"Task `{task_id}` status: {status}. View details in the Jobs tab.")

def _parse_structured_tool_call(text: str) -> Optional[Tuple[str, Dict[str, Any]]]:
    def _coerce_call(candidate: Any) -> Optional[Tuple[str, Dict[str, Any]]]:
        if not isinstance(candidate, dict):
            return None
        name = candidate.get("tool") or candidate.get("name") or candidate.get("action")
        if not isinstance(name, str) or not name.strip():
            return None
        raw_args = candidate.get("arguments") or candidate.get("args")
        if raw_args is None:
            raw_args = {k: v for k, v in candidate.items() if k not in {"tool", "name", "action", "arguments", "args"}}
        return name.strip(), raw_args if isinstance(raw_args, dict) else {}
    
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    
    if isinstance(payload, list):
        for entry in payload:
            if parsed := _coerce_call(entry):
                return parsed
        return None
    
    if not isinstance(payload, dict):
        return None
    
    if isinstance(payload.get("tool_calls"), list):
        for entry in payload["tool_calls"]:
            if parsed := _coerce_call(entry):
                return parsed
    
    return _coerce_call(payload)

def _format_tool_reply(tool_name: str, args: Dict[str, Any], result: object) -> str:
    if tool_name == "get_task_status" and isinstance(result, dict):
        task_id = result.get("task_id") or args.get("task_id") or args.get("run_id") or args.get("identifier") or "task"
        return _format_task_status(result, str(task_id))
    
    if tool_name in {"run_python", "run_shell"} and isinstance(result, dict):
        status = result.get("status")
        delay = int(result.get("delay_seconds") or 0)
        task_id = result.get("task_id") or result.get("run_id")
        label = result.get("path") if tool_name == "run_python" else result.get("command")
        stdout = (result.get("stdout") or "").strip()
        
        if status == "scheduled":
            return f"Scheduled `{label or tool_name}` to run in {delay} seconds." + (f" Task ID `{task_id}`." if task_id else "")
        if stdout:
            trimmed = stdout if len(stdout) <= 800 else stdout[:800] + "..."
            heading = f"Ran `{label or tool_name}`" + (f" (task `{task_id}`)" if task_id else "")
            return f"{heading}.\n```\n{trimmed}\n```"
        return f"Ran `{label or tool_name}`" + (f" (task `{task_id}`)" if task_id else "") + "."
    
    if tool_name == "launch" and isinstance(result, dict):
        message = result.get("message")
        task_id = (result.get("task") or {}).get("task_id")
        if message and task_id:
            return f"{message} Task ID `{task_id}`."
        return message or (f"Launch scheduled. Task ID `{task_id}`." if task_id else "Launch request acknowledged.")
    
    if result is None:
        return f"Tool '{tool_name}' completed with no result."
    
    try:
        return f"Tool '{tool_name}' completed:\n```\n{json.dumps(result, indent=2)}\n```"
    except Exception:
        return f"Tool '{tool_name}' completed."

def handle_scheduler_shortcut(prompt: str, executor: Callable[[str, Dict[str, Any]], Dict[str, Any]], chat_id: Optional[str] = None) -> Optional[Tuple[str, int]]:
    """Dispatch structured scheduler requests when the user provides a direct tool call payload."""
    parsed = _parse_structured_tool_call(prompt.strip())
    if not parsed:
        return None
    
    tool_name, args = parsed
    if not isinstance(args, dict):
        args = {}
    if chat_id and "chat_id" not in args:
        args["chat_id"] = chat_id
    
    response = executor(tool_name, args)
    if not response.get("success"):
        return (f"Tool '{tool_name}' failed: {response.get('error', 'unknown error')}", 1)
    
    reply = _format_tool_reply(tool_name, args, response.get("result"))
    return (reply, 1)

def execute_task(payload: Dict[str, object]) -> Dict[str, object]:
    """Dispatch the requested task and return a normalized result."""
    action = str(payload.get("action") or "").strip().lower()
    if not action:
        raise TaskExecutionError("Task request missing 'action'.")
    
    try:
        chat_id = payload.get("chat_id")
        delay = _parse_delay(payload.get("delay"), payload.get("delay_seconds"), payload.get("seconds"))
        
        if action == "open_application":
            target = payload.get("path") or payload.get("name") or ""
            if not isinstance(target, str) or not target.strip():
                raise TaskExecutionError("Open application action requires a name or path.")
            if launch(target, delay, chat_id=chat_id):
                return {"status": "ok", "message": "launched"}
            raise TaskExecutionError(f"Could not locate application '{target}'.")
        
        if action == "run_python":
            path = payload.get("path")
            if not isinstance(path, str):
                raise TaskExecutionError("'path' must be provided for run_python.")
            args = payload.get("args")
            if args is not None and not isinstance(args, list):
                raise TaskExecutionError("'args' must be a list when provided.")
            cwd = payload.get("cwd")
            if cwd is not None and not isinstance(cwd, str):
                raise TaskExecutionError("'cwd' must be a string when provided.")
            return run_python(path, args=args, cwd=cwd, delay_seconds=delay, chat_id=chat_id)
        
        if action == "run_shell":
            command = payload.get("command")
            if not isinstance(command, str):
                raise TaskExecutionError("'command' must be provided for run_shell.")
            cwd = payload.get("cwd")
            if cwd is not None and not isinstance(cwd, str):
                raise TaskExecutionError("'cwd' must be a string when provided.")
            return run_shell(command, cwd=cwd, delay_seconds=delay, chat_id=chat_id)
        
        raise TaskExecutionError(f"Unsupported action '{action}'.")
    except FileNotFoundError as exc:
        raise TaskExecutionError(str(exc)) from exc
