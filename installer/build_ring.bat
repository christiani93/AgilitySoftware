@echo off
setlocal EnableExtensions EnableDelayedExpansion
title AgilityRing - Build (Ring-Server)

REM Build-Skript für AgilityRing.exe (Ring-Server, 32-bit, TIMY-fähig).
REM Nutzt die 32-bit venv 'ring_env' (Junction auf %USERPROFILE%\.venvs\AgilitySoftware\ring_env).
REM Build läuft AUSSERHALB OneDrive in %LOCALAPPDATA%\AgilityBuild.

cd /d "%~dp0\.."
set "PROJECT_ROOT=%CD%"
set "VENV=%PROJECT_ROOT%\web_app\ring_env"
set "BUILD_BASE=%LOCALAPPDATA%\AgilityBuild\ring"
set "DIST_FINAL=%PROJECT_ROOT%\dist"

if not exist "%VENV%\Scripts\python.exe" (
    echo FEHLER: 32-bit venv ring_env wurde nicht gefunden:
    echo   %VENV%
    pause
    exit /b 1
)

echo ============================================
echo   Build AgilityRing.exe (32-bit, TIMY-fähig)
echo   Build-Pfad: %BUILD_BASE%
echo   Output:     %DIST_FINAL%\AgilityRing.exe
echo ============================================
echo.

if not exist "%BUILD_BASE%" mkdir "%BUILD_BASE%"
if not exist "%DIST_FINAL%" mkdir "%DIST_FINAL%"

call "%VENV%\Scripts\activate.bat"
if errorlevel 1 (
    echo FEHLER: Konnte ring_env nicht aktivieren.
    pause
    exit /b 1
)

python -c "import struct,sys; print(f'Python {sys.version.split()[0]} - {struct.calcsize(chr(80))*8}-bit')"
python -m pip install --upgrade pip
python -m pip install pyinstaller flask flask-socketio requests pywin32

echo.
echo [PyInstaller] Baue (Output ausserhalb OneDrive)...
pyinstaller installer\AgilityRing.spec --noconfirm --clean ^
  --distpath "%BUILD_BASE%\dist" ^
  --workpath "%BUILD_BASE%\build"

if errorlevel 1 (
    echo FEHLER: Build fehlgeschlagen.
    pause
    exit /b 1
)

echo.
echo [Copy] Verschiebe EXE nach %DIST_FINAL% ...
copy /Y "%BUILD_BASE%\dist\AgilityRing.exe" "%DIST_FINAL%\AgilityRing.exe" >nul
if errorlevel 1 (
    echo FEHLER: Konnte EXE nicht kopieren.
    pause
    exit /b 1
)

echo.
echo ============================================
echo   ERFOLG: %DIST_FINAL%\AgilityRing.exe
echo ============================================
echo.
echo Verteilung:
echo  - AgilityRing.exe auf jeden Ring-PC kopieren.
echo  - Beim ersten Start: Ring-Nr (1/2/3) + Server-IP eingeben.
echo  - Wird in ring_config.json neben der EXE gespeichert.
echo.
pause
endlocal
exit /b 0
