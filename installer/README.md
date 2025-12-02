# EdgePilot Installer

Cross-platform installers for EdgePilot AI Copilot Console.

## Files

- `install_windows.py` - Windows installer
- `install_macos.py` - macOS installer

## Features

Both installers provide a user-friendly GUI that:
- ✅ Downloads the latest EdgePilot from GitHub
- ✅ Prompts for API keys (Gemini required, Claude optional)
- ✅ Configures `.env` with user inputs and defaults
- ✅ Creates default `settings.json`
- ✅ Installs Python dependencies (`pip install -r requirements.txt`)
- ✅ Installs Node.js dependencies (`npm install`)
- ✅ Creates desktop shortcuts
  - **Windows**: Creates `.lnk` shortcut using VBScript
  - **macOS**: Creates `.command` shell script
- ✅ Functions as uninstaller if EdgePilot is already installed

## Building the Installers

### Prerequisites

- Python 3.8+
- PyInstaller: `pip install pyinstaller`

### Windows

```bash
# From the EdgePilot root directory
pyinstaller --onefile --windowed --icon=assets/logo.ico --name=EdgePilot-Installer-Windows-v1.0.1 installer/install_windows.py
```

The compiled `.exe` will be in the `dist/` folder.

### macOS

```bash
# From the EdgePilot root directory (on a Mac)
pyinstaller --onefile --windowed --icon=assets/logo.icns --name=EdgePilot-Installer-macOS-v1.0.1 installer/install_macos.py
```

The compiled `.app` will be in the `dist/` folder.

**Note:** For macOS, you may need to sign the app or allow it in System Preferences > Security & Privacy if you get a security warning.

## Using the Installer

### For End Users

1. **Download** the installer:
   - Windows: `EdgePilot-Installer-Windows-v1.0.1.exe`
   - macOS: `EdgePilot-Installer-macOS-v1.0.1.app`

2. **Run** the installer by double-clicking it

3. **Configure** installation:
   - Choose installation location
     - **Windows default:** `%USERPROFILE%\EdgePilot`
     - **macOS default:** `~/Applications/EdgePilot`
   - Enter **Gemini API Key** (required) - Get from https://aistudio.google.com/app/apikey
   - Optionally enter Claude API Key - Get from https://console.anthropic.com/
   - Check "Create Desktop Shortcut" if you want easy access

4. **Click "Install EdgePilot"** and wait for completion

5. **Launch EdgePilot** from:
   - Windows: Desktop shortcut (`EdgePilot.lnk`)
   - macOS: Desktop shortcut (`EdgePilot.command`)

## Requirements for Users

The installer automatically handles most dependencies, but users must have:

### Windows
- **Python 3.8+** - Download from https://python.org/
- **Node.js 18+** - Download from https://nodejs.org/

### macOS
- **Python 3** - Usually pre-installed, or install from https://python.org/
- **Node.js 18+** - Download from https://nodejs.org/

## What the Installers Do

Both installers:

1. **Download** EdgePilot from GitHub (direct zip download)
2. **Extract** to the chosen installation directory
3. **Configure** environment files with API keys
4. **Install** Python dependencies using `pip`
5. **Install** Node.js dependencies using `npm`
6. **Create** desktop shortcuts for easy launching
7. **Function as uninstaller** if EdgePilot is already installed

## How It Works

### Installation Process

1. **User Input**: GUI prompts for API keys and installation location
2. **Download**: Downloads EdgePilot repository as zip from GitHub
3. **Extract**: Extracts to the chosen installation directory
4. **Configuration**: Creates `env/.env` with user's API keys and defaults
5. **Settings**: Creates `data/settings.json` with default values
6. **Python Dependencies**: Runs `pip install -r requirements.txt`
7. **Node.js Dependencies**: Runs `npm install` in `ui/` directory
8. **Desktop Integration**: Creates platform-specific launcher
   - **Windows**: VBScript launcher that runs `python main.py` without console
   - **macOS**: Shell script (`.command`) that runs `python3 main.py`
9. **Completion**: Shows success message with option to launch immediately

### File Structure After Installation

```
~/EdgePilot/  (or chosen location)
├── env/
│   └── .env                    # Configured with user's API keys
├── data/
│   └── settings.json           # Default settings
├── ui/
│   └── node_modules/           # Installed Node.js dependencies
├── main.py                     # Entry point
├── requirements.txt
├── launch_edgepilot.vbs       # Windows launcher (Windows only)
├── launch_edgepilot.command   # macOS launcher (macOS only)
└── ...

Desktop/
└── EdgePilot.lnk              # Windows shortcut
    or
└── EdgePilot.command          # macOS shortcut
```

## Distributing the Installer

### GitHub Releases (Recommended)

1. Build installers for both platforms
2. Create a new GitHub release
3. Upload both executables:
   - `EdgePilot-Installer-Windows-v1.0.1.exe`
   - `EdgePilot-Installer-macOS-v1.0.1.app` (zip it first for upload)
4. Users can download from the Releases page

### Direct Download

Host the executables on a web server and provide download links.

## Testing Without Building

You can test the installers directly with Python before building:

```bash
# Windows
python installer/install_windows.py

# macOS
python3 installer/install_macos.py
```

## Troubleshooting

### "Cannot find file specified" error (Windows)
- Ensure Python is in the system PATH
- Ensure Node.js/npm is in the system PATH
- Try running Command Prompt as Administrator

### "Node.js not found" error
- Install Node.js 18+ from https://nodejs.org/
- Make sure to check "Add to PATH" during installation
- Restart the installer after installing Node.js

### "Python not found" error
- **Windows**: Install Python 3.8+ from https://python.org/
  - Check "Add Python to PATH" during installation
- **macOS**: Python 3 is usually pre-installed
  - If not, install from https://python.org/ or use Homebrew: `brew install python3`

### macOS: "App is damaged" or "cannot be opened" message
- This happens because the app isn't code-signed
- **Solution 1**: Right-click the app > "Open" (instead of double-clicking)
- **Solution 2**: Run in Terminal: `xattr -cr "/path/to/EdgePilot-Installer-macOS-v1.0.1.app"`
- **Solution 3**: Allow in System Preferences > Security & Privacy

### Windows: SmartScreen warning
- This happens because the installer isn't signed with a code signing certificate
- Click "More info" > "Run anyway"

### Permission errors during installation
- **Windows**: Run as Administrator
- **macOS**: Choose a different installation directory (avoid system directories)

## Platform-Specific Notes

### Windows

- Uses VBScript (`.vbs`) to create shortcuts and launch without console window
- Handles subprocess calls without creating visible console windows
- Detects OneDrive Desktop integration automatically

### macOS

- Creates executable shell scripts (`.command`) for launching
- Uses symlinks for desktop shortcuts (falls back to copying if symlinks fail)
- Uses `python3` command (macOS standard)
- No code signing by default (requires Apple Developer account)

## Code Signing (Optional)

For production releases, code signing is recommended:

### Windows
- Purchase a code signing certificate from a trusted CA
- Use `signtool.exe` to sign the `.exe`
- This eliminates SmartScreen warnings

### macOS
- Enroll in Apple Developer Program ($99/year)
- Sign with `codesign` and notarize with `notarytool`
- This eliminates "damaged app" warnings

## Version History

- **v1.0.1** - Current version
  - Improved subprocess handling to prevent "folder in use" errors
  - Fixed "cannot find file specified" error on Windows
  - Separate installers for Windows and macOS
  - Better error handling and cleanup
- **v1.0.0** - Initial release
