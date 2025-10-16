# edgepilot/metrics/power_macos.py
from __future__ import annotations

import platform
import subprocess
from typing import Dict, Any


def read_powermetrics() -> Dict[str, Any]:
    """Parse minimal power data on macOS if powermetrics is accessible; else unavailable."""
    if platform.system().lower() != "darwin":
        return {"available": False}
    try:
        # A quick and safe call: ask pmset for battery %
        out = subprocess.check_output(["pmset", "-g", "batt"], text=True, timeout=2)
        # Format e.g., " - InternalBattery-0 (id=xxxx)    87%; discharging; ..."
        pct = None
        for token in out.replace(";", " ").replace("%", " ").split():
            if token.isdigit():
                n = int(token)
                if 0 <= n <= 100:
                    pct = n
                    break
        return {"available": True, "battery_pct": pct}
    except Exception:
        return {"available": False}
