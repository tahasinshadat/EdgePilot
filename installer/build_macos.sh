#!/bin/bash
# Build macOS installer executable using PyInstaller

echo "Building EdgePilot Installer for macOS..."

# Install PyInstaller if not already installed
pip install -r requirements.txt

# Build executable
pyinstaller --onefile \
    --windowed \
    --name "EdgePilot-Installer" \
    --icon="../assets/logo.icns" \
    --add-data "../assets/logo.icns:assets" \
    install.py

echo ""
echo "Build complete! Installer is in dist/EdgePilot-Installer"
echo ""

# Make the installer executable
chmod +x dist/EdgePilot-Installer

# Optionally create a .app bundle
echo "Creating .app bundle..."
mkdir -p "dist/EdgePilot Installer.app/Contents/MacOS"
mkdir -p "dist/EdgePilot Installer.app/Contents/Resources"

# Move executable
mv dist/EdgePilot-Installer "dist/EdgePilot Installer.app/Contents/MacOS/"

# Create Info.plist
cat > "dist/EdgePilot Installer.app/Contents/Info.plist" << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>EdgePilot Installer</string>
    <key>CFBundleDisplayName</key>
    <string>EdgePilot Installer</string>
    <key>CFBundleIdentifier</key>
    <string>com.edgepilot.installer</string>
    <key>CFBundleVersion</key>
    <string>1.0</string>
    <key>CFBundleExecutable</key>
    <string>EdgePilot-Installer</string>
    <key>CFBundleIconFile</key>
    <string>logo</string>
    <key>LSMinimumSystemVersion</key>
    <string>10.13</string>
    <key>NSHighResolutionCapable</key>
    <true/>
</dict>
</plist>
EOF

# Copy icon
if [ -f "../assets/logo.icns" ]; then
    cp "../assets/logo.icns" "dist/EdgePilot Installer.app/Contents/Resources/logo.icns"
fi

echo ""
echo "App bundle created at: dist/EdgePilot Installer.app"
echo "You can now distribute this .app bundle to users!"
