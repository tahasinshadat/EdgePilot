# EdgePilot Installer

This directory contains the cross-platform installer for EdgePilot.

## Features

The installer provides a user-friendly GUI that:
- ✅ Detects platform (Windows/macOS) automatically
- ✅ Downloads/clones the latest EdgePilot from GitHub
- ✅ Checks for git (uses direct download if not available)
- ✅ Prompts for API keys (Gemini required, Claude/GPT optional)
- ✅ Configures `.env` with user inputs and defaults
- ✅ Creates default `settings.json`
- ✅ Installs Python dependencies (`pip install -r requirements.txt`)
- ✅ Installs Node.js dependencies (`cd ui && npm install`)
- ✅ Creates desktop shortcut/application
  - **Windows**: Creates `.bat` file (or `.lnk` if pywin32 available)
  - **macOS**: Creates clickable `.app` bundle

## Building the Installer

### Prerequisites

- Python 3.8+
- pip

### Windows

```bash
cd installer
build_windows.bat
```

This creates `dist/Windows/EdgePilot-Installer-Windows.exe` that can be distributed to users.

### macOS

```bash
cd installer
chmod +x build_macos.sh
./build_macos.sh
```

This creates `dist/MacOS/EdgePilot-Installer-MacOS.app` that can be distributed to users.

## Using the Installer

### For End Users

1. **Download** the installer:
   - Windows: `EdgePilot-Installer-Windows.exe`
   - macOS: `EdgePilot-Installer-MacOS.app`

2. **Run** the installer by double-clicking it

3. **Configure** installation:
   - Choose installation location (default: `~/EdgePilot` on Windows, `~/Applications/EdgePilot` on macOS)
   - Enter **Gemini API Key** (required) - Get from https://aistudio.google.com/app/apikey
   - Optionally enter Claude API Key - Get from https://console.anthropic.com/
   - Optionally enter GPT API Key - Get from https://platform.openai.com/api-keys
   - Check "Create Desktop Shortcut" if you want easy access

4. **Click "Install EdgePilot"** and wait for completion

5. **Launch EdgePilot** from:
   - Windows: Desktop shortcut or batch file
   - macOS: `~/Applications/EdgePilot.app`

## Requirements for Users

The installer automatically handles most dependencies, but users must have:

### Windows
- **Python 3.8+** - Download from https://python.org/
- **Node.js 18+** - Download from https://nodejs.org/
- **Git** (optional, but recommended) - Download from https://git-scm.com/

### macOS
- **Python 3.8+** - Usually pre-installed, or install from https://python.org/
- **Node.js 18+** - Download from https://nodejs.org/
- **Git** (optional, but recommended) - Usually pre-installed

## How It Works

### Installation Process

1. **Platform Detection**: Detects Windows or macOS
2. **Git Check**: Checks if git is installed
   - If yes: Clones repository using `git clone`
   - If no: Downloads repository as zip file
3. **User Input**: GUI prompts for API keys and options
4. **Configuration**: Creates `env/.env` with user's API keys and defaults
5. **Settings**: Creates `data/settings.json` with default values
6. **Python Dependencies**: Runs `pip install -r requirements.txt`
7. **Node.js Dependencies**: Runs `npm install` in `ui/` directory
8. **Desktop Integration**: Creates platform-specific launcher
   - Windows: Batch file that runs `python main.py`
   - macOS: App bundle with launcher script
9. **Completion**: Shows success message with installation location

### File Structure After Installation

```
~/EdgePilot/  (or chosen location)
├── env/
│   └── .env                    # Configured with user's API keys
├── data/
│   └── settings.json           # Default settings
├── ui/
│   └── node_modules/           # Installed Electron dependencies
├── main.py                     # Entry point
├── requirements.txt
└── ...

Desktop/
└── EdgePilot.lnk              # Windows shortcut
    or
~/Applications/
└── EdgePilot.app              # macOS application
```

## Distributing the Installer

### GitHub Releases (Recommended)

1. Build installers for both platforms
2. Create a new GitHub release
3. Upload both executables:
   - `EdgePilot-Installer.exe` (Windows)
   - `EdgePilot-Installer.app` (macOS) - zip it first
4. Users can download from Releases page

### Direct Download

Host the executables on a web server and provide download links.

## Troubleshooting

### "Node.js not found" error
- User needs to install Node.js 18+ from https://nodejs.org/
- After installing, run the installer again

### "Python not found" error (rare on modern systems)
- User needs to install Python 3.8+ from https://python.org/
- Make sure "Add Python to PATH" is checked during installation

### macOS: "App is damaged" message
- This happens because the app isn't signed
- User can right-click > Open to bypass Gatekeeper
- Or run: `xattr -cr "EdgePilot Installer.app"`

### Windows: SmartScreen warning
- This happens because the installer isn't signed with a code signing certificate
- User can click "More info" > "Run anyway"

## Code Signing (Optional)

For production releases, you should sign the installers:

### Windows
- Purchase a code signing certificate
- Use `signtool.exe` to sign the `.exe`

### macOS
- Enroll in Apple Developer Program ($99/year)
- Sign with `codesign` and notarize with `notarytool`

## License

MIT License - See LICENSE file for details
