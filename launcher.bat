@echo off
setlocal

title Field Photo to KMZ Studio
cd /d "%~dp0"

set "EXIF_ARG="
if exist "%~dp0exiftool.exe" set "EXIF_ARG=--exiftool ""%~dp0exiftool.exe"""
if exist "%~dp0exiftool\exiftool.exe" set "EXIF_ARG=--exiftool ""%~dp0exiftool\exiftool.exe"""

if exist "%~dp0.venv\Scripts\pythonw.exe" (
    "%~dp0.venv\Scripts\pythonw.exe" "%~dp0drone_images_to_kmz.py" --gui %EXIF_ARG%
    exit /b %errorlevel%
)

if exist "%~dp0.venv\Scripts\python.exe" (
    "%~dp0.venv\Scripts\python.exe" "%~dp0drone_images_to_kmz.py" --gui %EXIF_ARG%
    exit /b %errorlevel%
)

pyw -3 "%~dp0drone_images_to_kmz.py" --gui %EXIF_ARG% >nul 2>&1
if not errorlevel 1 exit /b 0

pythonw "%~dp0drone_images_to_kmz.py" --gui %EXIF_ARG% >nul 2>&1
if not errorlevel 1 exit /b 0

py -3 "%~dp0drone_images_to_kmz.py" --gui %EXIF_ARG%
if not errorlevel 1 exit /b 0

python "%~dp0drone_images_to_kmz.py" --gui %EXIF_ARG%
if not errorlevel 1 exit /b 0

echo Python was not found.
echo Install Python 3 and make sure the Python launcher is available.
pause
exit /b 1
