@echo off
REM Run Gangware as Administrator

:: Check for admin privileges
openfiles >nul 2>&1
if %errorlevel% NEQ 0 (
	echo Requesting administrator privileges...
	powershell -Command "Start-Process '%COMSPEC%' -ArgumentList '/c, "%~f0" %*' -Verb RunAs"
	exit /b
)

set SCRIPT_DIR=%~dp0
set PROJECT_ROOT=%SCRIPT_DIR%..\..
"%PROJECT_ROOT%\.venv\Scripts\python.exe" -m gangware.main %*
