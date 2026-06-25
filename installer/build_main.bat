@echo off
setlocal EnableExtensions EnableDelayedExpansion
title AgilitySoftware - Build (Hauptserver)

REM Build-Skript für AgilitySoftware.exe (Hauptserver).
REM Nutzt die 64-bit venv 'flask_env' (Junction auf %USERPROFILE%\.venvs\AgilitySoftware\flask_env).
REM
REM Build laeuft AUSSERHALB OneDrive (in %LOCALAPPDATA%\AgilityBuild), die fertige
REM EXE wird danach nach <Projekt>\dist\ zurueckkopiert. So vermeiden wir, dass
REM OneDrive waehrend des Builds tausende Temp-Files synchronisiert.

cd /d "%~dp0\.."
set "PROJECT_ROOT=%CD%"
set "VENV=%PROJECT_ROOT%\web_app\flask_env"
set "BUILD_BASE=%LOCALAPPDATA%\AgilityBuild\main"
set "DIST_FINAL=%PROJECT_ROOT%\dist"

if not exist "%VENV%\Scripts\python.exe" (
    echo FEHLER: venv flask_env wurde nicht gefunden:
    echo   %VENV%
    pause
    exit /b 1
)

echo ============================================
echo   Build AgilitySoftware.exe (64-bit)
echo   Build-Pfad: %BUILD_BASE%
echo   Output:     %DIST_FINAL%\AgilitySoftware.exe
echo ============================================
echo.

if not exist "%BUILD_BASE%" mkdir "%BUILD_BASE%"
if not exist "%DIST_FINAL%" mkdir "%DIST_FINAL%"

call "%VENV%\Scripts\activate.bat"
if errorlevel 1 (
    echo FEHLER: Konnte flask_env nicht aktivieren.
    pause
    exit /b 1
)

python -m pip install --upgrade pip
python -m pip install pyinstaller

echo.
echo [PyInstaller] Baue (Output ausserhalb OneDrive)...
pyinstaller installer\AgilitySoftware.spec --noconfirm --clean ^
  --distpath "%BUILD_BASE%\dist" ^
  --workpath "%BUILD_BASE%\build"

if errorlevel 1 (
    echo.
    echo FEHLER: Build fehlgeschlagen.
    pause
    exit /b 1
)

echo.
echo [Copy] Verschiebe EXE nach %DIST_FINAL% ...
copy /Y "%BUILD_BASE%\dist\AgilitySoftware.exe" "%DIST_FINAL%\AgilitySoftware.exe" >nul
if errorlevel 1 (
    echo FEHLER: Konnte EXE nicht kopieren.
    pause
    exit /b 1
)

echo.
echo ============================================
echo   ERFOLG: %DIST_FINAL%\AgilitySoftware.exe
echo ============================================
echo.
echo Hinweis: data\ liegt NICHT im EXE - die EXE legt data\ neben sich
echo selbst an. Fuer NAS-Daten: set AGILITY_DATA_DIR=\\NAS\path
echo.
pause
endlocal
exit /b 0
