"""macOS-specific application scheduler."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Dict, List

from tools.scheduler_components.base import BaseScheduler


class MacScheduler(BaseScheduler):
    def _get_mac_apps(self) -> Dict[str, Path]:
        mac_aliases = {
            "garageband": "/Applications/GarageBand.app",
            "garage band": "/Applications/GarageBand.app",
            "music": "/System/Applications/Music.app",
            "terminal": "/System/Applications/Utilities/Terminal.app",
            "safari": "/Applications/Safari.app",
            "notes": "/System/Applications/Notes.app",
        }
        search_dirs = [
            Path("/Applications"),
            Path("/System/Applications"),
            Path("/System/Applications/Utilities"),
            Path.home() / "Applications",
        ]
        apps: Dict[str, Path] = {}
        for alias, target in mac_aliases.items():
            if Path(target).exists():
                apps[alias] = Path(target)
        for directory in search_dirs:
            if directory.exists():
                for bundle in directory.glob("**/*.app"):
                    apps.setdefault(bundle.stem.lower(), bundle)
        return apps

    def list_applications(self, filter_term: str = "") -> List[str]:
        apps = self._get_mac_apps()
        results = sorted({path.stem for path in apps.values()})
        if filter_term:
            flt = filter_term.lower()
            results = [name for name in results if flt in name.lower()]
        return results

    def search(self, app_name: str) -> List[str]:
        apps = self._get_mac_apps()
        normalized = app_name.strip().lower()
        if normalized in apps:
            return [apps[normalized].stem]
        for key, bundle in apps.items():
            if normalized and normalized in key:
                return [bundle.stem]
        return []

    def launch(self, app_name: str) -> bool:
        candidate = Path(app_name).expanduser()
        if candidate.suffix.lower() == ".app" and candidate.exists():
            app_path = candidate
        else:
            apps = self._get_mac_apps()
            normalized = app_name.strip().lower()
            app_path = apps.get(normalized) or next((bundle for key, bundle in apps.items() if normalized in key), None)
            if not app_path:
                return False
        subprocess.run(["open", str(app_path)], check=True)
        return True
