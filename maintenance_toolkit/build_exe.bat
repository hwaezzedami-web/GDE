@echo off
echo ============================================
echo  Building Maintenance Engineer Toolkit .exe
echo ============================================
echo.

REM Try to find Python
where python >nul 2>&1
if %errorlevel%==0 (
    set PYTHON=python
    goto :found
)

where python3 >nul 2>&1
if %errorlevel%==0 (
    set PYTHON=python3
    goto :found
)

where py >nul 2>&1
if %errorlevel%==0 (
    set PYTHON=py
    goto :found
)

REM Check common install locations
if exist "C:\Python313\python.exe" (
    set PYTHON=C:\Python313\python.exe
    goto :found
)
if exist "C:\Python312\python.exe" (
    set PYTHON=C:\Python312\python.exe
    goto :found
)
if exist "C:\Python311\python.exe" (
    set PYTHON=C:\Python311\python.exe
    goto :found
)
if exist "C:\Python310\python.exe" (
    set PYTHON=C:\Python310\python.exe
    goto :found
)
if exist "C:\Python39\python.exe" (
    set PYTHON=C:\Python39\python.exe
    goto :found
)
if exist "C:\Python38\python.exe" (
    set PYTHON=C:\Python38\python.exe
    goto :found
)

REM Check AppData (Microsoft Store install)
for /d %%d in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
    if exist "%%d\python.exe" (
        set PYTHON=%%d\python.exe
        goto :found
    )
)

echo ERROR: Python not found!
echo.
echo Please install Python from https://www.python.org/downloads/
echo IMPORTANT: Check "Add Python to PATH" during installation.
echo.
echo Or if Python is already installed, run this manually:
echo   "C:\path\to\python.exe" -m pip install pyinstaller
echo   "C:\path\to\python.exe" -m PyInstaller --onefile --windowed --name MaintenanceToolkit app.py
echo.
pause
exit /b 1

:found
echo Found Python: %PYTHON%
echo.

REM Install PyInstaller
echo Installing PyInstaller...
"%PYTHON%" -m pip install pyinstaller
if %errorlevel% neq 0 (
    echo.
    echo ERROR: pip install failed. Try running as Administrator.
    pause
    exit /b 1
)

echo.
echo Building .exe ...
"%PYTHON%" -m PyInstaller --onefile --windowed --name "MaintenanceToolkit" app.py
if %errorlevel% neq 0 (
    echo.
    echo ERROR: Build failed.
    pause
    exit /b 1
)

echo.
echo ============================================
echo  Build complete!
echo  Your .exe is in the dist\ folder:
echo  %cd%\dist\MaintenanceToolkit.exe
echo ============================================
pause
