@echo off
setlocal EnableExtensions EnableDelayedExpansion

echo ============================================
echo   AgilitySoftware - Ring 3 (venv)
echo   (Ring-Server + Ring-PC Ansicht)
echo ============================================
echo.

set "SERVER_IP=127.0.0.1"
set "RING_NUMBER=3"
set "RING_LABEL=Ring 3"
set "RING_PORT=5003"
set "PY32=C:\Users\chris\AppData\Local\Programs\Python\Python313-32\python.exe"

cd /d "%~dp0"

if not exist "web_app" (
  echo FEHLER: Ordner web_app wurde nicht gefunden.
  echo Pfad: %CD%\web_app
  pause
  exit /b 1
)

cd web_app

if not exist "ring_server\ring_server.py" (
  echo FEHLER: ring_server\ring_server.py wurde nicht gefunden.
  echo Pfad: %CD%\ring_server\ring_server.py
  pause
  exit /b 1
)

if not exist "%PY32%" (
  echo FEHLER: Python 32-bit wurde nicht gefunden:
  echo   %PY32%
  pause
  exit /b 1
)

echo [RING3] Verwende Python 32-bit: %PY32%
echo [RING3] Pruefe virtuelle Umgebung ring_env ...

set "RING_ENV_DIR=%CD%\ring_env"
set "RING_ENV_PY=%RING_ENV_DIR%\Scripts\python.exe"

if not exist "%RING_ENV_PY%" (
  echo [RING3] Erstelle neue venv in ring_env ...
  "%PY32%" -m venv "%RING_ENV_DIR%"
)

if not exist "%RING_ENV_PY%" (
  echo FEHLER: ring_env konnte nicht erstellt werden.
  pause
  exit /b 1
)

echo [RING3] Aktualisiere Pakete in ring_env ...
"%RING_ENV_PY%" -m pip install --upgrade pip
"%RING_ENV_PY%" -m pip install flask flask-socketio requests pywin32

echo [RING3] Starte Ring-Server "%RING_LABEL%" auf Port %RING_PORT% ...
cd ring_server

echo --- Ring-Server laeuft. Zum Beenden STRG+C druecken. ---

"%RING_ENV_PY%" ring_server.py --ring "%RING_LABEL%" --port %RING_PORT%

echo [RING3] Ring-Server wurde beendet.
pause
endlocal
exit /b 0
