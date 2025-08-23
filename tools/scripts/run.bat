@echo off
REM Gangware Application Launcher Script for Windows
REM This script runs the application using the virtual environment

echo Starting Gangware...
set SCRIPT_DIR=%~dp0
set PROJECT_ROOT=%SCRIPT_DIR%..\..
"%PROJECT_ROOT%\.venv\Scripts\python.exe" "%SCRIPT_DIR%main.py" %*
