import os
import shutil
import psutil
from typing import Any, Dict, List
import logging

logger = logging.getLogger(__name__)

def preview_free_disk_space() -> Dict[str, Any]:
    """
    (SAFE) Scans system temp files and browser caches to report what CAN be deleted and how much space it will free.
    Does NOT delete anything.
    """
    total_bytes = 0
    deletable_items = []
    
    home = os.path.expanduser('~')
    
    import sys
    
    if os.name == 'nt':
        targets = [
            os.environ.get('TEMP', 'C:\\Temp'),
            os.path.join(home, 'AppData', 'Local', 'Temp'),
        ]
    else:
        # Universal Unix/Linux/macOS paths
        targets = [
            '/tmp',
            os.path.join(home, '.cache'),
            # Package manager download caches (safe — just re-downloads on next install)
            os.path.join(home, '.npm', '_cacache'),
            os.path.join(home, '.yarn', 'cache'),
            os.path.join(home, '.pnpm-store'),
            os.path.join(home, '.pip', 'cache'),
            os.path.join(home, '.conda', 'pkgs'),
            os.path.join(home, '.cargo', 'registry', 'cache'),
            os.path.join(home, '.gradle', 'caches'),
            os.path.join(home, '.m2', 'repository'),
            os.path.join(home, '.nuget', 'packages'),
            os.path.join(home, '.gem'),
        ]
        
        # macOS-specific paths
        if sys.platform == 'darwin':
            targets.extend([
                os.path.join(home, 'Library', 'Caches', 'pip'),
                os.path.join(home, 'Library', 'Caches', 'Homebrew'),
                '/opt/homebrew/cache',
                os.path.join(home, 'Library', 'Developer', 'Xcode', 'DerivedData'),
                os.path.join(home, 'Library', 'Developer', 'CoreSimulator', 'Caches'),
                os.path.join(home, 'Library', 'Caches', 'CocoaPods'),
                os.path.join(home, 'Library', 'Caches', 'org.carthage.CarthageKit'),
                os.path.join(home, 'Library', 'Logs'),
                os.path.join(home, 'Library', 'Logs', 'DiagnosticReports'),
            ])
        
        # Linux-specific paths
        if sys.platform == 'linux':
            targets.extend([
                '/var/tmp',
                os.path.join(home, '.local', 'share', 'flatpak', 'repo', 'tmp'),
                '/var/log',
            ])
        
    for target in targets:
        if not os.path.exists(target):
            continue
        try:
            for item in os.listdir(target):
                item_path = os.path.join(target, item)
                try:
                    size = 0
                    if os.path.isfile(item_path) or os.path.islink(item_path):
                        size = os.path.getsize(item_path)
                    elif os.path.isdir(item_path):
                        for dirpath, _, filenames in os.walk(item_path):
                            for filename in filenames:
                                try:
                                    size += os.path.getsize(os.path.join(dirpath, filename))
                                except OSError:
                                    pass
                    total_bytes += size
                    if size > 1024 * 1024:  # Only report items > 1MB to keep it clean
                        deletable_items.append({"path": item_path, "size_mb": round(size / (1024 * 1024), 2)})
                except Exception:
                    pass
        except Exception:
            pass
            
    # Sort by largest size
    deletable_items = sorted(deletable_items, key=lambda x: x['size_mb'], reverse=True)

    return {
        "success": True,
        "message": f"Found {round(total_bytes / (1024 * 1024), 2)} MB of junk files.",
        "total_freed_mb": round(total_bytes / (1024 * 1024), 2),
        "largest_items_found": deletable_items[:10], # Return top 10 largest items
        "next_step": "If the user wants to proceed, call execute_free_disk_space."
    }

def execute_free_disk_space(paths_to_delete: List[str]) -> Dict[str, Any]:
    """
    (HITL REQUIRED) Actually executes the deletion of system temp files and caches.
    """
    freed_bytes = 0
    for item_path in paths_to_delete:
        if not os.path.exists(item_path):
            continue
        try:
            if os.path.isfile(item_path) or os.path.islink(item_path):
                size = os.path.getsize(item_path)
                os.unlink(item_path)
                freed_bytes += size
            elif os.path.isdir(item_path):
                size = 0
                for dirpath, _, filenames in os.walk(item_path):
                    for filename in filenames:
                        try:
                            size += os.path.getsize(os.path.join(dirpath, filename))
                        except OSError:
                            pass
                # Add the size first, then attempt to delete ignoring locked file errors
                freed_bytes += size
                shutil.rmtree(item_path, ignore_errors=True)
        except Exception as e:
            logger.debug(f"Failed to delete {item_path}: {e}")

    mb_freed = freed_bytes / (1024 * 1024)
    return {
        "success": True,
        "message": f"Successfully cleared {mb_freed:.2f} MB of temporary files.",
        "freed_bytes": freed_bytes,
    }

def hibernate_background_apps(app_names: List[str]) -> Dict[str, Any]:
    """
    (HITL REQUIRED) Identifies and suspends heavy background processes.
    """
    suspended = []
    failed = []
    
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            name = proc.info['name'].lower() if proc.info['name'] else ''
            if any(app.lower() in name for app in app_names):
                proc.suspend()
                suspended.append(proc.info['name'])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            failed.append(proc.info['name'] if proc.info['name'] else "Unknown")
        except AttributeError:
             # some OSes don't support suspend, fallback to terminate
             try:
                 proc.terminate()
                 suspended.append(proc.info['name'])
             except Exception:
                 pass
            
    return {
        "success": len(suspended) > 0,
        "suspended_apps": suspended,
        "failed_to_suspend": failed,
        "message": f"Suspended {len(suspended)} background processes matching: {', '.join(app_names)}"
    }

def analyze_network_hogs() -> Dict[str, Any]:
    """
    Queries active network connections to find apps silently downloading/uploading massive amounts of data.
    """
    hogs = {}
    try:
        # We can look at connections to find active processes.
        connections = psutil.net_connections(kind='inet')
        for conn in connections:
            if conn.pid:
                if conn.pid not in hogs:
                    try:
                        proc = psutil.Process(conn.pid)
                        hogs[conn.pid] = {"process": proc.name(), "connections": 1}
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
                else:
                    hogs[conn.pid]["connections"] += 1
                    
        # Sort by most connections
        top_hogs = sorted(hogs.values(), key=lambda x: x["connections"], reverse=True)[:5]
        
        return {
            "success": True,
            "top_network_hogs": top_hogs,
            "message": f"Analyzed network connections. Top active network processes: {', '.join([h['process'] for h in top_hogs])}"
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
