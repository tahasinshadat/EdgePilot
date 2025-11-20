#!/usr/bin/env python3
"""
EdgePilot Installer
Cross-platform installer for EdgePilot AI Copilot Console

Supports: Windows and macOS
"""

import os
import sys
import platform
import subprocess
import shutil
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path
import urllib.request
import zipfile
import tarfile
import json


class EdgePilotInstaller:
    def __init__(self):
        self.system = platform.system()
        self.install_dir = None
        self.repo_url = "https://github.com/tahasinshadat/EdgePilot.git"
        self.repo_zip_url = "https://github.com/tahasinshadat/EdgePilot/archive/refs/heads/main.zip"

        # Default install locations
        if self.system == "Windows":
            self.default_install_dir = Path.home() / "EdgePilot"
        elif self.system == "Darwin":  # macOS
            self.default_install_dir = Path.home() / "Applications" / "EdgePilot"
        else:
            self.default_install_dir = Path.home() / "EdgePilot"

        # API keys
        self.gemini_key = ""
        self.claude_key = ""
        self.create_shortcut = True

        # Create GUI
        self.create_gui()

    def create_gui(self):
        """Create the installer GUI."""
        self.root = tk.Tk()
        self.root.title("EdgePilot Installer")
        self.root.geometry("600x500")
        self.root.resizable(False, False)

        # Header
        header = tk.Label(
            self.root,
            text="EdgePilot AI Copilot Console",
            font=("Arial", 18, "bold"),
            pady=20
        )
        header.pack()

        # Main frame
        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Install location
        location_frame = ttk.LabelFrame(main_frame, text="Install Location", padding="10")
        location_frame.pack(fill=tk.X, pady=10)

        self.install_path_var = tk.StringVar(value=str(self.default_install_dir))
        install_entry = ttk.Entry(location_frame, textvariable=self.install_path_var, width=50)
        install_entry.pack(side=tk.LEFT, padx=(0, 5))

        browse_btn = ttk.Button(location_frame, text="Browse", command=self.browse_install_location)
        browse_btn.pack(side=tk.LEFT)

        # API Keys frame
        api_frame = ttk.LabelFrame(main_frame, text="API Keys Configuration", padding="10")
        api_frame.pack(fill=tk.X, pady=10)

        # Gemini API Key (Required)
        ttk.Label(api_frame, text="Gemini API Key (Required):").pack(anchor=tk.W, pady=(0, 5))
        self.gemini_entry = ttk.Entry(api_frame, width=60, show="*")
        self.gemini_entry.pack(fill=tk.X, pady=(0, 10))

        # Claude API Key (Optional)
        ttk.Label(api_frame, text="Claude API Key (Optional):").pack(anchor=tk.W, pady=(0, 5))
        self.claude_entry = ttk.Entry(api_frame, width=60, show="*")
        self.claude_entry.pack(fill=tk.X)

        # Options frame
        options_frame = ttk.LabelFrame(main_frame, text="Options", padding="10")
        options_frame.pack(fill=tk.X, pady=10)

        self.shortcut_var = tk.BooleanVar(value=True)
        shortcut_check = ttk.Checkbutton(
            options_frame,
            text="Create Desktop Shortcut",
            variable=self.shortcut_var
        )
        shortcut_check.pack(anchor=tk.W)

        # Progress
        self.progress_var = tk.StringVar(value="Ready to install")
        progress_label = ttk.Label(main_frame, textvariable=self.progress_var)
        progress_label.pack(pady=(10, 5))

        self.progress = ttk.Progressbar(main_frame, mode='indeterminate')
        self.progress.pack(fill=tk.X, pady=(0, 10))

        # Install button
        self.install_btn = ttk.Button(
            main_frame,
            text="Install EdgePilot",
            command=self.start_installation,
            style="Accent.TButton"
        )
        self.install_btn.pack(pady=10)

        # Center window
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() // 2) - (self.root.winfo_width() // 2)
        y = (self.root.winfo_screenheight() // 2) - (self.root.winfo_height() // 2)
        self.root.geometry(f"+{x}+{y}")

    def browse_install_location(self):
        """Browse for installation directory."""
        directory = filedialog.askdirectory(
            title="Select Installation Directory",
            initialdir=str(self.default_install_dir.parent)
        )
        if directory:
            self.install_path_var.set(directory)

    def start_installation(self):
        """Start the installation process."""
        # Validate Gemini API key
        self.gemini_key = self.gemini_entry.get().strip()
        if not self.gemini_key:
            messagebox.showerror("Error", "Gemini API Key is required!")
            return

        # Get optional keys
        self.claude_key = self.claude_entry.get().strip()
        self.create_shortcut = self.shortcut_var.get()
        self.install_dir = Path(self.install_path_var.get())

        # Disable install button
        self.install_btn.config(state="disabled")
        self.progress.start()

        # Run installation in thread to keep GUI responsive
        import threading
        thread = threading.Thread(target=self.run_installation)
        thread.daemon = True
        thread.start()

    def update_progress(self, message):
        """Update progress message."""
        self.progress_var.set(message)
        self.root.update()

    def run_installation(self):
        """Run the installation process."""
        try:
            # Step 1: Check for required software
            self.update_progress("Checking for required software...")
            has_git = self.check_git()
            has_node = self.check_node()

            if not has_node:
                raise Exception(
                    "Node.js/npm not found!\n\n"
                    "Please install Node.js 18+ from https://nodejs.org/\n"
                    "and run the installer again."
                )

            # Step 2: Download/Clone repository
            self.update_progress("Downloading EdgePilot...")
            if has_git:
                self.clone_repository()
            else:
                self.download_repository()

            # Step 3: Configure .env
            self.update_progress("Configuring environment...")
            self.configure_env()

            # Step 4: Create settings.json
            self.update_progress("Creating settings file...")
            self.create_settings()

            # Step 5: Install Python dependencies
            self.update_progress("Installing Python dependencies...")
            self.install_python_deps()

            # Step 6: Install Node.js dependencies
            self.update_progress("Installing Node.js dependencies...")
            self.install_node_deps()

            # Step 7: Create desktop shortcut
            if self.create_shortcut:
                self.update_progress("Creating desktop shortcut...")
                self.create_desktop_shortcut()

            # Done!
            self.progress.stop()
            self.update_progress("Installation complete!")

            self.root.after(100, lambda: messagebox.showinfo(
                "Success",
                f"EdgePilot has been installed successfully!\n\n"
                f"Installation location: {self.install_dir}\n\n"
                f"{'A desktop shortcut has been created.' if self.create_shortcut else ''}"
            ))

            self.root.after(500, self.root.quit)

        except Exception as e:
            self.progress.stop()
            self.update_progress(f"Error: {str(e)}")
            self.root.after(100, lambda: messagebox.showerror("Installation Failed", str(e)))
            self.install_btn.config(state="normal")

    def check_git(self) -> bool:
        """Check if git is installed."""
        try:
            subprocess.run(
                ["git", "--version"],
                check=True,
                capture_output=True,
                timeout=5
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def check_node(self) -> bool:
        """Check if Node.js/npm is installed."""
        try:
            subprocess.run(
                ["npm", "--version"],
                check=True,
                capture_output=True,
                timeout=5
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def clone_repository(self):
        """Clone the repository using git."""
        # Remove existing directory if it exists
        if self.install_dir.exists():
            shutil.rmtree(self.install_dir)

        # Create parent directory
        self.install_dir.parent.mkdir(parents=True, exist_ok=True)

        # Clone repository
        subprocess.run(
            ["git", "clone", self.repo_url, str(self.install_dir)],
            check=True,
            capture_output=True
        )

    def download_repository(self):
        """Download repository as zip (fallback when git not available)."""
        # Create install directory
        self.install_dir.parent.mkdir(parents=True, exist_ok=True)

        # Download zip file
        zip_path = self.install_dir.parent / "edgepilot.zip"

        self.update_progress("Downloading EdgePilot (this may take a minute)...")
        urllib.request.urlretrieve(self.repo_zip_url, zip_path)

        # Extract zip
        self.update_progress("Extracting files...")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(self.install_dir.parent)

        # Rename extracted folder
        extracted_folder = self.install_dir.parent / "EdgePilot-main"
        if extracted_folder.exists():
            if self.install_dir.exists():
                shutil.rmtree(self.install_dir)
            extracted_folder.rename(self.install_dir)

        # Clean up zip file
        zip_path.unlink()

    def configure_env(self):
        """Configure .env file with API keys."""
        env_file = self.install_dir / "env" / ".env"
        env_file.parent.mkdir(parents=True, exist_ok=True)

        env_content = f"""GEMINI_API_KEY={self.gemini_key}
OPENAI_API_KEY=INSERT_KEY
ANTHROPIC_API_KEY={self.claude_key if self.claude_key else 'INSERT_KEY'}
DEFAULT_PROVIDER=gemini
PROM_URL=http://localhost:9090
PROM_TIMEOUT_SEC=15

# Default SMTP Configuration for EdgePilot Notifications
# These credentials are used to SEND emails (sender)
# Users must provide their own email address (recipient)
DEFAULT_SMTP_SERVER=smtp.gmail.com
DEFAULT_SMTP_PORT=587
DEFAULT_SMTP_USERNAME=edgepilot.app@gmail.com
DEFAULT_SMTP_PASSWORD="kdrw lbey jhzm wfma"
DEFAULT_SMTP_USE_TLS=true
"""

        with open(env_file, 'w') as f:
            f.write(env_content)

    def create_settings(self):
        """Create default settings.json."""
        settings_file = self.install_dir / "data" / "settings.json"
        settings_file.parent.mkdir(parents=True, exist_ok=True)

        settings = {
            "usage_alerts_enabled": False,
            "alert_thresholds": {
                "cpu_percent": 85.0,
                "memory_percent": 85.0,
                "disk_percent": 90.0
            },
            "check_interval_seconds": 30,
            "email_alerts_enabled": False,
            "email_address": "",
            "smtp_username": "",
            "smtp_password": ""
        }

        with open(settings_file, 'w') as f:
            json.dump(settings, f, indent=2)

    def install_python_deps(self):
        """Install Python dependencies."""
        requirements_file = self.install_dir / "requirements.txt"

        if not requirements_file.exists():
            raise Exception("requirements.txt not found!")

        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", str(requirements_file)],
            check=True,
            capture_output=True,
            cwd=str(self.install_dir)
        )

    def install_node_deps(self):
        """Install Node.js dependencies."""
        ui_dir = self.install_dir / "ui"
        package_json = ui_dir / "package.json"

        if not package_json.exists():
            raise Exception("ui/package.json not found!")

        # npm was already checked at the start, so just install
        subprocess.run(
            ["npm", "install"],
            check=True,
            capture_output=True,
            cwd=str(ui_dir)
        )

    def create_desktop_shortcut(self):
        """Create desktop shortcut."""
        if self.system == "Windows":
            self.create_windows_shortcut()
        elif self.system == "Darwin":
            self.create_macos_app()

    def create_windows_shortcut(self):
        """Create Windows desktop shortcut."""
        desktop = Path.home() / "Desktop"
        shortcut_path = desktop / "EdgePilot.bat"

        # Create batch file that launches EdgePilot
        batch_content = f'''@echo off
cd /d "{self.install_dir}"
"{sys.executable}" main.py
pause
'''

        with open(shortcut_path, 'w') as f:
            f.write(batch_content)

        # Try to create a proper .lnk shortcut if pywin32 is available
        try:
            import win32com.client

            shell = win32com.client.Dispatch("WScript.Shell")
            shortcut = shell.CreateShortCut(str(desktop / "EdgePilot.lnk"))
            shortcut.TargetPath = str(shortcut_path)
            shortcut.WorkingDirectory = str(self.install_dir)
            shortcut.IconLocation = str(self.install_dir / "assets" / "logo.ico")
            shortcut.Description = "EdgePilot AI Copilot Console"
            shortcut.save()

            # Remove batch file since we have .lnk
            shortcut_path.unlink()

        except ImportError:
            # pywin32 not available, batch file is good enough
            pass

    def create_macos_app(self):
        """Create macOS .app bundle."""
        applications_dir = Path.home() / "Applications"
        app_dir = applications_dir / "EdgePilot.app"
        contents_dir = app_dir / "Contents"
        macos_dir = contents_dir / "MacOS"
        resources_dir = contents_dir / "Resources"

        # Create directory structure
        macos_dir.mkdir(parents=True, exist_ok=True)
        resources_dir.mkdir(parents=True, exist_ok=True)

        # Create launcher script
        launcher_script = macos_dir / "EdgePilot"
        launcher_content = f'''#!/bin/bash
cd "{self.install_dir}"
{sys.executable} main.py
'''

        with open(launcher_script, 'w') as f:
            f.write(launcher_content)

        # Make executable
        launcher_script.chmod(0o755)

        # Create Info.plist
        plist_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>EdgePilot</string>
    <key>CFBundleDisplayName</key>
    <string>EdgePilot</string>
    <key>CFBundleIdentifier</key>
    <string>com.edgepilot.app</string>
    <key>CFBundleVersion</key>
    <string>1.0</string>
    <key>CFBundleExecutable</key>
    <string>EdgePilot</string>
    <key>CFBundleIconFile</key>
    <string>logo</string>
    <key>LSMinimumSystemVersion</key>
    <string>10.13</string>
    <key>NSHighResolutionCapable</key>
    <true/>
</dict>
</plist>
'''

        info_plist = contents_dir / "Info.plist"
        with open(info_plist, 'w') as f:
            f.write(plist_content)

        # Copy icon if available
        logo_source = self.install_dir / "assets" / "logo.icns"
        if logo_source.exists():
            shutil.copy2(logo_source, resources_dir / "logo.icns")

    def run(self):
        """Run the installer GUI."""
        self.root.mainloop()


def main():
    """Main entry point."""
    # Check platform
    system = platform.system()
    if system not in ["Windows", "Darwin"]:
        print(f"Unsupported platform: {system}")
        print("EdgePilot installer supports Windows and macOS only.")
        sys.exit(1)

    # Create and run installer
    installer = EdgePilotInstaller()
    installer.run()


if __name__ == "__main__":
    main()
