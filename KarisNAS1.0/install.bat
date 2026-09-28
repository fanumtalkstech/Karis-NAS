@echo off
setlocal
title Karis-NAS 1.0 - Installer

echo ===============================================================================
echo   Karis-NAS 1.0 - Installation ^& Update
echo ===============================================================================
echo.

where python >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python 3 was not found in your system PATH!
    echo.
    echo Please install Python 3.8 or higher from https://www.python.org/downloads/
    echo Be sure to check the box "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)

python installer.py

pause
