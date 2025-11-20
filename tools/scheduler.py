"""Unified task scheduler for launching apps, running scripts, and shell commands."""

from __future__ import annotations

import copy
import functools
import itertools
import json
import os
import re
import shlex
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple


ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
TASK_HISTORY_FILE = DATA_DIR / "task_history.json"
MAX_TASK_HISTORY = 500


def _ensure_task_storage() -> None:
    TASK_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)


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
        if self.exit_code is None:
            return True
        return self.exit_code == 0

    def to_dict(self) -> Dict[str, object]:
        payload = asdict(self)
        payload["ok"] = self.ok
        return payload


class _TaskRegistry:
    """Registry for tracking scheduled operations with persistence."""

    def __init__(self) -> None:
        self._records: Dict[str, Dict[str, Any]] = {}
        self._index: Dict[Tuple[str, str], List[str]] = {}
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
                data = json.load(fh)
        except (json.JSONDecodeError, OSError):
            return
        tasks = data.get("tasks", [])
        for record in tasks:
            task_id = record.get("task_id")
            if not task_id:
                continue
            self._records[task_id] = record
        self._rebuild_indexes_unlocked()
        self._reset_counter_unlocked()

    def _reset_counter_unlocked(self) -> None:
        max_id = 0
        for task_id in self._records:
            try:
                suffix = int(str(task_id).split(":")[-1])
            except (ValueError, IndexError):
                continue
            max_id = max(max_id, suffix)
        self._counter = itertools.count(max_id + 1)

    def _rebuild_indexes_unlocked(self) -> None:
        ordered = sorted(self._records.values(), key=lambda r: r.get("created_at", 0))
        self._index = {}
        self._recent = []
        self._recent_by_action = {}
        for record in ordered:
            task_id = record.get("task_id")
            if not task_id:
                continue
            key = (record.get("action"), record.get("target"))
            self._index.setdefault(key, []).append(task_id)
            self._recent.append(task_id)
            self._recent_by_action.setdefault(record.get("action"), []).append(task_id)

    def _trim_unlocked(self) -> None:
        if len(self._records) <= MAX_TASK_HISTORY:
            return
        ordered = sorted(self._records.values(), key=lambda r: r.get("created_at", 0))
        keep = ordered[-MAX_TASK_HISTORY:]
        self._records = {rec["task_id"]: rec for rec in keep if rec.get("task_id")}
        self._rebuild_indexes_unlocked()
        self._reset_counter_unlocked()

    def _persist_locked(self) -> None:
        self._trim_unlocked()
        ordered = sorted(self._records.values(), key=lambda r: r.get("created_at", 0))
        _ensure_task_storage()
        tmp = TASK_HISTORY_FILE.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump({"tasks": ordered}, fh, indent=2)
        tmp.replace(TASK_HISTORY_FILE)

    def register(
        self,
        action: str,
        target: str,
        *,
        delay_seconds: int = 0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        now = time.time()
        task_id = f"{action}:{int(now * 1000)}:{next(self._counter)}"
        meta = metadata.copy() if metadata else {}
        record = {
            "task_id": task_id,
            "action": action,
            "target": target,
            "status": "scheduled",
            "created_at": now,
            "scheduled_for": now + delay_seconds if delay_seconds > 0 else now,
            "delay_seconds": delay_seconds,
            "started_at": None,
            "finished_at": None,
            "result": None,
            "error": None,
            "metadata": meta,
        }
        key = (action, target)
        with self._lock:
            self._records[task_id] = record
            self._index.setdefault(key, []).append(task_id)
            self._recent.append(task_id)
            self._recent_by_action.setdefault(action, []).append(task_id)
            self._persist_locked()
        return copy.deepcopy(record)

    def mark_running(self, task_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            record = self._records.get(task_id)
            if not record:
                return None
            record["status"] = "running"
            record["started_at"] = time.time()
            self._persist_locked()
            return copy.deepcopy(record)

    def mark_completed(self, task_id: str, result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        with self._lock:
            record = self._records.get(task_id)
            if not record:
                return None
            record["status"] = "completed"
            record["finished_at"] = time.time()
            record["result"] = result
            record["error"] = None
            self._persist_locked()
            return copy.deepcopy(record)

    def mark_failed(self, task_id: str, error: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            record = self._records.get(task_id)
            if not record:
                return None
            record["status"] = "failed"
            record["finished_at"] = time.time()
            record["error"] = error
            self._persist_locked()
            return copy.deepcopy(record)

    def get(self, task_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            record = self._records.get(task_id)
            if not record:
                return None
            return copy.deepcopy(record)

    def list_latest(self, action: str, target: str, limit: int = 1) -> List[Dict[str, Any]]:
        key = (action, target)
        with self._lock:
            task_ids = self._index.get(key, [])
            if not task_ids:
                return []
            selected = task_ids[-limit:] if limit > 0 else task_ids[:]
            return [copy.deepcopy(self._records[task_id]) for task_id in reversed(selected)]

    def latest_any(self) -> Optional[Dict[str, Any]]:
        with self._lock:
            if not self._recent:
                return None
            return copy.deepcopy(self._records[self._recent[-1]])

    def latest_for_action(self, action: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            task_ids = self._recent_by_action.get(action, [])
            if not task_ids:
                return None
            return copy.deepcopy(self._records[task_ids[-1]])

    def list_recent(self, action: Optional[str], limit: int) -> List[Dict[str, Any]]:
        if limit <= 0:
            return []
        with self._lock:
            if action:
                task_ids = self._recent_by_action.get(action, [])
            else:
                task_ids = self._recent
            if not task_ids:
                return []
            selected = task_ids[-limit:]
            return [copy.deepcopy(self._records[task_id]) for task_id in reversed(selected)]

    def find_by_metadata(self, action: Optional[str], key: str, query: str, limit: int) -> List[Dict[str, Any]]:
        normalized = query.strip().lower()
        if not normalized or limit <= 0:
            return []
        with self._lock:
            task_ids = self._recent if not action else self._recent_by_action.get(action, [])
            if not task_ids:
                return []
            matches: List[Dict[str, Any]] = []
            for task_id in reversed(task_ids):
                record = self._records[task_id]
                value = record.get("metadata", {}).get(key)
                if isinstance(value, str) and normalized in value.lower():
                    matches.append(copy.deepcopy(record))
                    if len(matches) >= limit:
                        break
            return matches

    def list_all(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [copy.deepcopy(record) for record in self._records.values()]


_REGISTRY = _TaskRegistry()


def register_task(
    action: str,
    target: str,
    *,
    delay_seconds: int = 0,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return _REGISTRY.register(action, target, delay_seconds=delay_seconds, metadata=metadata)


def mark_task_running(task_id: str) -> Optional[Dict[str, Any]]:
    return _REGISTRY.mark_running(task_id)


def mark_task_completed(task_id: str, result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    return _REGISTRY.mark_completed(task_id, result)


def mark_task_failed(task_id: str, error: str) -> Optional[Dict[str, Any]]:
    return _REGISTRY.mark_failed(task_id, error)


def get_task(task_id: str) -> Optional[Dict[str, Any]]:
    return _REGISTRY.get(task_id)


def get_latest_task(action: str, target: str) -> Optional[Dict[str, Any]]:
    records = _REGISTRY.list_latest(action, target, limit=1)
    return records[0] if records else None


def list_tasks(action: str, target: str, limit: int = 5) -> List[Dict[str, Any]]:
    return _REGISTRY.list_latest(action, target, limit=limit)


def list_all_tasks(
    limit: int = 100,
    action: Optional[str] = None,
    status: Optional[str] = None,
    chat_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    records = _REGISTRY.list_all()
    if action:
        records = [rec for rec in records if rec.get("action") == action]
    if status:
        status_lower = status.lower()
        records = [rec for rec in records if str(rec.get("status", "")).lower() == status_lower]
    if chat_id:
        records = [rec for rec in records if rec.get("metadata", {}).get("chat_id") == chat_id]
    records.sort(key=lambda rec: rec.get("created_at", 0), reverse=True)
    if limit > 0:
        return records[:limit]
    return records


def get_latest_task_any(action: Optional[str] = None) -> Optional[Dict[str, Any]]:
    if action:
        return _REGISTRY.latest_for_action(action)
    return _REGISTRY.latest_any()


def list_recent_tasks(action: Optional[str] = None, limit: int = 5) -> List[Dict[str, Any]]:
    return _REGISTRY.list_recent(action, limit)


def get_latest_task_by_metadata(action: Optional[str], key: str, value: str) -> Optional[Dict[str, Any]]:
    records = _REGISTRY.find_by_metadata(action, key, value, limit=1)
    return records[0] if records else None


def list_tasks_by_metadata(action: Optional[str], key: str, value: str, limit: int = 5) -> List[Dict[str, Any]]:
    return _REGISTRY.find_by_metadata(action, key, value, limit=limit)


def _normalize_path(path: str | None) -> Optional[Path]:
    if not path:
        return None
    expanded = Path(path).expanduser()
    try:
        return expanded.resolve()
    except FileNotFoundError:
        return expanded


def _ensure_exists(path: Optional[Path]) -> None:
    if path is None:
        raise TaskExecutionError("Path is required for this action.")
    if not path.exists():
        raise TaskExecutionError(f"Path not found: {path}")


def _run_subprocess(
    command: Iterable[str] | str,
    *,
    cwd: Optional[Path] = None,
    capture_output: bool = True,
    shell: bool = False,
) -> CommandResult:
    start = time.time()
    if capture_output:
        completed = subprocess.run(
            command,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            shell=shell,
        )
        return CommandResult(
            action="run",
            command=command if isinstance(command, list) else shlex.split(command) if isinstance(command, str) else list(command),
            cwd=str(cwd) if cwd else None,
            started_at=start,
            finished_at=time.time(),
            stdout=completed.stdout,
            stderr=completed.stderr,
            exit_code=completed.returncode,
        )
    process = subprocess.Popen(
        command,
        cwd=str(cwd) if cwd else None,
        shell=shell,
    )
    return CommandResult(
        action="launch",
        command=command if isinstance(command, list) else shlex.split(command) if isinstance(command, str) else list(command),
        cwd=str(cwd) if cwd else None,
        started_at=start,
        finished_at=time.time(),
        exit_code=0,
        pid=process.pid,
    )


def open_application(path: str) -> CommandResult:
    app_path = _normalize_path(path)
    _ensure_exists(app_path)

    if sys.platform == "darwin":
        command = ["open", str(app_path)]
    elif os.name == "nt":
        command = ["cmd", "/c", "start", "", str(app_path)]
    else:
        command = [str(app_path)]

    result = _run_subprocess(command, capture_output=True)
    result.action = "open_application"
    return result


def run_python_script(path: str, args: Optional[List[str]] = None, cwd: Optional[str] = None) -> CommandResult:
    script_path = _normalize_path(path)
    _ensure_exists(script_path)
    if script_path.is_dir():
        raise TaskExecutionError("Python script path must be a file, not a directory.")

    command = [sys.executable, str(script_path)]
    if args:
        command.extend(args)
    result = _run_subprocess(command, cwd=_normalize_path(cwd))
    result.action = "run_python"
    return result


def run_shell_command(command: str, cwd: Optional[str] = None) -> CommandResult:
    if not command.strip():
        raise TaskExecutionError("Shell command must not be empty.")
    result = _run_subprocess(
        command,
        cwd=_normalize_path(cwd),
        capture_output=True,
        shell=True,
    )
    result.action = "run_shell"
    return result


def _parse_delay_value(value: object) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        match = re.search(r"-?\d+", value)
        if match:
            return int(match.group(0))
        stripped = value.strip()
        if not stripped:
            return 0
    else:
        return None
    raise TaskExecutionError("Delay must be provided as seconds.")


def _normalize_delay(*values: object) -> int:
    for raw in values:
        parsed = _parse_delay_value(raw)
        if parsed is None:
            continue
        if parsed < 0:
            raise TaskExecutionError("Delay must be greater than or equal to zero.")
        if parsed > 0:
            return parsed
    return 0


def run_python(
    path: str,
    args: Optional[List[str]] = None,
    cwd: Optional[str] = None,
    delay_seconds: object = 0,
    seconds: object = None,
    delay: object = None,
    chat_id: Optional[str] = None,
) -> Dict[str, object]:
    if args is not None and not isinstance(args, list):
        raise TaskExecutionError("'args' must be a list when provided.")

    delay_value = _normalize_delay(delay_seconds, seconds, delay)

    raw_path = Path(path).expanduser()
    try:
        script_path = raw_path.resolve()
    except FileNotFoundError:
        raise TaskExecutionError(f"Path not found: {raw_path}")

    if script_path.is_dir():
        raise TaskExecutionError("Python script path must be a file, not a directory.")
    if not script_path.exists():
        raise TaskExecutionError(f"Path not found: {script_path}")

    script_str = str(script_path)
    args_list = list(args) if args else []
    call_args = args_list if args is not None else None
    metadata = {"args": args_list, "cwd": cwd}
    if chat_id:
        metadata["chat_id"] = chat_id
    record = register_task(
        "run_python",
        script_str,
        delay_seconds=delay_value,
        metadata=metadata,
    )

    def _execute() -> Dict[str, object]:
        mark_task_running(record["task_id"])
        try:
            result_obj = run_python_script(script_str, args=call_args, cwd=cwd)
            result = result_obj.to_dict()
            mark_task_completed(record["task_id"], result)
            return result
        except Exception as exc:  # noqa: BLE001
            mark_task_failed(record["task_id"], str(exc))
            raise

    if delay_value > 0:
        def _delayed() -> None:
            time.sleep(delay_value)
            try:
                result_obj = run_python_script(script_str, args=call_args, cwd=cwd)
                mark_task_completed(record["task_id"], result_obj.to_dict())
                print(f"✓ Ran Python script '{script_path.name}'")
            except Exception as exc:  # noqa: BLE001
                mark_task_failed(record["task_id"], str(exc))
                print(f"✗ Python script error: {exc}")

        threading.Thread(target=_delayed, daemon=True).start()
        print(f"Scheduled '{script_path.name}' to run in {delay_value} seconds (task {record['task_id']})...")
        return {
            "status": "scheduled",
            "task_id": record["task_id"],
            "run_id": record["task_id"],
            "action": "run_python",
            "path": script_str,
            "delay_seconds": delay_value,
            "scheduled_for": record["scheduled_for"],
        }

    result = _execute()
    result["task_id"] = record["task_id"]
    result["run_id"] = record["task_id"]
    result["status"] = "completed"
    return result


def run_shell(
    command: str,
    cwd: Optional[str] = None,
    delay_seconds: object = 0,
    seconds: object = None,
    delay: object = None,
    chat_id: Optional[str] = None,
) -> Dict[str, object]:
    if cwd is not None and not isinstance(cwd, str):
        raise TaskExecutionError("'cwd' must be a string when provided.")

    cleaned = command.strip()
    if not cleaned:
        raise TaskExecutionError("Shell command must not be empty.")

    delay_value = _normalize_delay(delay_seconds, seconds, delay)

    metadata = {"cwd": cwd}
    if chat_id:
        metadata["chat_id"] = chat_id
    record = register_task(
        "run_shell",
        cleaned,
        delay_seconds=delay_value,
        metadata=metadata,
    )

    def _execute() -> Dict[str, object]:
        mark_task_running(record["task_id"])
        try:
            result_obj = run_shell_command(cleaned, cwd=cwd)
            result = result_obj.to_dict()
            mark_task_completed(record["task_id"], result)
            return result
        except Exception as exc:  # noqa: BLE001
            mark_task_failed(record["task_id"], str(exc))
            raise

    if delay_value > 0:
        def _delayed() -> None:
            time.sleep(delay_value)
            try:
                result_obj = run_shell_command(cleaned, cwd=cwd)
                mark_task_completed(record["task_id"], result_obj.to_dict())
                print("✓ Ran delayed shell command")
            except Exception as exc:  # noqa: BLE001
                mark_task_failed(record["task_id"], str(exc))
                print(f"✗ Shell command error: {exc}")

        threading.Thread(target=_delayed, daemon=True).start()
        print(f"Scheduled shell command to run in {delay_value} seconds (task {record['task_id']})...")
        return {
            "status": "scheduled",
            "task_id": record["task_id"],
            "run_id": record["task_id"],
            "action": "run_shell",
            "command": cleaned,
            "delay_seconds": delay_value,
            "scheduled_for": record["scheduled_for"],
        }

    result = _execute()
    result["task_id"] = record["task_id"]
    result["run_id"] = record["task_id"]
    result["status"] = "completed"
    return result


# ---------------------------------------------------------------------------
# Windows Start Menu helpers (used when os.name == "nt")
# ---------------------------------------------------------------------------

if os.name == "nt":

    def get_start_menu_paths() -> List[Path]:
        """Get all Windows Start Menu directories."""
        paths = []

        user_start = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
        if user_start.exists():
            paths.append(user_start)

        programdata = os.environ.get("PROGRAMDATA", "C:\\ProgramData")
        all_users_start = Path(programdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
        if all_users_start.exists():
            paths.append(all_users_start)

        return paths


    def get_microsoft_store_apps() -> List[tuple]:
        """
        Get Microsoft Store / UWP apps.
        Returns list of (app_name, app_id) tuples.
        """
        store_apps: List[tuple] = []

        try:
            ps_command = "Get-AppxPackage | Select-Object Name, PackageFamilyName"
            result = subprocess.run(
                ["powershell", "-Command", ps_command],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode == 0:
                lines = result.stdout.strip().split("\n")
                for line in lines[3:]:
                    line = line.strip()
                    if line:
                        parts = line.split(None, 1)
                        if len(parts) == 2:
                            name = parts[0]
                            family_name = parts[1] if len(parts) > 1 else ""
                            store_apps.append((name, family_name))
        except Exception:  # noqa: BLE001
            pass

        return store_apps


    def search_start_menu(app_name: str, verbose: bool = False) -> List[str]:
        app_name_lower = app_name.lower()
        shortcuts: List[str] = []

        start_menu_paths = get_start_menu_paths()

        if verbose:
            print(f"Searching in {len(start_menu_paths)} Start Menu locations...")
            for path in start_menu_paths:
                print(f"  - {path}")

        for start_menu_path in start_menu_paths:
            for root, _dirs, files in os.walk(start_menu_path):
                for file in files:
                    if file.lower().endswith(".lnk") and app_name_lower in file.lower():
                        full_path = os.path.join(root, file)
                        shortcuts.append(full_path)
                        if verbose:
                            print(f"  ✓ Match: {file}")

        return shortcuts


    def search_store_apps(app_name: str, verbose: bool = False) -> Optional[str]:
        app_name_lower = app_name.lower()

        if verbose:
            print("Searching Microsoft Store apps...")

        store_apps = get_microsoft_store_apps()

        for name, package_family in store_apps:
            if app_name_lower in name.lower():
                if verbose:
                    print(f"  ✓ Found Store app: {name}")
                return f"shell:AppsFolder\\{package_family}!App"

        return None


    def list_installed_apps(search_term: str = "") -> List[str]:
        shortcuts: List[str] = []
        search_lower = search_term.lower()

        for start_menu_path in get_start_menu_paths():
            for _root, _dirs, files in os.walk(start_menu_path):
                for file in files:
                    if file.lower().endswith(".lnk"):
                        app_name = Path(file).stem
                        if not search_term or search_lower in app_name.lower():
                            shortcuts.append(app_name)

        return sorted(set(shortcuts))

else:

    def search_start_menu(app_name: str, verbose: bool = False) -> List[str]:
        return []

    def search_store_apps(app_name: str, verbose: bool = False) -> Optional[str]:
        return None

    def list_installed_apps(search_term: str = "") -> List[str]:
        return []


# ---------------------------------------------------------------------------
# macOS application discovery
# ---------------------------------------------------------------------------

if sys.platform == "darwin":
    MAC_APP_ALIASES: Dict[str, str] = {
        "garageband": "/Applications/GarageBand.app",
        "garage band": "/Applications/GarageBand.app",
        "music": "/System/Applications/Music.app",
        "terminal": "/System/Applications/Utilities/Terminal.app",
        "safari": "/Applications/Safari.app",
        "notes": "/System/Applications/Notes.app",
    }

    MAC_SEARCH_DIRECTORIES = [
        Path("/Applications"),
        Path("/System/Applications"),
        Path("/System/Applications/Utilities"),
        Path.home() / "Applications",
    ]

    @functools.lru_cache(maxsize=1)
    def _gather_mac_apps() -> Dict[str, Path]:
        apps: Dict[str, Path] = {}
        for alias, target in MAC_APP_ALIASES.items():
            location = Path(target)
            if location.exists():
                apps[alias] = location
        for directory in MAC_SEARCH_DIRECTORIES:
            if not directory.exists():
                continue
            for bundle in directory.glob("**/*.app"):
                key = bundle.stem.lower()
                apps.setdefault(key, bundle)
        return apps


    def _resolve_mac_application(app_name: str) -> Optional[Path]:
        candidate = Path(app_name).expanduser()
        if candidate.suffix.lower() == ".app" and candidate.exists():
            return candidate

        normalized = app_name.strip().lower()
        aliases = _gather_mac_apps()
        if normalized in aliases:
            return aliases[normalized]

        for key, bundle in aliases.items():
            if normalized and normalized in key:
                return bundle
        return None


def _launch_macos(app_name: str, delay_seconds: int, chat_id: Optional[str]) -> bool:
    resolved = _resolve_mac_application(app_name)
    if not resolved:
        print(f"✗ Could not find an application matching '{app_name}'.")
        return False

    metadata = {"app_name": app_name}
    if chat_id:
        metadata["chat_id"] = chat_id
    record = register_task(
        "open_application",
        str(resolved),
        delay_seconds=delay_seconds,
        metadata=metadata,
    )

    def _launch_now() -> bool:
        mark_task_running(record["task_id"])
        try:
            result = open_application(str(resolved)).to_dict()
            mark_task_completed(record["task_id"], result)
            print(f"✓ Launched {resolved.stem}")
            return True
        except Exception as exc:  # noqa: BLE001
            mark_task_failed(record["task_id"], str(exc))
            print(f"✗ {exc}")
            return False

    if delay_seconds > 0:
        def _delayed() -> None:
            time.sleep(delay_seconds)
            _launch_now()

        threading.Thread(target=_delayed, daemon=True).start()
        print(f"Scheduled {resolved.stem} to launch in {delay_seconds} seconds (task {record['task_id']})...")
        return True

    return _launch_now()


def _launch_windows(app_name: str, delay_seconds: int, chat_id: Optional[str]) -> bool:
    metadata = {"app_name": app_name}
    if chat_id:
        metadata["chat_id"] = chat_id
    record = register_task(
        "open_application",
        app_name,
        delay_seconds=delay_seconds,
        metadata=metadata,
    )

    def _launch_shortcut(path: str) -> bool:
        mark_task_running(record["task_id"])
        try:
            def _do_launch() -> None:
                try:
                    os.startfile(path)  # type: ignore[attr-defined]
                    mark_task_completed(record["task_id"], {"path": path})
                    print(f"✓ Launched {Path(path).stem}")
                except Exception as exc:  # noqa: BLE001
                    mark_task_failed(record["task_id"], str(exc))
                    print(f"✗ Error launching {path}: {exc}")

            if delay_seconds > 0:
                def _delayed() -> None:
                    time.sleep(delay_seconds)
                    _do_launch()

                threading.Thread(target=_delayed, daemon=True).start()
                print(f"Scheduled {Path(path).stem} to launch in {delay_seconds} seconds (task {record['task_id']})...")
                return True

            _do_launch()
            return True
        except Exception as exc:  # noqa: BLE001
            mark_task_failed(record["task_id"], str(exc))
            print(f"✗ Error launching {path}: {exc}")
            return False

    shortcuts = search_start_menu(app_name, verbose=False)
    if shortcuts:
        chosen = shortcuts[0]
        if len(shortcuts) == 1:
            print(f"Found: {Path(chosen).stem}")
        else:
            print(f"Found {len(shortcuts)} matches, using {Path(chosen).stem}")
        return _launch_shortcut(chosen)

    print("Not found in Start Menu, checking Microsoft Store apps...")
    store_app = search_store_apps(app_name, verbose=True)
    if store_app:
        print("Found Microsoft Store app!")

        def _launch_store() -> None:
            mark_task_running(record["task_id"])
            try:
                subprocess.Popen(["explorer.exe", store_app])  # noqa: S603
                mark_task_completed(record["task_id"], {"command": store_app})
                print(f"✓ Launched {app_name}")
            except Exception as exc:  # noqa: BLE001
                mark_task_failed(record["task_id"], str(exc))
                print(f"✗ Error: {exc}")

        if delay_seconds > 0:
            def _delayed() -> None:
                time.sleep(delay_seconds)
                _launch_store()

            threading.Thread(target=_delayed, daemon=True).start()
            print(f"Scheduled to launch in {delay_seconds} seconds (task {record['task_id']})...")
            return True

        _launch_store()
        return True

    print("Trying Windows built-in command as fallback...")

    def _fallback() -> None:
        mark_task_running(record["task_id"])
        try:
            subprocess.Popen(  # noqa: S603
                ["cmd", "/c", "start", "", app_name],
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            mark_task_completed(record["task_id"], {"command": app_name})
            print(f"✓ Launched {app_name}")
        except Exception as exc:  # noqa: BLE001
            mark_task_failed(record["task_id"], str(exc))
            print(f"✗ Error launching {app_name}: {exc}")

    if delay_seconds > 0:
        def _delayed() -> None:
            time.sleep(delay_seconds)
            _fallback()

        threading.Thread(target=_delayed, daemon=True).start()
        print(f"Scheduled {app_name} to launch in {delay_seconds} seconds (task {record['task_id']})...")
        return True

    _fallback()
    return True


def _launch_generic(app_name: str, delay_seconds: int, chat_id: Optional[str]) -> bool:
    metadata = {"app_name": app_name}
    if chat_id:
        metadata["chat_id"] = chat_id
    record = register_task(
        "open_application",
        app_name,
        delay_seconds=delay_seconds,
        metadata=metadata,
    )

    def _do_launch() -> None:
        mark_task_running(record["task_id"])
        try:
            subprocess.Popen([app_name])  # noqa: S603
            mark_task_completed(record["task_id"], {"command": app_name})
            print(f"✓ Launched {app_name}")
        except Exception as exc:  # noqa: BLE001
            mark_task_failed(record["task_id"], str(exc))
            print(f"✗ Error launching {app_name}: {exc}")

    if delay_seconds > 0:
        def _delayed() -> None:
            time.sleep(delay_seconds)
            _do_launch()

        threading.Thread(target=_delayed, daemon=True).start()
        print(f"Scheduled {app_name} to launch in {delay_seconds} seconds (task {record['task_id']})...")
        return True

    _do_launch()
    return True


def launch(app_name: str, delay_seconds: int = 0, chat_id: Optional[str] = None) -> bool:
    if sys.platform == "darwin":
        return _launch_macos(app_name, delay_seconds, chat_id)
    if os.name == "nt":
        return _launch_windows(app_name, delay_seconds, chat_id)
    return _launch_generic(app_name, delay_seconds, chat_id)


def launch_now(app_name: str) -> bool:
    return launch(app_name, 0)


def launch_in(app_name: str, seconds: int) -> bool:
    return launch(app_name, seconds)


def search(app_name: str) -> List[str]:
    results: List[str] = []

    shortcuts = search_start_menu(app_name, verbose=False)
    for shortcut in shortcuts:
        title = Path(shortcut).stem
        if title not in results:
            results.append(title)

    store_app = search_store_apps(app_name, verbose=False)
    if store_app:
        results.append(app_name.title())

    if sys.platform == "darwin":
        resolved = _resolve_mac_application(app_name)
        if resolved:
            results.append(resolved.stem)

    return results


def list_apps(filter_term: str = "") -> List[str]:
    if sys.platform == "darwin":
        apps = sorted({path.stem for path in _gather_mac_apps().values()})
        if filter_term:
            term = filter_term.lower()
            apps = [name for name in apps if term in name.lower()]
        return apps
    return list_installed_apps(filter_term)


def _format_task_status(record: Dict[str, object], task_id: str) -> str:
    status = record.get("status", "unknown")
    if status == "not_found":
        return f"The task `{task_id}` was not found. Check the Jobs tab for scheduled work."
    if status == "scheduled":
        scheduled_for = record.get("scheduled_for")
        if scheduled_for:
            eta = time.strftime("%H:%M:%S", time.localtime(float(scheduled_for)))
            return (
                f"Task `{task_id}` is scheduled for {eta}. "
                "Track progress in the Jobs tab."
            )
        return f"Task `{task_id}` is scheduled. Track updates in the Jobs tab."
    if status == "running":
        return f"Task `{task_id}` is currently running. Details are available in the Jobs tab."
    if status == "failed":
        return f"Task `{task_id}` failed. Open the Jobs tab to view the error."
    if status == "completed":
        return f"Task `{task_id}` completed. See the Jobs tab for output."
    return f"Task `{task_id}` status: {status}. View details in the Jobs tab."


def handle_scheduler_shortcut(
    prompt: str,
    executor: Callable[[str, Dict[str, Any]], Dict[str, Any]],
    chat_id: Optional[str] = None,
) -> Optional[Tuple[str, int]]:
    def _split_args(arg_text: str) -> List[str]:
        try:
            return shlex.split(arg_text)
        except ValueError:
            return arg_text.split()

    def _extract_args(text: str, *, stop_at_colon: bool = False) -> Tuple[str, List[str]]:
        pattern = r"with\s+(?:input|args?)\s+([^:]+)" if stop_at_colon else r"with\s+(?:input|args?)\s+(.+)"
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            return text.strip(), []
        arg_str = match.group(1).strip()
        cleaned = text[: match.start()].strip()
        return cleaned, _split_args(arg_str)

    """
    Parse natural language scheduler commands and dispatch matching tool calls.

    Returns:
        Optional tuple of (assistant reply, tool_calls_used)
    """
    prefix = "i need to schedule a task"
    text = prompt.strip()
    lower = text.lower()
    forced = lower.startswith(prefix)
    body = text[len(prefix):].lstrip(": ").strip() if forced else text

    # Task status updates
    task_match = re.search(r"(run_python|run_shell|open_application):\d+:\d+", body, re.IGNORECASE)
    if task_match and any(keyword in lower for keyword in ("update", "output", "result", task_match.group(1).lower())):
        task_id = task_match.group(0)
        record = executor("get_task_status", {"task_id": task_id})
        if not record.get("success"):
            return (f"Unable to retrieve `{task_id}`: {record.get('error', 'unknown error')}", 1)
        payload = record.get("result") or {}
        status_text = _format_task_status(payload, task_id)
        eta = payload.get("scheduled_for")
        detail_hint = ""
        if not eta and payload.get("status") == "scheduled":
            eta = payload.get("created_at")
        if eta:
            detail_hint = f" (scheduled around {time.strftime('%H:%M:%S', time.localtime(float(eta)))})"
        return (f"{status_text}{detail_hint}", 1)

    # Delayed Python script
    script_delay = re.search(r"run\s+\w*\s*script.*?in\s+(\d+)\s*seconds?:\s*(.+)", body, re.IGNORECASE)
    if script_delay:
        delay = int(script_delay.group(1))
        path_raw = script_delay.group(2).strip().strip("`\"")
        _, leading_args = _extract_args(body, stop_at_colon=True)
        path, trailing_args = _extract_args(path_raw)
        args = leading_args + trailing_args
        payload = {"path": path, "delay_seconds": delay}
        if args:
            payload["args"] = args
        if chat_id:
            payload["chat_id"] = chat_id
        result = executor("run_python", payload)
        if not result.get("success"):
            return (f"Couldn't schedule `{path}`: {result.get('error', 'unknown error')}", 1)
        payload = result.get("result") or {}
        task_id = payload.get("task_id") or payload.get("run_id")
        if task_id:
            return (f"Scheduled `{path}` to run in {delay} seconds. Task ID `{task_id}`. Track it in the Jobs tab.", 1)
        return (f"Scheduled `{path}` to run in {delay} seconds. Track it in the Jobs tab.", 1)

    # Immediate script execution
    script_now = re.search(r"run\s+\w*\s*script.*?:\s*(.+)", body, re.IGNORECASE)
    if script_now:
        path_raw = script_now.group(1).strip().strip("`\"")
        _, leading_args = _extract_args(body, stop_at_colon=True)
        path, trailing_args = _extract_args(path_raw)
        args = leading_args + trailing_args
        payload = {"path": path}
        if args:
            payload["args"] = args
        if chat_id:
            payload["chat_id"] = chat_id
        result = executor("run_python", payload)
        if not result.get("success"):
            return (f"Couldn't run `{path}`: {result.get('error', 'unknown error')}", 1)
        payload = result.get("result") or {}
        stdout = (payload.get("stdout") or "").strip()
        if stdout:
            trimmed = stdout if len(stdout) < 500 else stdout[:500] + "..."
            return (f"Ran `{path}`.\n```\n{trimmed}\n```", 1)
        return (f"Ran `{path}` successfully.", 1)

    # Delayed app launch
    launch_delay = re.search(r"launch\s+(.+?)\s+in\s+(\d+)\s*seconds?", body, re.IGNORECASE)
    if launch_delay:
        app_name = launch_delay.group(1).strip(" `\"'")
        delay = int(launch_delay.group(2))
        payload = {"app_name": app_name, "delay_seconds": delay}
        if chat_id:
            payload["chat_id"] = chat_id
        result = executor("launch", payload)
        if not result.get("success"):
            return (f"Couldn't schedule `{app_name}`: {result.get('error', 'unknown error')}", 1)
        payload = result.get("result") or {}
        task = payload.get("task") or {}
        task_id = task.get("task_id")
        message = payload.get("message") or f"Scheduled `{app_name}` to launch."
        if task_id:
            message += f" Task ID `{task_id}`."
        message += " Track it in the Jobs tab."
        return (message, 1)

    if forced:
        return ("I couldn't parse that scheduler command. Please try again.", 0)
    return None


def execute_task(payload: Dict[str, object]) -> Dict[str, object]:
    """Dispatch the requested task and return a normalized result."""
    action = str(payload.get("action") or "").strip().lower()
    if not action:
        raise TaskExecutionError("Task request missing 'action'.")

    try:
        chat_id = payload.get("chat_id")

        if action == "open_application":
            target = payload.get("path") or payload.get("name") or ""
            if not isinstance(target, str) or not target.strip():
                raise TaskExecutionError("Open application action requires a name or path.")
            delay = _normalize_delay(payload.get("delay"), payload.get("delay_seconds"), payload.get("seconds"))
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
            delay = _normalize_delay(payload.get("delay"), payload.get("delay_seconds"), payload.get("seconds"))
            if delay > 0:
                return run_python(path, args=args, cwd=cwd, delay_seconds=delay, chat_id=chat_id)
            return run_python(path, args=args, cwd=cwd, chat_id=chat_id)

        if action == "run_shell":
            command = payload.get("command")
            if not isinstance(command, str):
                raise TaskExecutionError("'command' must be provided for run_shell.")
            cwd = payload.get("cwd")
            if cwd is not None and not isinstance(cwd, str):
                raise TaskExecutionError("'cwd' must be a string when provided.")
            delay = _normalize_delay(payload.get("delay"), payload.get("delay_seconds"), payload.get("seconds"))
            if delay > 0:
                return run_shell(command, cwd=cwd, delay_seconds=delay, chat_id=chat_id)
            return run_shell(command, cwd=cwd, chat_id=chat_id)

        raise TaskExecutionError(f"Unsupported action '{action}'.")
    except FileNotFoundError as exc:
        raise TaskExecutionError(str(exc)) from exc
