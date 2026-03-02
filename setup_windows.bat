@echo off
setlocal

cd /d "%~dp0"

py -3 --version >nul 2>&1
if errorlevel 1 (
    python --version >nul 2>&1
    if errorlevel 1 (
        echo Python 3 was not found.
        echo Install Python 3, then rerun this setup script.
        pause
        exit /b 1
    )
    set "PYTHON_CMD=python"
) else (
    set "PYTHON_CMD=py -3"
)

%PYTHON_CMD% -m venv .venv
if errorlevel 1 (
    echo Failed to create the virtual environment.
    pause
    exit /b 1
)

call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

if not exist "exiftool\exiftool.exe" (
    if exist "exiftool_bundle.zip" (
        echo Extracting bundled ExifTool...
        powershell -NoProfile -ExecutionPolicy Bypass -Command "Expand-Archive -Path 'exiftool_bundle.zip' -DestinationPath '.' -Force"
    )
)

echo.
echo Setup complete.
echo Run launcher.bat to start the app.
if exist "exiftool\exiftool.exe" (
    echo ExifTool is ready in .\exiftool\exiftool.exe
) else (
    echo ExifTool not found. The app still works, but HEIC and phone metadata support may be reduced.
)
echo.
pause
