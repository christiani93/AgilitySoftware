@echo off
setlocal ENABLEDELAYEDEXPANSION

REM ========= Konfiguration =========
set "PYTHON_32=C:\Users\chris\AppData\Local\Programs\Python\Python313-32\python.exe"
set "VENV_NAME=ring_server_env_32bit"
set "RING_LABEL=Ring 1"
set "RING_PORT=5001"
REM =================================

echo --- Einrichtung fuer %RING_LABEL% ---

if not exist "%PYTHON_32%" (
  echo FEHLER: Python 32-bit nicht gefunden: %PYTHON_32%
  pause
  exit /b 1
)

if not exist "%VENV_NAME%\Scripts\python.exe" (
  echo Erstelle neue 32-bit venv...
  "%PYTHON_32%" -m venv "%VENV_NAME%"
)

call "%VENV_NAME%\Scripts\activate.bat"
if errorlevel 1 (
  echo FEHLER: venv konnte nicht aktiviert werden.
  pause
  exit /b 1
)

echo Aktualisiere pip in der 32-bit venv...
python -m pip install --upgrade pip

echo Installiere/aktualisiere Abhaengigkeiten...
python -m pip install flask flask-socketio requests pywin32

echo Starte Ring-Server fuer %RING_LABEL% auf Port %RING_PORT% ...
python ring_server.py --ring "%RING_LABEL%" --port %RING_PORT%

endlocal
pause
