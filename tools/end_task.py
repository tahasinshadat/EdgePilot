from __future__ import annotations

from pathlib import Path
from typing import List

import psutil


def end_task(identifier: str, force: bool = False, exact_path: bool = False) -> dict:
    """
    Attempt to terminate or kill processes matching the identifier.

    Parameters
    ----------
    identifier:
        Part of the executable path, command line, or process name to match.
        If exact_path is True, this should be the full path to the executable.
    force:
        When True, processes are killed (SIGKILL). Otherwise terminate is used (SIGTERM).
    exact_path:
        When True, only match processes with the exact executable path.
        When False, match any process where the identifier appears in the path, name, or command line.

    Returns
    -------
    dict
        Summary containing matched process IDs and counts for terminated/killed.
    """
    identifier_low = identifier.lower()
    matched: List[psutil.Process] = []

    # If exact_path is specified, try to resolve it to an absolute path
    if exact_path:
        try:
            exact_path_obj = Path(identifier).resolve()
            identifier_str = str(exact_path_obj).lower()
        except Exception:
            identifier_str = identifier_low
    else:
        identifier_str = identifier_low

    for proc in psutil.process_iter(["pid", "name", "exe", "cmdline"]):
        try:
            if exact_path:
                # For exact path matching, only match the exe field
                proc_exe = proc.info.get("exe")
                if proc_exe:
                    proc_exe_lower = str(proc_exe).lower()
                    if proc_exe_lower == identifier_str or Path(proc_exe).resolve() == Path(identifier).resolve():
                        matched.append(proc)
            else:
                # For partial matching, check all fields
                candidates = [
                    proc.info.get("exe"),
                    proc.info.get("name"),
                ]
                cmdline = proc.info.get("cmdline") or []
                candidates.extend(cmdline)
                candidates = [c for c in candidates if c]
                if any(identifier_low in str(c).lower() for c in candidates):
                    matched.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    terminated = 0
    failed: List[int] = []

    for proc in matched:
        try:
            if force:
                proc.kill()
            else:
                proc.terminate()
            terminated += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            failed.append(proc.pid)

    return {
        "identifier": identifier,
        "force": force,
        "exact_path": exact_path,
        "matched": [proc.pid for proc in matched],
        "terminated": terminated,
        "failed": failed,
    }
