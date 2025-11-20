"""
Standalone Usage Monitor for EdgePilot
Monitors system metrics and shows desktop notifications when thresholds are exceeded.
Runs independently from the main EdgePilot application.
"""

import json
import os
import smtplib
import sys
import time
from email.message import EmailMessage
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

# Default settings configuration
DEFAULT_SETTINGS = {
    "usage_alerts_enabled": False,
    "alert_thresholds": {
        "cpu_percent": 85.0,
        "memory_percent": 85.0,
        "disk_percent": 90.0,
    },
    "check_interval_seconds": 30,
}


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
            return DEFAULT_SETTINGS.copy()

        try:
            with open(SETTINGS_PATH, "r") as f:
                settings = json.load(f)
                # Merge with defaults to ensure all required keys exist
                return {**DEFAULT_SETTINGS, **settings}
        except Exception as e:
            print(f"Error loading settings: {e}")
            return DEFAULT_SETTINGS.copy()

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

    def send_email(self, subject: str, body: str) -> bool:
        # Check if email alerts are enabled
        if not self.settings.get("email_alerts_enabled", False):
            return False

        # Get recipient email (required)
        email_address = self.settings.get("email_address", "").strip()
        if not email_address:
            return False

        # Get SMTP settings - use defaults from environment if not configured
        smtp_username = self.settings.get("smtp_username", "").strip()
        smtp_password = self.settings.get("smtp_password", "").strip()

        # If user didn't provide SMTP credentials, use defaults from environment
        if not smtp_username or not smtp_password:
            smtp_username = os.getenv("DEFAULT_SMTP_USERNAME", "").strip()
            smtp_password = os.getenv("DEFAULT_SMTP_PASSWORD", "").strip()

        if not smtp_username or not smtp_password:
            print("Email alert skipped: No SMTP credentials configured")
            return False

        # Get SMTP server settings
        smtp_server = self.settings.get("smtp_server") or os.getenv("DEFAULT_SMTP_SERVER", "smtp.gmail.com")
        smtp_port = self.settings.get("smtp_port") or int(os.getenv("DEFAULT_SMTP_PORT", "587"))
        smtp_use_tls = self.settings.get("smtp_use_tls", os.getenv("DEFAULT_SMTP_USE_TLS", "true").lower() == "true")

        try:
            # Create message
            msg = EmailMessage()
            msg["From"] = smtp_username
            msg["To"] = email_address
            msg["Subject"] = subject
            msg.set_content(body)

            # Send email using appropriate SMTP method based on port
            if smtp_use_tls and smtp_port == 587:
                # Use STARTTLS for port 587
                with smtplib.SMTP(smtp_server, smtp_port, timeout=10) as smtp:
                    smtp.starttls()
                    smtp.login(smtp_username, smtp_password)
                    smtp.send_message(msg)
            else:
                # Use SSL for port 465 or other ports
                with smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=10) as smtp:
                    smtp.login(smtp_username, smtp_password)
                    smtp.send_message(msg)

            print(f"Email alert sent to {email_address}")
            return True

        except Exception as e:
            print(f"Error sending email: {e}")
            return False

    def check_and_alert(self):
        """Check metrics and send alerts if thresholds are exceeded."""
        if not self.is_enabled():
            return  # Alerts disabled

        metrics = self.check_metrics()
        thresholds = self.settings.get("alert_thresholds", {})

        # Alert configuration: (key, metric_key, display_name, default_threshold, advice)
        alert_configs = [
            ("cpu", "cpu_percent", "CPU", 85.0, "Your system is under stress."),
            ("memory", "memory_percent", "Memory", 85.0, "Consider closing some applications."),
            ("disk", "disk_percent", "Disk", 90.0, "Consider freeing up space."),
        ]

        for key, metric_key, display_name, default_threshold, advice in alert_configs:
            threshold = thresholds.get(f"{key}_percent", default_threshold)
            if metrics[metric_key] >= threshold:
                if self.should_alert(key):
                    title = f"EdgePilot: {'High' if key != 'disk' else 'Low'} {display_name} {'Usage' if key != 'disk' else 'Space'}"
                    message = f"{display_name} usage is at {metrics[metric_key]:.1f}% (threshold: {threshold}%)\n{advice}"
                    self.show_notification(title=title, message=message, timeout=30)
                    self.send_email(subject=title, body=message)

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
