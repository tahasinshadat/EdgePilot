# edgepilot/scheduler/runner.py
from __future__ import annotations

import os
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class TaskHandle:
    task_id: str
    popen: subprocess.Popen
    log_path: Path


def start_subprocess(task_id: str, command: str, log_dir: Path) -> TaskHandle:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"{task_id}.log"
    # Rotate a small log if exists
    if log_file.exists() and log_file.stat().st_size > 10 * 1024 * 1024:
        log_file.rename(log_dir / f"{task_id}.1.log")

    with open(log_file, "ab") as f:
        try:
            # Prefer list args for safety; fall back to shell if user relies on shell features
            args = shlex.split(command)
            pop = subprocess.Popen(args, stdout=f, stderr=subprocess.STDOUT)
        except Exception:
            # shell=True fallback can help in constrained environments
            pop = subprocess.Popen(command, stdout=f, stderr=subprocess.STDOUT, shell=True, executable="/bin/bash")
    return TaskHandle(task_id=task_id, popen=pop, log_path=log_file)
