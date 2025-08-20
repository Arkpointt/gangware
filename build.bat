@echo off
echo ========================================
echo    Gangware Build Script
echo ========================================
echo.

:: Check if virtual environment is activated
if not defined VIRTUAL_ENV (
    echo Activating virtual environment...
    call .venv\Scripts\activate.bat
    if errorlevel 1 (
        echo ERROR: Failed to activate virtual environment
        echo Please make sure .venv exists and is properly set up
        pause
        exit /b 1
    )
)

echo Current Python: %VIRTUAL_ENV%\Scripts\python.exe
echo.

:: Clean previous builds
echo Cleaning previous builds...
if exist "dist" rmdir /s /q "dist"
if exist "build" rmdir /s /q "build"
echo.

:: Install/update PyInstaller if needed
echo Checking PyInstaller installation...
python -m pip install --upgrade pyinstaller
if errorlevel 1 (
    echo ERROR: Failed to install PyInstaller
    pause
    exit /b 1
)
echo.

:: Run tests first (optional but recommended)
echo Running quick smoke test...
python -m pytest tests/test_smoke.py -v --tb=short
if errorlevel 1 (
    echo WARNING: Some tests failed, but continuing with build...
    echo.
) else (
    echo Tests passed!
    echo.
)

:: Build the executable
echo Building Gangware executable...
echo This may take several minutes...
echo.
pyinstaller --clean gangware.spec

if errorlevel 1 (
    echo.
    echo ERROR: Build failed!
    echo Check the output above for error details.
    pause
    exit /b 1
)

:: Check if build was successful
if not exist "dist\Gangware.exe" (
    echo.
    echo ERROR: Gangware.exe was not created!
    echo Check the build output for errors.
    pause
    exit /b 1
)

echo.
echo ========================================
echo    Build completed successfully!
echo ========================================
echo.
echo Executable created: dist\Gangware.exe
echo.

:: Get file size
for %%A in ("dist\Gangware.exe") do set size=%%~zA
set /a sizeInMB=size/1024/1024
echo File size: %sizeInMB% MB
echo.

:: Test the executable
echo Testing the executable...
echo Starting Gangware.exe for 3 seconds...
timeout /t 2 /nobreak >nul
start "" "dist\Gangware.exe"
timeout /t 3 /nobreak >nul
taskkill /f /im "Gangware.exe" >nul 2>&1

echo.
echo Build process complete!
echo.
echo To distribute:
echo 1. Copy the entire 'dist' folder
echo 2. Make sure users have Windows Defender/antivirus exceptions set
echo 3. Consider code signing for wider distribution
echo.
pause
