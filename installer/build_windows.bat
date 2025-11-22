@echo off
REM Build Windows installer executable using PyInstaller

echo Building EdgePilot Installer for Windows...

REM Install PyInstaller if not already installed
pip install -r requirements.txt

REM Build executable
pyinstaller --onefile ^
    --windowed ^
    --name "EdgePilot-Installer-Windows" ^
    --icon="../assets/logo.ico" ^
    --add-data "../assets/logo.ico;assets" ^
    --distpath "dist/Windows" ^
    install.py

echo.
echo Build complete! Installer is in dist/Windows/EdgePilot-Installer-Windows.exe
echo.
pause
