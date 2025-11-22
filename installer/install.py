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

        # Check if EdgePilot is already installed
        self.is_installed = self.check_installation()
        self.mode = "uninstall" if self.is_installed else "install"

        # Create GUI
        self.create_gui()

    def check_installation(self) -> bool:
        """Check if EdgePilot is already installed."""
        # Check if installation directory exists and has key files
        if not self.default_install_dir.exists():
            return False

        # Verify it's a valid EdgePilot installation by checking for key files
        key_files = [
            self.default_install_dir / "main.py",
            self.default_install_dir / "requirements.txt",
            self.default_install_dir / "ui" / "main.js"
        ]

        return all(f.exists() for f in key_files)

    def create_gui(self):
        """Create the installer GUI."""
        self.root = tk.Tk()
        title = "EdgePilot Uninstaller" if self.mode == "uninstall" else "EdgePilot Installer"
        self.root.title(title)
        self.root.geometry("600x650" if self.mode == "install" else "600x350")
        self.root.resizable(False, False)

        # Header
        header_text = "EdgePilot AI Copilot Console"
        if self.mode == "uninstall":
            header_text += "\n(Uninstaller)"

        header = tk.Label(
            self.root,
            text=header_text,
            font=("Arial", 18, "bold"),
            pady=20
        )
        header.pack()

        # Main frame
        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)

        if self.mode == "install":
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
        else:
            # Uninstall mode - show installation info
            info_frame = ttk.LabelFrame(main_frame, text="Installation Found", padding="10")
            info_frame.pack(fill=tk.X, pady=10)

            info_text = f"EdgePilot is currently installed at:\n{self.default_install_dir}\n\n"
            info_text += "The following will be removed:\n"
            info_text += "• Installation directory and all files\n"
            info_text += "• Desktop shortcuts\n"
            info_text += "• Configuration and data files"

            info_label = tk.Label(
                info_frame,
                text=info_text,
                justify=tk.LEFT,
                wraplength=520
            )
            info_label.pack(anchor=tk.W, pady=10)

        # Progress
        initial_text = "Ready to uninstall" if self.mode == "uninstall" else "Ready to install"
        self.progress_var = tk.StringVar(value=initial_text)
        progress_label = ttk.Label(main_frame, textvariable=self.progress_var)
        progress_label.pack(pady=(10, 5))

        self.progress = ttk.Progressbar(main_frame, mode='indeterminate')
        self.progress.pack(fill=tk.X, pady=(0, 10))

        # Install/Uninstall button
        button_text = "Uninstall EdgePilot" if self.mode == "uninstall" else "Install EdgePilot"
        button_command = self.start_uninstallation if self.mode == "uninstall" else self.start_installation

        self.install_btn = ttk.Button(
            main_frame,
            text=button_text,
            command=button_command,
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
        installation_started = False
        try:
            # Step 1: Check for required software
            self.update_progress("Checking for required software...")
            has_node = self.check_node()

            if not has_node:
                raise Exception(
                    "Node.js/npm not found!\n\n"
                    "Please install Node.js 18+ from https://nodejs.org/\n"
                    "and run the installer again."
                )

            # Step 2: Download repository as zip
            # Note: Always use zip download to avoid git authentication issues
            self.update_progress("Downloading EdgePilot...")
            installation_started = True  # Mark that we've started creating files
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
                f"{'A desktop shortcut has been created.' if self.create_shortcut else ''}\n\n"
                f"Run this installer again to uninstall EdgePilot."
            ))

            self.root.after(500, self.root.quit)

        except Exception as e:
            self.progress.stop()
            self.update_progress(f"Error: {str(e)}")

            # Cleanup partial installation
            if installation_started and self.install_dir and self.install_dir.exists():
                self.update_progress("Cleaning up partial installation...")
                try:
                    shutil.rmtree(self.install_dir)
                    self.update_progress("Cleanup complete.")
                except Exception as cleanup_error:
                    print(f"Cleanup failed: {cleanup_error}")

            self.root.after(100, lambda: messagebox.showerror(
                "Installation Failed",
                f"{str(e)}\n\n{'Partial installation has been cleaned up.' if installation_started else ''}"
            ))
            self.install_btn.config(state="normal")

    def start_uninstallation(self):
        """Start the uninstallation process."""
        # Confirm uninstallation
        response = messagebox.askyesno(
            "Confirm Uninstall",
            "Are you sure you want to uninstall EdgePilot?\n\n"
            "This will remove all files, settings, and shortcuts.\n"
            "This action cannot be undone."
        )

        if not response:
            return

        # Disable button
        self.install_btn.config(state="disabled")
        self.progress.start()

        # Run uninstallation in thread
        import threading
        thread = threading.Thread(target=self.run_uninstallation)
        thread.daemon = True
        thread.start()

    def run_uninstallation(self):
        """Run the uninstallation process."""
        try:
            self.install_dir = self.default_install_dir

            # Step 1: Remove desktop shortcuts
            self.update_progress("Removing desktop shortcuts...")
            self.remove_shortcuts()

            # Step 2: Remove installation directory
            self.update_progress("Removing installation files...")
            if self.install_dir.exists():
                shutil.rmtree(self.install_dir)

            # Done!
            self.progress.stop()
            self.update_progress("Uninstallation complete!")

            self.root.after(100, lambda: messagebox.showinfo(
                "Success",
                "EdgePilot has been uninstalled successfully!\n\n"
                "All files, settings, and shortcuts have been removed."
            ))

            self.root.after(500, self.root.quit)

        except Exception as e:
            self.progress.stop()
            self.update_progress(f"Error: {str(e)}")
            self.root.after(100, lambda: messagebox.showerror("Uninstallation Failed", str(e)))
            self.install_btn.config(state="normal")

    def remove_shortcuts(self):
        """Remove desktop shortcuts."""
        if self.system == "Windows":
            desktop = Path.home() / "Desktop"
            # Remove batch file
            batch_file = desktop / "EdgePilot.bat"
            if batch_file.exists():
                batch_file.unlink()
            # Remove .lnk shortcut
            lnk_file = desktop / "EdgePilot.lnk"
            if lnk_file.exists():
                lnk_file.unlink()

        elif self.system == "Darwin":
            # Remove macOS .app bundle
            applications_dir = Path.home() / "Applications"
            app_dir = applications_dir / "EdgePilot.app"
            if app_dir.exists():
                shutil.rmtree(app_dir)

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
            # On Windows, npm is a .cmd file and needs shell=True
            subprocess.run(
                ["npm", "--version"],
                check=True,
                capture_output=True,
                timeout=5,
                shell=(self.system == "Windows")
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
        try:
            subprocess.run(
                ["git", "clone", self.repo_url, str(self.install_dir)],
                check=True,
                capture_output=True,
                text=True
            )
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr if e.stderr else str(e)
            raise Exception(f"Git clone failed: {error_msg}")

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
            cwd=str(ui_dir),
            shell=(self.system == "Windows")
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
