"""Windows-specific application scheduler."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import List

from tools.scheduler_components.base import BaseScheduler


class WindowsScheduler(BaseScheduler):
    def _get_windows_start_menu_paths(self) -> List[Path]:
        paths = []
        user_start = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
        if user_start.exists():
            paths.append(user_start)
        all_users_start = Path(os.environ.get("PROGRAMDATA", "C:\\ProgramData")) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
        if all_users_start.exists():
            paths.append(all_users_start)
        return paths

    def list_applications(self, filter_term: str = "") -> List[str]:
        filter_lower = filter_term.lower() if filter_term else ""
        shortcuts = []
        for start_menu_path in self._get_windows_start_menu_paths():
            for _root, _dirs, files in os.walk(start_menu_path):
                for file in files:
                    if file.lower().endswith(".lnk"):
                        app_name = Path(file).stem
                        if not filter_term or filter_lower in app_name.lower():
                            shortcuts.append(app_name)
        return sorted(set(shortcuts))

    def search(self, app_name: str) -> List[str]:
        results: List[str] = []
        for start_menu_path in self._get_windows_start_menu_paths():
            for root, _dirs, files in os.walk(start_menu_path):
                for file in files:
                    if file.lower().endswith(".lnk") and app_name.lower() in file.lower():
                        title = Path(os.path.join(root, file)).stem
                        if title not in results:
                            results.append(title)
        try:
            ps_result = subprocess.run(
                ["powershell", "-Command", "Get-AppxPackage | Select-Object Name, PackageFamilyName"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if ps_result.returncode == 0:
                for line in ps_result.stdout.strip().split("\n")[3:]:
                    parts = line.strip().split(None, 1)
                    if len(parts) == 2 and app_name.lower() in parts[0].lower():
                        results.append(app_name.title())
                        break
        except Exception:
            pass
        return results

    def launch(self, app_name: str) -> bool:
        shortcuts: List[str] = []
        for start_menu_path in self._get_windows_start_menu_paths():
            for root, _dirs, files in os.walk(start_menu_path):
                for file in files:
                    if file.lower().endswith(".lnk") and app_name.lower() in file.lower():
                        shortcuts.append(os.path.join(root, file))

        if shortcuts:
            os.startfile(shortcuts[0])  # type: ignore[attr-defined]
            return True

        try:
            ps_result = subprocess.run(
                ["powershell", "-Command", "Get-AppxPackage | Select-Object Name, PackageFamilyName"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if ps_result.returncode == 0:
                for line in ps_result.stdout.strip().split("\n")[3:]:
                    parts = line.strip().split(None, 1)
                    if len(parts) == 2 and app_name.lower() in parts[0].lower():
                        store_app = f"shell:AppsFolder\\{parts[1]}!App"
                        subprocess.Popen(["explorer.exe", store_app])  # noqa: S603
                        return True
        except Exception:
            pass

        subprocess.Popen(["cmd", "/c", "start", "", app_name], shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # noqa: S603
        return True
