"""Linux-specific application scheduler."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import List

from tools.scheduler_components.base import BaseScheduler


class LinuxScheduler(BaseScheduler):
    def _list_paths(self) -> List[str]:
        return ["/usr/bin", "/usr/local/bin", "/opt"]

    def list_applications(self, filter_term: str = "") -> List[str]:
        results: List[str] = []
        filter_lower = filter_term.lower() if filter_term else ""
        for base_path in self._list_paths():
            path = Path(base_path)
            if path.exists():
                for item in path.iterdir():
                    if item.is_file() and os.access(item, os.X_OK):
                        name = item.name
                        if not filter_term or filter_lower in name.lower():
                            results.append(name)
        return sorted(set(results))

    def search(self, app_name: str) -> List[str]:
        return self.list_applications(app_name)

    def launch(self, app_name: str) -> bool:
        try:
            subprocess.Popen([app_name])  # noqa: S603
            return True
        except Exception:
            return False
