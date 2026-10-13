@echo off
echo ============================================
echo  Building Maintenance Engineer Toolkit .exe
echo ============================================
echo.

REM Install PyInstaller if not present
pip install pyinstaller

REM Build single-file executable
pyinstaller --onefile --windowed --name "MaintenanceToolkit" --icon=NONE app.py

echo.
echo ============================================
echo  Build complete!
echo  Your .exe is in the dist\ folder
echo ============================================
pause
