@echo off
setlocal EnableExtensions EnableDelayedExpansion

echo ============================================
echo   AgilitySoftware - Ring (DEV, GUI)
echo   Startet den Ring-Launcher wie die EXE:
echo   Tk-Konfig-Dialog + Ring-Dashboard-Fenster
echo   - aus dem Quellcode ueber die Dev-venv,
echo   ohne EXE-Build. Code-Aenderungen greifen
echo   nach einem Neustart dieser Bat.
echo ============================================
echo.

REM Fester Pfad zu Python 32-bit (TIMY/pywin32 brauchen 32-bit)
set "PY32=C:\Users\chris\AppData\Local\Programs\Python\Python313-32\python.exe"

cd /d "%~dp0"

REM DEV-Ring: crashguard aus (kein Reporting aus der Entwicklungsumgebung)
set CRASHGUARD_DISABLE=1

if not exist "web_app\ring_server\ring_launcher.py" (
  echo FEHLER: web_app\ring_server\ring_launcher.py wurde nicht gefunden.
  echo Pfad: %CD%\web_app\ring_server\ring_launcher.py
  pause
  exit /b 1
)

if not exist "%PY32%" (
  echo FEHLER: Python 32-bit wurde nicht gefunden:
  echo   %PY32%
  pause
  exit /b 1
)

cd web_app

set "RING_ENV_DIR=%CD%\ring_env"
set "RING_ENV_PY=%RING_ENV_DIR%\Scripts\python.exe"

if not exist "%RING_ENV_PY%" (
  echo [RING-DEV] Erstelle neue 32-bit venv in ring_env ...
  "%PY32%" -m venv "%RING_ENV_DIR%"
)

if not exist "%RING_ENV_PY%" (
  echo FEHLER: ring_env konnte nicht erstellt werden.
  pause
  exit /b 1
)

echo [RING-DEV] Aktualisiere Pakete in ring_env ...
"%RING_ENV_PY%" -m pip install --upgrade pip
"%RING_ENV_PY%" -m pip install flask flask-socketio requests pywin32

echo.
echo [RING-DEV] Starte Ring-Launcher (GUI) ...
echo --- Fenster schliessen oder STRG+C zum Beenden. ---
echo.

cd ring_server
"%RING_ENV_PY%" ring_launcher.py

echo.
echo [RING-DEV] Ring-Launcher wurde beendet.
pause
endlocal
exit /b 0
