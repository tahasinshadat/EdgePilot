"""
Simple application launcher with timer support for Windows.
Uses Windows Start Menu shortcuts (the same system Windows Search uses).
"""

import os
import time
import subprocess
import threading
from pathlib import Path
from typing import List, Optional


def get_start_menu_paths() -> List[Path]:
    """Get all Windows Start Menu directories."""
    paths = []
    
    # User's Start Menu
    user_start = Path(os.environ.get('APPDATA', '')) / 'Microsoft' / 'Windows' / 'Start Menu' / 'Programs'
    if user_start.exists():
        paths.append(user_start)
    
    # All Users Start Menu
    programdata = os.environ.get('PROGRAMDATA', 'C:\\ProgramData')
    all_users_start = Path(programdata) / 'Microsoft' / 'Windows' / 'Start Menu' / 'Programs'
    if all_users_start.exists():
        paths.append(all_users_start)
    
    return paths


def get_microsoft_store_apps() -> List[tuple]:
    """
    Get Microsoft Store / UWP apps (like Minecraft).
    Returns list of (app_name, app_id) tuples.
    """
    store_apps = []
    
    try:
        # Use PowerShell to get installed UWP apps
        ps_command = "Get-AppxPackage | Select-Object Name, PackageFamilyName"
        result = subprocess.run(
            ['powershell', '-Command', ps_command],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            for line in lines[3:]:  # Skip header lines
                line = line.strip()
                if line:
                    parts = line.split(None, 1)
                    if len(parts) == 2:
                        name = parts[0]
                        family_name = parts[1] if len(parts) > 1 else ""
                        store_apps.append((name, family_name))
    except Exception as e:
        pass  # Silently fail if PowerShell not available
    
    return store_apps


def search_start_menu(app_name: str, verbose: bool = False) -> List[str]:
    """
    Search Windows Start Menu for app shortcuts (same as Windows Search does).
    Returns list of .lnk shortcut paths.
    """
    app_name_lower = app_name.lower()
    shortcuts = []
    
    start_menu_paths = get_start_menu_paths()
    
    if verbose:
        print(f"Searching in {len(start_menu_paths)} Start Menu locations...")
        for path in start_menu_paths:
            print(f"  - {path}")
    
    for start_menu_path in start_menu_paths:
        # Walk through all subdirectories
        for root, dirs, files in os.walk(start_menu_path):
            for file in files:
                if file.lower().endswith('.lnk'):
                    # Check if app name is in the shortcut name
                    if app_name_lower in file.lower():
                        full_path = os.path.join(root, file)
                        shortcuts.append(full_path)
                        if verbose:
                            print(f"  ✓ Match: {file}")
    
    return shortcuts


def search_store_apps(app_name: str, verbose: bool = False) -> Optional[str]:
    """
    Search Microsoft Store / UWP apps (like Minecraft).
    Returns the app package name if found.
    """
    app_name_lower = app_name.lower()
    
    if verbose:
        print(f"Searching Microsoft Store apps...")
    
    store_apps = get_microsoft_store_apps()
    
    for name, package_family in store_apps:
        if app_name_lower in name.lower():
            if verbose:
                print(f"  ✓ Found Store app: {name}")
            return f"shell:AppsFolder\\{package_family}!App"
    
    return None


def launch_shortcut(shortcut_path: str, delay_seconds: int = 0) -> None:
    """
    Launch a Windows shortcut (.lnk file) after an optional delay.
    """
    def delayed_launch():
        if delay_seconds > 0:
            print(f"Waiting {delay_seconds} seconds before launching {Path(shortcut_path).stem}...")
            time.sleep(delay_seconds)
        
        try:
            # Use os.startfile to launch the shortcut (Windows-native way)
            os.startfile(shortcut_path)
            print(f"✓ Launched {Path(shortcut_path).stem}")
        except Exception as e:
            print(f"✗ Error launching {shortcut_path}: {e}")
    
    if delay_seconds > 0:
        # Run in background thread
        thread = threading.Thread(target=delayed_launch, daemon=True)
        thread.start()
        print(f"Scheduled {Path(shortcut_path).stem} to launch in {delay_seconds} seconds...")
    else:
        delayed_launch()


def launch(app_name: str, delay_seconds: int = 0) -> bool:
    """
    Launch an application by name (same way Windows Start Menu works).
    
    Args:
        app_name: Name of the application (e.g., "minecraft", "chrome", "notepad")
        delay_seconds: Number of seconds to wait before launching (default: 0)
    
    Returns:
        True if application was found and scheduled, False otherwise
    
    Examples:
        >>> launch("minecraft", 30)  # Launch Minecraft in 30 seconds
        >>> launch("chrome")  # Launch Chrome immediately
        >>> launch("notepad", 5)  # Launch Notepad in 5 seconds
    """
    # Step 1: Search Start Menu shortcuts (traditional apps)
    shortcuts = search_start_menu(app_name, verbose=False)
    
    if shortcuts:
        # Show what we found
        if len(shortcuts) == 1:
            print(f"Found: {Path(shortcuts[0]).stem}")
        else:
            print(f"Found {len(shortcuts)} matches:")
            for i, shortcut in enumerate(shortcuts[:3], 1):  # Show first 3
                print(f"  {i}. {Path(shortcut).stem}")
            print(f"Using: {Path(shortcuts[0]).stem}")
        
        # Launch the first match
        launch_shortcut(shortcuts[0], delay_seconds)
        return True
    
    # Step 2: Search Microsoft Store / UWP apps (like Minecraft)
    print(f"Not found in Start Menu, checking Microsoft Store apps...")
    store_app = search_store_apps(app_name, verbose=True)
    
    if store_app:
        print(f"Found Microsoft Store app!")
        
        def launch_store_app():
            if delay_seconds > 0:
                print(f"Waiting {delay_seconds} seconds before launching...")
                time.sleep(delay_seconds)
            
            try:
                # Launch UWP app using explorer with shell protocol
                subprocess.Popen(['explorer.exe', store_app])
                print(f"✓ Launched {app_name}")
            except Exception as e:
                print(f"✗ Error: {e}")
        
        if delay_seconds > 0:
            thread = threading.Thread(target=launch_store_app, daemon=True)
            thread.start()
            print(f"Scheduled to launch in {delay_seconds} seconds...")
        else:
            launch_store_app()
        
        return True
    
    # Step 3: Fallback to Windows 'start' command for built-in apps
    print(f"Trying Windows built-in command as fallback...")
    
    def try_start_command():
        if delay_seconds > 0:
            print(f"Waiting {delay_seconds} seconds before launching {app_name}...")
            time.sleep(delay_seconds)
        
        try:
            subprocess.Popen(['cmd', '/c', 'start', '', app_name], 
                           shell=True,
                           stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
            print(f"✓ Launched {app_name}")
        except Exception as e:
            print(f"✗ Error launching {app_name}: {e}")
    
    if delay_seconds > 0:
        thread = threading.Thread(target=try_start_command, daemon=True)
        thread.start()
        print(f"Scheduled {app_name} to launch in {delay_seconds} seconds...")
    else:
        try_start_command()
    
    return True


def list_installed_apps(search_term: str = "") -> List[str]:
    """
    List all installed applications in Start Menu.
    Optionally filter by search term.
    
    Args:
        search_term: Optional filter (e.g., "game" to see all game-related apps)
    
    Returns:
        List of application names
    """
    shortcuts = []
    search_lower = search_term.lower()
    
    for start_menu_path in get_start_menu_paths():
        for root, dirs, files in os.walk(start_menu_path):
            for file in files:
                if file.lower().endswith('.lnk'):
                    app_name = Path(file).stem
                    if not search_term or search_lower in app_name.lower():
                        shortcuts.append(app_name)
    
    # Remove duplicates and sort
    return sorted(set(shortcuts))


# Alternative simpler functions for specific use cases

def launch_now(app_name: str) -> bool:
    """Launch app immediately."""
    return launch(app_name, 0)


def launch_in(app_name: str, seconds: int) -> bool:
    """Launch app after delay."""
    return launch(app_name, seconds)


# ============================================================================
# SIMPLE LLM-FRIENDLY API (Just 3 functions!)
# ============================================================================

def search(app_name: str) -> List[str]:
    """
    Search for applications matching a name.
    Returns a list of app names found.
    
    🤖 LLM USE: When user asks "do I have X?" or "is X installed?"
    
    Args:
        app_name: Search term (e.g., "game", "office", "chrome")
    
    Returns:
        List of matching application names
    
    Examples:
        >>> search("chrome")
        ['Google Chrome']
        
        >>> search("minecraft")
        ['Minecraft Launcher', 'Minecraft']
        
        >>> apps = search("game")
        >>> print(f"Found {len(apps)} games")
    """
    results = []
    
    # Search Start Menu shortcuts
    shortcuts = search_start_menu(app_name, verbose=False)
    for shortcut in shortcuts:
        app_title = Path(shortcut).stem
        if app_title not in results:
            results.append(app_title)
    
    # Search Store apps
    store_app = search_store_apps(app_name, verbose=False)
    if store_app:
        # Add the app name as title case as approximation
        results.append(app_name.title())
    
    return results


def list_apps(filter_term: str = "") -> List[str]:
    """
    List all installed applications, optionally filtered by a search term.
    
    🤖 LLM USE: When user asks "what apps do I have?" or "list my games"
    
    Args:
        filter_term: Optional search term to filter results (e.g., "game", "microsoft")
                    Leave empty to get ALL apps
    
    Returns:
        Sorted list of application names
    
    Examples:
        >>> games = list_apps("game")
        >>> print(games)
        ['Game Bar', 'Minecraft', 'Steam']
        
        >>> all_apps = list_apps()
        >>> print(f"You have {len(all_apps)} apps installed")
    """
    return list_installed_apps(filter_term)


# ============================================================================
# LLM WORKFLOW DOCUMENTATION
# ============================================================================

"""
LLM QUICK REFERENCE
===================

3 FUNCTIONS FOR LLM USE:
-------------------------

1. launch(app_name, seconds=0) ⭐ MAIN FUNCTION
   - Use when user wants to launch/open/start an app
   - Examples:
     * launch("minecraft", 30)  # Launch in 30 seconds
     * launch("chrome")          # Launch now
     * launch("notepad", 5)      # Launch in 5 seconds

2. search(app_name) 🔍 VERIFICATION
   - Use when user asks "do I have X?" or "is X installed?"
   - Examples:
     * results = search("discord")
     * if results: print("Found!")

3. list_apps(filter_term="") 📋 BROWSE
   - Use when user asks "what apps do I have?"
   - Examples:
     * games = list_apps("game")
     * all_apps = list_apps()

WORKFLOW:
---------
User: "Launch Minecraft in 30 seconds"
  → launch("minecraft", 30)

User: "What games do I have?"
  → games = list_apps("game")
  → [Show list to user]

User: "Do I have Discord? If so, open it"
  → if search("discord"):
        launch("discord", 0)

TIME PARSING:
-------------
"30 seconds" → 30
"2 minutes" → 120
"1 hour" → 3600
"now" → 0
"""

if __name__ == "__main__":
    print("=== Testing App Launcher ===\n")
    
    # Test 1: Launch notepad immediately
    print("Test 1: Launch Notepad now")
    launch("notepad", 0)
    
    print("\n" + "="*50 + "\n")
    
    # Test 2: Schedule Minecraft
    print("Test 2: Schedule Minecraft in 3 seconds")
    launch("minecraft", 3)
    
    print("\n" + "="*50 + "\n")
    
    # Test 3: Launch Chrome
    print("Test 3: Launch Chrome in 1 second")
    launch("chrome", 1)
    
    print("\n" + "="*50 + "\n")
    
    # Test 4: List some installed apps
    print("Test 4: Show some installed apps with 'game' in the name")
    game_apps = list_apps("game")
    for app in game_apps[:5]:
        print(f"  - {app}")
    
    print("\n" + "="*50 + "\n")
    
    # Test 5: Search for an app
    print("Test 5: Search for Discord")
    discord_results = search("discord")
    if discord_results:
        print(f"Found: {discord_results}")
    else:
        print("Discord not found")
    
    # Keep running to see delayed launches
    print("\n" + "="*50)
    print("Waiting for scheduled launches...")
    time.sleep(5)
    print("\nDone!")
