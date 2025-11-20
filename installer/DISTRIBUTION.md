# Distributing EdgePilot Installer

This guide explains how to build and distribute the EdgePilot installer.

## Building the Installer

### For Windows (on Windows machine)

1. Navigate to installer directory:
   ```bash
   cd installer
   ```

2. Run the build script:
   ```bash
   build_windows.bat
   ```

3. Find the executable:
   ```
   installer/dist/EdgePilot-Installer.exe
   ```

### For macOS (on macOS machine)

1. Navigate to installer directory:
   ```bash
   cd installer
   ```

2. Make build script executable (first time only):
   ```bash
   chmod +x build_macos.sh
   ```

3. Run the build script:
   ```bash
   ./build_macos.sh
   ```

4. Find the app bundle:
   ```
   installer/dist/EdgePilot Installer.app
   ```

## Testing the Installer

### Before Distribution

Always test the installer before distributing:

1. **Run the installer** on a clean machine (or VM)
2. **Verify** all steps complete successfully
3. **Test** the installed EdgePilot application
4. **Check** that all features work (MCP tools, UI, settings)

### Test Checklist

- [ ] Installer GUI appears correctly
- [ ] API key validation works (requires Gemini key)
- [ ] Repository downloads successfully
- [ ] Dependencies install without errors
- [ ] Desktop shortcut/app is created
- [ ] EdgePilot launches from shortcut
- [ ] MCP tools work (run `python test_tools.py`)
- [ ] UI launches correctly (`python main.py`)

## Distribution Methods

### Method 1: GitHub Releases (Recommended)

This is the easiest way for users to find and download the installer.

1. **Build installers** for both platforms

2. **Create a new release** on GitHub:
   ```bash
   # Tag your release
   git tag v1.0.0
   git push origin v1.0.0
   ```

3. **Go to GitHub** → Releases → Draft a new release

4. **Upload files**:
   - `EdgePilot-Installer.exe` (Windows)
   - `EdgePilot-Installer.app.zip` (macOS - zip the .app first)

5. **Write release notes**:
   ```markdown
   ## EdgePilot v1.0.0

   ### Installation

   **Windows:**
   1. Download `EdgePilot-Installer.exe`
   2. Run the installer
   3. Follow on-screen instructions

   **macOS:**
   1. Download `EdgePilot-Installer.app.zip`
   2. Extract the zip
   3. Right-click on the app → Open
   4. Follow on-screen instructions

   ### Prerequisites
   - Python 3.8+
   - Node.js 18+
   - Gemini API Key (get from https://aistudio.google.com/app/apikey)

   ### What's New
   - Initial release
   - Full MCP integration
   - Usage alerts with email notifications
   - Cross-platform support
   ```

6. **Publish the release**

### Method 2: Direct Download (Website)

If you have a website:

1. Upload installers to your web server
2. Create download links on your website
3. Include instructions and prerequisites

### Method 3: Package Managers (Advanced)

For wider distribution:

**Windows:**
- [Chocolatey](https://chocolatey.org/)
- [Scoop](https://scoop.sh/)
- [WinGet](https://github.com/microsoft/winget-pkgs)

**macOS:**
- [Homebrew Cask](https://docs.brew.sh/How-to-Create-and-Maintain-a-Tap)

## Code Signing (Optional but Recommended)

### Why Code Sign?

- **Windows**: Prevents SmartScreen warnings
- **macOS**: Prevents Gatekeeper warnings
- **Trust**: Users trust signed applications more

### Windows Code Signing

1. **Purchase a code signing certificate** (~$100-300/year)
   - DigiCert
   - Sectigo
   - GlobalSign

2. **Sign the executable**:
   ```bash
   signtool sign /f certificate.pfx /p password /tr http://timestamp.digicert.com /td sha256 /fd sha256 EdgePilot-Installer.exe
   ```

### macOS Code Signing

1. **Enroll in Apple Developer Program** ($99/year)

2. **Get a Developer ID**

3. **Sign the app**:
   ```bash
   codesign --deep --force --sign "Developer ID Application: Your Name" "EdgePilot Installer.app"
   ```

4. **Notarize the app**:
   ```bash
   # Create a zip for notarization
   ditto -c -k --keepParent "EdgePilot Installer.app" EdgePilot-Installer.zip

   # Submit for notarization
   xcrun notarytool submit EdgePilot-Installer.zip \
     --apple-id "your@email.com" \
     --password "app-specific-password" \
     --team-id "YOUR_TEAM_ID" \
     --wait

   # Staple the notarization ticket
   xcrun stapler staple "EdgePilot Installer.app"
   ```

## File Sizes

Typical installer sizes:

- **Windows**: ~15-25 MB (compressed with UPX)
- **macOS**: ~20-30 MB

To reduce size:
- Use PyInstaller's `--onefile` mode (already enabled)
- Exclude unnecessary modules with `--exclude-module`
- Use UPX compression (automatic with PyInstaller)

## Updating the Installer

When you make changes to EdgePilot:

1. **Update version number** in installer (if you add versioning)
2. **Rebuild installers** for both platforms
3. **Test thoroughly**
4. **Create new GitHub release**
5. **Update download links** if using direct download

## Troubleshooting Build Issues

### Windows

**"PyInstaller not found"**
```bash
pip install pyinstaller
```

**Icon not found**
- Make sure `assets/logo.png` exists
- Or remove `--icon` flag from build script

### macOS

**Permission denied**
```bash
chmod +x build_macos.sh
```

**"pyinstaller: command not found"**
```bash
pip3 install pyinstaller
```

## Security Considerations

### What Users See

**Windows:**
- SmartScreen warning (unless signed)
- "Unknown publisher" message
- User must click "More info" → "Run anyway"

**macOS:**
- Gatekeeper warning (unless signed and notarized)
- "App is from an unidentified developer"
- User must right-click → Open (first time)

### How to Help Users

1. **Provide clear instructions** in release notes
2. **Explain why warnings appear** (app isn't signed)
3. **Consider code signing** for production releases

## Best Practices

1. **Always test** on clean machines before distributing
2. **Include clear instructions** with each release
3. **List prerequisites** prominently
4. **Provide screenshots** of installation process
5. **Offer support** via GitHub Issues
6. **Keep README updated** with latest installation info
7. **Sign installers** for production releases
8. **Version your releases** with semantic versioning

## Support

If users encounter issues:
- Direct them to [INSTALL.md](../INSTALL.md)
- Check [installer/README.md](README.md) for troubleshooting
- Create GitHub issues for bugs

## License

The installer is part of EdgePilot and uses the same MIT License.
