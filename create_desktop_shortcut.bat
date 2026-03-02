@echo off
setlocal enabledelayedexpansion

for /f "tokens=3" %%A in ('reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders" /v Desktop') do set "DESKTOP=%%A"
set "APP_DIR=%~dp0"
if "%APP_DIR:~-1%"=="\" set "APP_DIR=%APP_DIR:~0,-1%"
set "ICON_FILE=%APP_DIR%\806app.ico"
set "LAUNCHER_FILE=%APP_DIR%\launch_app.vbs"

echo.
echo ========================================
echo Field Photo to KMZ Studio
echo Desktop Shortcut Creator
echo ========================================
echo.

if not exist "%DESKTOP%" (
    echo ERROR: Desktop path not found.
    pause
    exit /b 1
)

if not exist "%LAUNCHER_FILE%" (
    echo ERROR: launch_app.vbs not found.
    pause
    exit /b 1
)

set "ICON_PATH=%ICON_FILE%"
if not exist "%ICON_FILE%" set "ICON_PATH=C:\Windows\System32\shell32.dll,268"

set "VBS_FILE=%TEMP%\create_drone_to_kmz_shortcut.vbs"

(
echo Set oWS = WScript.CreateObject("WScript.Shell"^)
echo sLinkFile = "%DESKTOP%\Drone to KMZ.lnk"
echo Set oLink = oWS.CreateShortcut(sLinkFile^)
echo oLink.TargetPath = "wscript.exe"
echo oLink.Arguments = """" ^& "%LAUNCHER_FILE%" ^& """"
echo oLink.WorkingDirectory = "%APP_DIR%"
echo oLink.Description = "Field Photo to KMZ Studio"
echo oLink.IconLocation = "%ICON_PATH%"
echo oLink.WindowStyle = 1
echo oLink.Save
echo WScript.Echo "Shortcut created successfully."
) > "%VBS_FILE%"

cscript //nologo "%VBS_FILE%"
del "%VBS_FILE%"

echo.
echo The desktop shortcut is ready:
echo %DESKTOP%\Drone to KMZ.lnk
echo.
pause
