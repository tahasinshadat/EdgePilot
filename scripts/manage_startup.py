#!/usr/bin/env python3
"""
EdgePilot Usage Monitor Startup Manager

This script helps install/uninstall the usage monitor to run automatically on system startup.

Usage:
    python scripts/manage_startup.py install    # Install startup configuration
    python scripts/manage_startup.py uninstall  # Remove startup configuration
    python scripts/manage_startup.py status     # Check installation status
"""

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


def get_root_dir() -> Path:
    """Get the EdgePilot root directory."""
    return Path(__file__).parent.parent


def get_python_path() -> str:
    """Get the current Python interpreter path."""
    return sys.executable


def install() -> bool:
    """Install startup configuration for current OS."""
    system = platform.system()
    print(f"Installing for {system}...")

    if system == "Windows":
        root_dir = get_root_dir()
        vbs_script = root_dir / "scripts" / "start_monitor_windows.vbs"

        if not vbs_script.exists():
            print(f"Error: VBS script not found at {vbs_script}")
            return False

        # Get Windows Startup folder
        startup_folder = Path(os.getenv("APPDATA")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"

        if not startup_folder.exists():
            print(f"Error: Startup folder not found at {startup_folder}")
            return False

        # Copy VBS script to Startup folder
        dest_file = startup_folder / "EdgePilot_Monitor.vbs"

        try:
            shutil.copy2(vbs_script, dest_file)
            print(f"Installed startup script to: {dest_file}")
            print(f"   The usage monitor will start automatically on next login.")
            print(f"   Make sure 'Enable Usage Alerts' is turned ON in Settings.")
            return True
        except Exception as e:
            print(f"Error installing startup script: {e}")
            return False

    elif system == "Darwin":
        root_dir = get_root_dir()
        plist_template = root_dir / "scripts" / "com.edgepilot.monitor.plist.template"

        if not plist_template.exists():
            print(f"Error: Plist template not found at {plist_template}")
            return False

        # Read template
        with open(plist_template, "r") as f:
            plist_content = f.read()

        # Replace placeholders
        python_path = get_python_path()
        script_path = root_dir / "tools" / "usage_monitor.py"
        settings_path = root_dir / "data" / "settings.json"
        log_dir = root_dir / "data"

        plist_content = plist_content.replace("{{PYTHON_PATH}}", str(python_path))
        plist_content = plist_content.replace("{{SCRIPT_PATH}}", str(script_path))
        plist_content = plist_content.replace("{{ROOT_DIR}}", str(root_dir))
        plist_content = plist_content.replace("{{SETTINGS_PATH}}", str(settings_path))
        plist_content = plist_content.replace("{{LOG_DIR}}", str(log_dir))

        # Write to LaunchAgents directory
        launch_agents_dir = Path.home() / "Library" / "LaunchAgents"
        launch_agents_dir.mkdir(parents=True, exist_ok=True)

        plist_file = launch_agents_dir / "com.edgepilot.monitor.plist"

        try:
            with open(plist_file, "w") as f:
                f.write(plist_content)

            # Load the launch agent
            subprocess.run(["launchctl", "load", str(plist_file)], check=True, capture_output=True)

            print(f"Installed launch agent to: {plist_file}")
            print(f"   The usage monitor will start automatically on next login.")
            print(f"   Make sure 'Enable Usage Alerts' is turned ON in Settings.")
            return True
        except subprocess.CalledProcessError as e:
            print(f"Error loading launch agent: {e.stderr.decode()}")
            return False
        except Exception as e:
            print(f"Error installing launch agent: {e}")
            return False

    else:
        print(f"Unsupported operating system: {system}")
        print(f"   Only Windows and macOS are supported.")
        print(f"   For Linux, see scripts/manage_startup.py for manual setup.")
        return False


def uninstall() -> bool:
    """Remove startup configuration for current OS."""
    system = platform.system()
    print(f"Uninstalling for {system}...")

    if system == "Windows":
        startup_folder = Path(os.getenv("APPDATA")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
        dest_file = startup_folder / "EdgePilot_Monitor.vbs"

        if dest_file.exists():
            try:
                dest_file.unlink()
                print(f"Removed startup script from: {dest_file}")
                return True
            except Exception as e:
                print(f"Error removing startup script: {e}")
                return False
        else:
            print(f"Startup script not found at: {dest_file}")
            return True

    elif system == "Darwin":
        plist_file = Path.home() / "Library" / "LaunchAgents" / "com.edgepilot.monitor.plist"

        if plist_file.exists():
            try:
                # Unload the launch agent
                subprocess.run(["launchctl", "unload", str(plist_file)], capture_output=True)

                # Remove the plist file
                plist_file.unlink()

                print(f"Removed launch agent from: {plist_file}")
                return True
            except Exception as e:
                print(f"Error removing launch agent: {e}")
                return False
        else:
            print(f"Launch agent not found at: {plist_file}")
            return True

    else:
        print(f"Unsupported operating system: {system}")
        return False


def status() -> bool:
    """Check startup configuration status for current OS."""
    system = platform.system()
    print(f"Checking status for {system}...")

    if system == "Windows":
        startup_folder = Path(os.getenv("APPDATA")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
        dest_file = startup_folder / "EdgePilot_Monitor.vbs"

        if dest_file.exists():
            print(f"Startup script is installed at: {dest_file}")
            return True
        else:
            print(f"Startup script is NOT installed")
            return False

    elif system == "Darwin":
        plist_file = Path.home() / "Library" / "LaunchAgents" / "com.edgepilot.monitor.plist"

        if plist_file.exists():
            # Check if it's loaded
            result = subprocess.run(
                ["launchctl", "list"],
                capture_output=True,
                text=True
            )

            if "com.edgepilot.monitor" in result.stdout:
                print(f"Launch agent is installed and loaded at: {plist_file}")
                return True
            else:
                print(f"Launch agent file exists but is not loaded: {plist_file}")
                print(f"   Run: launchctl load {plist_file}")
                return False
        else:
            print(f"Launch agent is NOT installed")
            return False

    else:
        print(f"Unsupported operating system: {system}")
        return False


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1].lower()

    if command == "install":
        success = install()
    elif command == "uninstall":
        success = uninstall()
    elif command == "status":
        success = status()
    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
