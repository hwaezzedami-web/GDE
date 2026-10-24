@echo off
echo ============================================
echo   PS Core KPI Report Generator
echo ============================================
echo.

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH.
    echo Please install Python from https://www.python.org/downloads/
    pause
    exit /b 1
)

REM Install required packages if needed
echo Checking dependencies...
pip install openpyxl xlrd pandas --quiet 2>nul

echo.
echo Running report generator...
echo.
python "%~dp0generate_kpi_report.py"

echo.
if errorlevel 1 (
    echo ERROR: Report generation failed!
) else (
    echo Opening output folder...
    explorer "%~dp0output"
)

echo.
pause
