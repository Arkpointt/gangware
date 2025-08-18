@echo off
REM Gangware Application Launcher Script for Windows
REM This script runs the application using the virtual environment

echo Starting Gangware...
"%~dp0.venv\Scripts\python.exe" "%~dp0main.py" %*
