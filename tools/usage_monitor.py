"""
Standalone Usage Monitor for EdgePilot
Monitors system metrics and shows desktop notifications when thresholds are exceeded.
Runs independently from the main EdgePilot application.
"""

import json
import os
import sys
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

import psutil

# Cross-platform desktop notifications
try:
    from plyer import notification
    HAS_PLYER = True
except ImportError:
    HAS_PLYER = False
    print("Warning: plyer not installed. Install with: pip install plyer")


# Paths
SCRIPT_DIR = Path(__file__).parent.parent
SETTINGS_PATH = SCRIPT_DIR / "data" / "settings.json"
MONITOR_PID_FILE = SCRIPT_DIR / "data" / "usage_monitor.pid"
LOGO_PATH = SCRIPT_DIR / "assets" / "logo.png"


class UsageMonitor:
    """Monitors system usage and sends desktop notifications."""

    def __init__(self):
        """Initialize the usage monitor."""
        self.settings = self.load_settings()
        self.last_alert_time = {}  # Track last alert time for each metric to avoid spam
        self.alert_cooldown = 300  # 5 minutes between same alerts

    def load_settings(self) -> Dict[str, Any]:
        """Load settings from settings.json."""
        if not SETTINGS_PATH.exists():
            # Return default settings
            return {
                "usage_alerts_enabled": False,
                "alert_thresholds": {
                    "cpu_percent": 85.0,
                    "memory_percent": 85.0,
                    "disk_percent": 90.0,
                },
                "check_interval_seconds": 30,
            }

        try:
            with open(SETTINGS_PATH, "r") as f:
                settings = json.load(f)
                # Ensure required keys exist
                if "usage_alerts_enabled" not in settings:
                    settings["usage_alerts_enabled"] = False
                if "alert_thresholds" not in settings:
                    settings["alert_thresholds"] = {
                        "cpu_percent": 85.0,
                        "memory_percent": 85.0,
                        "disk_percent": 90.0,
                    }
                if "check_interval_seconds" not in settings:
                    settings["check_interval_seconds"] = 30
                return settings
        except Exception as e:
            print(f"Error loading settings: {e}")
            return {
                "usage_alerts_enabled": False,
                "alert_thresholds": {
                    "cpu_percent": 85.0,
                    "memory_percent": 85.0,
                    "disk_percent": 90.0,
                },
                "check_interval_seconds": 30,
            }

    def is_enabled(self) -> bool:
        """Check if usage alerts are enabled."""
        self.settings = self.load_settings()  # Reload to pick up changes
        return self.settings.get("usage_alerts_enabled", False)

    def check_metrics(self) -> Dict[str, Any]:
        """Check current system metrics."""
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')

        return {
            "cpu_percent": cpu_percent,
            "memory_percent": memory.percent,
            "disk_percent": disk.percent,
            "timestamp": datetime.now().isoformat(),
        }

    def should_alert(self, metric_name: str) -> bool:
        """Check if enough time has passed to send another alert for this metric."""
        last_time = self.last_alert_time.get(metric_name, 0)
        current_time = time.time()

        if current_time - last_time >= self.alert_cooldown:
            self.last_alert_time[metric_name] = current_time
            return True
        return False

    def show_notification(self, title: str, message: str, timeout: int = 10):
        """Show a desktop notification."""
        if not HAS_PLYER:
            # Fallback to console output
            print(f"\n{'='*60}")
            print(f"ALERT: {title}")
            print(f"{message}")
            print(f"{'='*60}\n")
            return

        try:
            # Prepare notification arguments
            notify_kwargs = {
                "title": title,
                "message": message,
                "app_name": "EdgePilot",
                "timeout": timeout,
            }

            # Add icon if logo file exists
            if LOGO_PATH.exists():
                notify_kwargs["app_icon"] = str(LOGO_PATH)

            notification.notify(**notify_kwargs)
        except Exception as e:
            print(f"Error showing notification: {e}")
            # Fallback to console
            print(f"\nALERT: {title} - {message}\n")

    def check_and_alert(self):
        """Check metrics and send alerts if thresholds are exceeded."""
        if not self.is_enabled():
            return  # Alerts disabled

        metrics = self.check_metrics()
        thresholds = self.settings.get("alert_thresholds", {})

        # Check CPU
        cpu_threshold = thresholds.get("cpu_percent", 85.0)
        if metrics["cpu_percent"] >= cpu_threshold:
            if self.should_alert("cpu"):
                self.show_notification(
                    title="EdgePilot: High CPU Usage",
                    message=f"CPU usage is at {metrics['cpu_percent']:.1f}% (threshold: {cpu_threshold}%)\nYour system is under stress.",
                    timeout=30,
                )

        # Check Memory
        memory_threshold = thresholds.get("memory_percent", 85.0)
        if metrics["memory_percent"] >= memory_threshold:
            if self.should_alert("memory"):
                self.show_notification(
                    title="EdgePilot: High Memory Usage",
                    message=f"Memory usage is at {metrics['memory_percent']:.1f}% (threshold: {memory_threshold}%)\nConsider closing some applications.",
                    timeout=30,
                )

        # Check Disk
        disk_threshold = thresholds.get("disk_percent", 90.0)
        if metrics["disk_percent"] >= disk_threshold:
            if self.should_alert("disk"):
                self.show_notification(
                    title="EdgePilot: Low Disk Space",
                    message=f"Disk usage is at {metrics['disk_percent']:.1f}% (threshold: {disk_threshold}%)\nConsider freeing up space.",
                    timeout=30,
                )

    def write_pid(self):
        """Write current process ID to file."""
        MONITOR_PID_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(MONITOR_PID_FILE, "w") as f:
            f.write(str(os.getpid()))

    def remove_pid(self):
        """Remove PID file."""
        if MONITOR_PID_FILE.exists():
            MONITOR_PID_FILE.unlink()

    def run(self):
        """Main monitoring loop."""
        print("EdgePilot Usage Monitor started")
        print(f"PID: {os.getpid()}")
        print(f"Settings file: {SETTINGS_PATH}")
        print(f"Alerts enabled: {self.is_enabled()}")

        self.write_pid()

        try:
            while True:
                self.check_and_alert()

                # Sleep for the configured interval
                interval = self.settings.get("check_interval_seconds", 30)
                time.sleep(interval)

        except KeyboardInterrupt:
            print("\nUsage Monitor stopped by user")
        except Exception as e:
            print(f"Error in monitor loop: {e}")
        finally:
            self.remove_pid()


def is_monitor_running() -> Optional[int]:
    """Check if the monitor is already running."""
    if not MONITOR_PID_FILE.exists():
        return None

    try:
        with open(MONITOR_PID_FILE, "r") as f:
            pid = int(f.read().strip())

        # Check if process with this PID exists
        if psutil.pid_exists(pid):
            # Verify it's actually our monitor process
            try:
                proc = psutil.Process(pid)
                if "usage_monitor" in " ".join(proc.cmdline()):
                    return pid
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        # PID file exists but process doesn't - clean up
        MONITOR_PID_FILE.unlink()
        return None
    except Exception:
        return None


def stop_monitor():
    """Stop the running monitor process."""
    pid = is_monitor_running()
    if pid is None:
        print("Monitor is not running")
        return False

    try:
        proc = psutil.Process(pid)
        proc.terminate()

        # Wait for process to terminate
        try:
            proc.wait(timeout=5)
        except psutil.TimeoutExpired:
            # Force kill if it doesn't terminate
            proc.kill()

        print(f"Monitor (PID {pid}) stopped")

        # Clean up PID file
        if MONITOR_PID_FILE.exists():
            MONITOR_PID_FILE.unlink()

        return True
    except Exception as e:
        print(f"Error stopping monitor: {e}")
        return False


if __name__ == "__main__":
    if len(sys.argv) > 1:
        command = sys.argv[1]

        if command == "stop":
            stop_monitor()
        elif command == "status":
            pid = is_monitor_running()
            if pid:
                print(f"Monitor is running (PID: {pid})")
            else:
                print("Monitor is not running")
        elif command == "start":
            pid = is_monitor_running()
            if pid:
                print(f"Monitor is already running (PID: {pid})")
            else:
                monitor = UsageMonitor()
                monitor.run()
        else:
            print("Usage: python usage_monitor.py [start|stop|status]")
    else:
        # Default: run the monitor
        monitor = UsageMonitor()
        monitor.run()
