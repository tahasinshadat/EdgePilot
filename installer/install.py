#!/usr/bin/env python3
"""
EdgePilot Installer - Simplified version
Cross-platform installer/uninstaller for EdgePilot AI Copilot Console

Run Build:
pyinstaller --onefile --windowed --icon=assets/logo.ico --name=EdgePilot-Installer-Windows installer/install.py
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
import urllib.error
import zipfile
import json
import tempfile
import threading


# === Configuration ===
REPO_ZIP_URL = "https://github.com/tahasinshadat/EdgePilot/archive/refs/heads/main.zip"
DOWNLOAD_TIMEOUT = 300  # 5 minutes

# Default installation directory (Windows only)
DEFAULT_INSTALL_DIR = Path.home() / "EdgePilot"


# === Helper Functions ===

def is_installation_in_progress():
    """Check if installation is currently in progress."""
    lock_file = Path(tempfile.gettempdir()) / "edgepilot_installing.lock"
    if lock_file.exists():
        # Check if lock is stale (older than 30 minutes)
        import time
        if time.time() - lock_file.stat().st_mtime < 1800:
            return True
    return False


def mark_installation_started():
    """Mark that installation has started."""
    lock_file = Path(tempfile.gettempdir()) / "edgepilot_installing.lock"
    lock_file.write_text(str(os.getpid()))


def mark_installation_finished():
    """Mark that installation has finished."""
    lock_file = Path(tempfile.gettempdir()) / "edgepilot_installing.lock"
    try:
        if lock_file.exists():
            lock_file.unlink()
    except Exception:
        pass


def check_if_installed():
    """Check if EdgePilot is already installed."""
    # If installation is in progress, don't report as installed
    if is_installation_in_progress():
        return False

    if not DEFAULT_INSTALL_DIR.exists():
        return False

    # Verify it's a valid installation
    key_files = [
        DEFAULT_INSTALL_DIR / "main.py",
        DEFAULT_INSTALL_DIR / "requirements.txt",
        DEFAULT_INSTALL_DIR / "ui" / "main.js"
    ]
    return all(f.exists() for f in key_files)


def check_single_instance():
    """Simple lock mechanism - returns True if we can proceed."""
    lock_file = Path(tempfile.gettempdir()) / "edgepilot_installer.lock"

    try:
        # Try to create an exclusive lock file
        if lock_file.exists():
            # Check if it's stale (older than 2 minutes instead of 5)
            import time
            if time.time() - lock_file.stat().st_mtime > 120:
                # Stale lock, remove it
                lock_file.unlink()
            else:
                # Check if the process is actually running
                try:
                    pid = int(lock_file.read_text().strip())
                    # On Windows, check if process exists
                    if platform.system() == "Windows":
                        result = subprocess.run(
                            ["tasklist", "/FI", f"PID eq {pid}"],
                            capture_output=True,
                            text=True,
                            timeout=2
                        )
                        # If PID not found in tasklist, lock is stale
                        if f"{pid}" not in result.stdout:
                            lock_file.unlink()
                        else:
                            return False
                    else:
                        # On Unix, check if process exists
                        os.kill(pid, 0)
                        return False
                except (ValueError, ProcessLookupError, subprocess.TimeoutExpired):
                    # Invalid PID or process doesn't exist, remove stale lock
                    lock_file.unlink()

        lock_file.write_text(str(os.getpid()))
        return True
    except Exception:
        return True  # If we can't create lock, allow to proceed


def release_lock():
    """Release the lock file."""
    lock_file = Path(tempfile.gettempdir()) / "edgepilot_installer.lock"
    try:
        if lock_file.exists():
            # Only remove if it's our PID
            try:
                pid = int(lock_file.read_text().strip())
                if pid == os.getpid():
                    lock_file.unlink()
            except (ValueError, FileNotFoundError):
                pass
    except Exception:
        pass


def check_node():
    """Check if Node.js/npm is installed."""
    try:
        subprocess.run(
            ["npm", "--version"],
            check=True,
            capture_output=True,
            timeout=5,
            shell=(platform.system() == "Windows")
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return False


def check_writable(directory):
    """Check if directory is writable."""
    test_dir = Path(directory)
    try:
        test_dir.mkdir(parents=True, exist_ok=True)
        test_file = test_dir / ".write_test"
        test_file.write_text("test")
        test_file.unlink()
        return True
    except (OSError, PermissionError):
        return False


def get_desktop_path():
    """Get the actual desktop path, handling OneDrive integration."""
    # Try OneDrive Desktop first (most common on Windows 10/11)
    onedrive_desktop = Path.home() / "OneDrive" / "Desktop"
    if onedrive_desktop.exists():
        return onedrive_desktop

    # Try regular Desktop
    regular_desktop = Path.home() / "Desktop"
    if regular_desktop.exists():
        return regular_desktop

    # On Windows, try to get from registry
    if platform.system() == "Windows":
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
            )
            desktop_path, _ = winreg.QueryValueEx(key, "Desktop")
            winreg.CloseKey(key)
            # Expand environment variables
            desktop_path = os.path.expandvars(desktop_path)
            return Path(desktop_path)
        except Exception:
            pass

    # Fallback to regular Desktop (will be created if needed)
    return regular_desktop


# === Installer GUI ===

class InstallerGUI:
    """Simple installer GUI and workflow."""

    def __init__(self):
        # Safety check: If installation is in progress, don't create a new GUI
        if is_installation_in_progress():
            print("Installation already in progress - not creating new window")
            return

        self.root = tk.Tk()
        self.root.title("EdgePilot Installer")
        self.root.geometry("600x650")
        self.root.resizable(False, False)

        self.install_dir = DEFAULT_INSTALL_DIR
        self.gemini_key = ""
        self.claude_key = ""
        self.create_shortcut = True
        self.installation_started = False  # Track if we've created files

        self._build_gui()
        self._center_window()

    def _build_gui(self):
        """Build the installer GUI."""
        # Header
        tk.Label(
            self.root,
            text="EdgePilot AI Copilot Console",
            font=("Arial", 18, "bold"),
            pady=20
        ).pack()

        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Install Location
        location_frame = ttk.LabelFrame(main_frame, text="Install Location", padding="10")
        location_frame.pack(fill=tk.X, pady=10)

        self.install_path_var = tk.StringVar(value=str(self.install_dir))
        ttk.Entry(location_frame, textvariable=self.install_path_var, width=50).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(location_frame, text="Browse", command=self._browse_location).pack(side=tk.LEFT)

        # API Keys
        api_frame = ttk.LabelFrame(main_frame, text="API Keys", padding="10")
        api_frame.pack(fill=tk.X, pady=10)

        ttk.Label(api_frame, text="Gemini API Key (Required):").pack(anchor=tk.W, pady=(0, 5))
        self.gemini_entry = ttk.Entry(api_frame, width=60, show="*")
        self.gemini_entry.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(api_frame, text="Claude API Key (Optional):").pack(anchor=tk.W, pady=(0, 5))
        self.claude_entry = ttk.Entry(api_frame, width=60, show="*")
        self.claude_entry.pack(fill=tk.X)

        # Options
        options_frame = ttk.LabelFrame(main_frame, text="Options", padding="10")
        options_frame.pack(fill=tk.X, pady=10)

        self.shortcut_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(options_frame, text="Create Desktop Shortcut", variable=self.shortcut_var).pack(anchor=tk.W)

        # Progress
        self.progress_var = tk.StringVar(value="Ready to install")
        ttk.Label(main_frame, textvariable=self.progress_var).pack(pady=(10, 5))

        self.progress = ttk.Progressbar(main_frame, mode='indeterminate')
        self.progress.pack(fill=tk.X, pady=(0, 10))

        # Install Button
        self.install_btn = ttk.Button(main_frame, text="Install EdgePilot", command=self._start_install)
        self.install_btn.pack(pady=10)

    def _center_window(self):
        """Center the window on screen."""
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() // 2) - (self.root.winfo_width() // 2)
        y = (self.root.winfo_screenheight() // 2) - (self.root.winfo_height() // 2)
        self.root.geometry(f"+{x}+{y}")

    def _browse_location(self):
        """Browse for installation directory."""
        directory = filedialog.askdirectory(title="Select Installation Directory")
        if directory:
            self.install_path_var.set(directory)

    def _start_install(self):
        """Validate inputs and start installation."""
        # Validate Gemini API key
        self.gemini_key = self.gemini_entry.get().strip()
        if not self.gemini_key:
            messagebox.showerror("Error", "Gemini API Key is required!")
            return

        self.claude_key = self.claude_entry.get().strip()
        self.create_shortcut = self.shortcut_var.get()
        self.install_dir = Path(self.install_path_var.get())

        # Check if directory is writable
        if not check_writable(self.install_dir.parent):
            messagebox.showerror("Error", f"Cannot write to {self.install_dir.parent}\n\nPlease choose a different location.")
            return

        # Mark installation as in progress BEFORE starting to prevent other instances
        mark_installation_started()

        # Disable button and start progress
        self.install_btn.config(state="disabled")
        self.progress.start()

        # Run installation in background thread
        thread = threading.Thread(target=self._run_install, daemon=True)
        thread.start()

    def _update_progress(self, message):
        """Update progress message."""
        self.progress_var.set(message)
        self.root.update()

    def _run_install(self):
        """Run the installation process."""
        try:
            # Check Node.js
            self._update_progress("Checking for Node.js...")
            if not check_node():
                raise Exception("Node.js/npm not found!\n\nInstall from https://nodejs.org/ and try again.")

            # Download
            self._update_progress("Downloading EdgePilot from GitHub...")
            self.installation_started = True  # Mark that we're creating files
            self._download_edgepilot()

            # Configure
            self._update_progress("Configuring environment...")
            self._create_env_file()
            self._create_settings_file()

            # Install dependencies
            self._update_progress("Installing Python dependencies (this may take a minute)...")
            self._install_python_deps()

            self._update_progress("Installing Node.js dependencies...")
            self._install_node_deps()

            # Create shortcut
            if self.create_shortcut:
                self._update_progress("Creating desktop shortcut...")
                self._create_shortcut()

            # Success!
            mark_installation_finished()  # Clear the lock
            self.progress.stop()
            self._update_progress("Installation complete!")
            self.root.after(100, self._show_success)

        except Exception as e:
            mark_installation_finished()  # Clear the lock even on error
            self.progress.stop()
            self._update_progress(f"Error: {str(e)}")

            # Cleanup partial installation ONLY if we started creating files
            if self.installation_started and self.install_dir.exists():
                try:
                    self._update_progress("Cleaning up partial installation...")
                    shutil.rmtree(self.install_dir)
                    self._update_progress("Cleanup complete.")
                except Exception as cleanup_error:
                    print(f"Cleanup failed: {cleanup_error}")

            error_msg = str(e)
            if self.installation_started:
                error_msg += "\n\nPartial installation has been cleaned up."

            self.root.after(100, lambda: messagebox.showerror("Installation Failed", error_msg))
            self.install_btn.config(state="normal")

    def _download_edgepilot(self):
        """Download and extract EdgePilot from GitHub."""
        self.install_dir.parent.mkdir(parents=True, exist_ok=True)
        zip_path = self.install_dir.parent / "edgepilot.zip"

        try:
            # Download ZIP with timeout
            req = urllib.request.Request(
                REPO_ZIP_URL,
                headers={'User-Agent': 'EdgePilot-Installer'}
            )

            with urllib.request.urlopen(req, timeout=DOWNLOAD_TIMEOUT) as response:
                total_size = int(response.headers.get('content-length', 0))
                downloaded = 0
                chunk_size = 8192

                with open(zip_path, 'wb') as f:
                    while True:
                        chunk = response.read(chunk_size)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)

                        # Update progress
                        if total_size > 0:
                            percent = (downloaded / total_size) * 100
                            self._update_progress(f"Downloading EdgePilot... {percent:.0f}%")

        except urllib.error.URLError as e:
            raise Exception(f"Download failed: {e.reason}")
        except Exception as e:
            raise Exception(f"Download failed: {str(e)}")

        # Extract
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(self.install_dir.parent)
        except zipfile.BadZipFile:
            raise Exception("Downloaded file is corrupted. Please try again.")
        finally:
            # Always cleanup zip file
            if zip_path.exists():
                zip_path.unlink()

        # Rename folder
        extracted = self.install_dir.parent / "EdgePilot-main"
        if not extracted.exists():
            raise Exception("Extraction failed: EdgePilot-main folder not found")

        if self.install_dir.exists():
            shutil.rmtree(self.install_dir)

        extracted.rename(self.install_dir)

    def _create_env_file(self):
        """Create .env file with API keys."""
        env_file = self.install_dir / "env" / ".env"
        env_file.parent.mkdir(parents=True, exist_ok=True)

        env_content = f"""GEMINI_API_KEY={self.gemini_key}
OPENAI_API_KEY=INSERT_KEY
ANTHROPIC_API_KEY={self.claude_key if self.claude_key else 'INSERT_KEY'}
DEFAULT_PROVIDER=gemini
PROM_URL=http://localhost:9090
PROM_TIMEOUT_SEC=15

DEFAULT_SMTP_SERVER=smtp.gmail.com
DEFAULT_SMTP_PORT=587
DEFAULT_SMTP_USERNAME=edgepilot.app@gmail.com
DEFAULT_SMTP_PASSWORD="kdrw lbey jhzm wfma"
DEFAULT_SMTP_USE_TLS=true
"""
        env_file.write_text(env_content)

    def _create_settings_file(self):
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

        settings_file.write_text(json.dumps(settings, indent=2))

    def _install_python_deps(self):
        """Install Python dependencies."""
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"],
                check=True,
                capture_output=True,
                cwd=str(self.install_dir),
                timeout=300  # 5 minute timeout
            )
        except subprocess.TimeoutExpired:
            raise Exception("Python dependency installation timed out.\n\nPlease check your internet connection and try again.")
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.decode() if e.stderr else str(e)
            raise Exception(f"Python dependency installation failed:\n{error_msg}")

    def _install_node_deps(self):
        """Install Node.js dependencies."""
        try:
            subprocess.run(
                ["npm", "install"],
                check=True,
                capture_output=True,
                cwd=str(self.install_dir / "ui"),
                shell=(platform.system() == "Windows"),
                timeout=300  # 5 minute timeout
            )
        except subprocess.TimeoutExpired:
            raise Exception("Node.js dependency installation timed out.\n\nPlease check your internet connection and try again.")
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.decode() if e.stderr else str(e)
            raise Exception(f"Node.js dependency installation failed:\n{error_msg}")

    def _create_shortcut(self):
        """Create desktop shortcut with custom icon (Windows only)."""
        desktop = get_desktop_path()
        shortcut_path = desktop / "EdgePilot.lnk"

        # Create a VBS launcher in the install directory that runs python without console
        vbs_launcher_path = self.install_dir / "launch_edgepilot.vbs"
        vbs_launcher_content = f'''Set objShell = CreateObject("WScript.Shell")
objShell.CurrentDirectory = "{self.install_dir}"
objShell.Run "python main.py", 0, False
Set objShell = Nothing
'''
        vbs_launcher_path.write_text(vbs_launcher_content)

        # Path to icon (use logo.ico from assets folder)
        icon_path = self.install_dir / "assets" / "logo.ico"

        # If logo.ico doesn't exist, try logo.png
        if not icon_path.exists():
            icon_path = self.install_dir / "assets" / "logo.png"

        # Create a temporary VBS script to create the shortcut
        temp_vbs = Path(tempfile.gettempdir()) / "create_edgepilot_shortcut.vbs"

        vbs_content = f'''Set oWS = WScript.CreateObject("WScript.Shell")
Set oLink = oWS.CreateShortcut("{shortcut_path}")
oLink.TargetPath = "{vbs_launcher_path}"
oLink.WorkingDirectory = "{self.install_dir}"
oLink.Description = "EdgePilot AI Copilot Console"
'''

        # Add icon if it exists
        if icon_path.exists():
            vbs_content += f'oLink.IconLocation = "{icon_path}"\n'

        vbs_content += 'oLink.Save\n'

        # Write and execute the VBS script
        temp_vbs.write_text(vbs_content)

        try:
            subprocess.run(
                ["cscript", "//nologo", str(temp_vbs)],
                check=True,
                capture_output=True,
                timeout=10
            )
        finally:
            # Clean up the temporary VBS script
            if temp_vbs.exists():
                temp_vbs.unlink()

    def _show_success(self):
        """Show success dialog with launch option."""
        dialog = tk.Toplevel(self.root)
        dialog.title("Success")
        dialog.geometry("400x200")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        # Center dialog
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
        y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")

        # Success message
        frame = ttk.Frame(dialog, padding="20")
        frame.pack(fill=tk.BOTH, expand=True)

        # Use a label with different styling instead of color
        success_label = tk.Label(
            frame,
            text="✓ Successfully Installed!",
            font=("Arial", 16, "bold")
        )
        success_label.pack(pady=20)

        # Buttons
        button_frame = ttk.Frame(frame)
        button_frame.pack(pady=10)

        ttk.Button(button_frame, text="Launch EdgePilot Now", command=lambda: self._launch_and_close(dialog)).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Close", command=lambda: self._close(dialog)).pack(side=tk.LEFT, padx=5)

    def _launch_and_close(self, dialog):
        """Launch EdgePilot and close installer."""
        main_py = self.install_dir / "main.py"

        # Verify main.py exists before launching
        if not main_py.exists():
            messagebox.showerror("Launch Failed", f"main.py not found at:\n{main_py}")
            return

        try:
            # Use the VBS launcher to run python without console window
            vbs_launcher = self.install_dir / "launch_edgepilot.vbs"

            # Launch EdgePilot using VBS (no console window)
            subprocess.Popen(
                ["wscript", str(vbs_launcher)],
                cwd=str(self.install_dir)
            )

            # Close installer immediately to prevent re-opening
            self.root.quit()
            if dialog:
                dialog.destroy()
        except Exception as e:
            messagebox.showerror("Launch Failed", f"Could not launch EdgePilot:\n{str(e)}")

    def _close(self, dialog=None):
        """Close the installer."""
        if dialog:
            dialog.destroy()
        self.root.quit()

    def run(self):
        """Run the installer."""
        self.root.mainloop()


# === Uninstaller GUI ===

class UninstallerGUI:
    """Simple uninstaller GUI and workflow."""

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("EdgePilot Uninstaller")
        self.root.geometry("600x500")  # Increased height to show all content
        self.root.resizable(False, False)

        self.install_dir = DEFAULT_INSTALL_DIR

        self._build_gui()
        self._center_window()

    def _build_gui(self):
        """Build the uninstaller GUI."""
        # Header
        tk.Label(
            self.root,
            text="EdgePilot AI Copilot Console\n(Uninstaller)",
            font=("Arial", 18, "bold"),
            pady=20
        ).pack()

        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Installation Path - Make it prominent
        path_frame = ttk.LabelFrame(main_frame, text="Installation Location", padding="15")
        path_frame.pack(fill=tk.X, pady=(10, 20))

        tk.Label(
            path_frame,
            text="EdgePilot is currently installed at:",
            font=("Arial", 10),
            justify=tk.LEFT
        ).pack(anchor=tk.W, pady=(0, 5))

        # Path in larger, bold font
        tk.Label(
            path_frame,
            text=str(self.install_dir),
            font=("Arial", 11, "bold"),
            justify=tk.LEFT,
            wraplength=540
        ).pack(anchor=tk.W, pady=(0, 10))

        # What will be removed
        removal_text = "The following will be removed:\n"
        removal_text += "  • Installation directory and all files\n"
        removal_text += "  • Desktop shortcuts\n"
        removal_text += "  • Configuration and data files"

        tk.Label(
            path_frame,
            text=removal_text,
            justify=tk.LEFT,
            font=("Arial", 9)
        ).pack(anchor=tk.W)

        # Progress
        self.progress_var = tk.StringVar(value="Ready to uninstall")
        ttk.Label(main_frame, textvariable=self.progress_var, font=("Arial", 9)).pack(pady=(10, 5))

        self.progress = ttk.Progressbar(main_frame, mode='indeterminate')
        self.progress.pack(fill=tk.X, pady=(0, 20))

        # Buttons - Make them more prominent
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(pady=10)

        # Uninstall Button - larger and more prominent
        self.uninstall_btn = ttk.Button(
            button_frame,
            text="Uninstall EdgePilot",
            command=self._start_uninstall,
            width=25
        )
        self.uninstall_btn.pack(side=tk.LEFT, padx=5)

        # Cancel Button
        ttk.Button(
            button_frame,
            text="Cancel",
            command=self.root.quit,
            width=15
        ).pack(side=tk.LEFT, padx=5)

    def _center_window(self):
        """Center the window on screen."""
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() // 2) - (self.root.winfo_width() // 2)
        y = (self.root.winfo_screenheight() // 2) - (self.root.winfo_height() // 2)
        self.root.geometry(f"+{x}+{y}")

    def _start_uninstall(self):
        """Confirm and start uninstallation."""
        response = messagebox.askyesno(
            "Confirm Uninstall",
            "Are you sure you want to uninstall EdgePilot?\n\n"
            "This will remove all files, settings, and shortcuts.\n"
            "This action cannot be undone."
        )

        if not response:
            return

        # Disable button and start progress
        self.uninstall_btn.config(state="disabled")
        self.progress.start()

        # Run uninstallation in background thread
        thread = threading.Thread(target=self._run_uninstall, daemon=True)
        thread.start()

    def _update_progress(self, message):
        """Update progress message."""
        self.progress_var.set(message)
        self.root.update()

    def _run_uninstall(self):
        """Run the uninstallation process."""
        try:
            # Remove shortcuts
            self._update_progress("Removing desktop shortcuts...")
            self._remove_shortcuts()

            # Remove installation
            self._update_progress("Removing installation files...")
            if self.install_dir.exists():
                shutil.rmtree(self.install_dir)

            # Success!
            self.progress.stop()
            self._update_progress("Uninstallation complete!")

            self.root.after(100, lambda: messagebox.showinfo(
                "Success",
                "EdgePilot has been uninstalled successfully!\n\n"
                "All files, settings, and shortcuts have been removed."
            ))

            self.root.after(500, self.root.quit)

        except Exception as e:
            self.progress.stop()
            self._update_progress(f"Error: {str(e)}")
            self.root.after(100, lambda: messagebox.showerror("Uninstallation Failed", str(e)))
            self.uninstall_btn.config(state="normal")

    def _remove_shortcuts(self):
        """Remove desktop shortcuts (Windows only)."""
        desktop = get_desktop_path()

        # Remove .lnk shortcut
        lnk_file = desktop / "EdgePilot.lnk"
        if lnk_file.exists():
            lnk_file.unlink()

        # Remove old VBS launcher (if exists from previous version)
        vbs_file = desktop / "EdgePilot.vbs"
        if vbs_file.exists():
            vbs_file.unlink()

        # Remove old batch file (if exists from previous version)
        batch_file = desktop / "EdgePilot.bat"
        if batch_file.exists():
            batch_file.unlink()

    def run(self):
        """Run the uninstaller."""
        self.root.mainloop()


# === Main Entry Point ===

def main():
    """Main entry point - decide install vs uninstall mode."""
    # Check platform - Windows only
    system = platform.system()
    if system != "Windows":
        print(f"Unsupported platform: {system}")
        print("EdgePilot installer currently supports Windows only.")
        sys.exit(1)

    try:
        # Check if installation is currently in progress
        if is_installation_in_progress():
            # Show message and exit - don't open another window
            temp_root = tk.Tk()
            temp_root.withdraw()
            messagebox.showinfo(
                "Installation in Progress",
                "EdgePilot installation is already in progress.\n\n"
                "Please wait for it to complete."
            )
            temp_root.destroy()
            sys.exit(0)

        # Check if EdgePilot is installed
        is_installed = check_if_installed()

        # Launch appropriate GUI
        if is_installed:
            app = UninstallerGUI()
        else:
            app = InstallerGUI()

        app.run()

    except KeyboardInterrupt:
        print("\nInstallation cancelled by user.")
        sys.exit(0)
    except Exception as e:
        print(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
