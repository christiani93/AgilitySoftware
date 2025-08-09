@echo off
setlocal

:: =========================================================
:: Ring-Server Start-Skript (v1.0)
:: =========================================================

:: KONFIGURATION
set "PYTHON_32BIT_EXECUTABLE=C:\Users\chris\AppData\Local\Programs\Python\Python313-32\python.exe"
set "RING_ID=Ring 1"
set "VENV_NAME=ring_server_env_32bit"

echo --- Einrichtung für %RING_ID% ---

if not exist "%PYTHON_32BIT_EXECUTABLE%" (
    echo FEHLER: Python-Pfad nicht gefunden: %PYTHON_32BIT_EXECUTABLE%
    pause
    exit /b 1
)

:: Virtuelle Umgebung erstellen, falls nicht vorhanden
if not exist "%VENV_NAME%\" (
    echo Erstelle neue virtuelle Umgebung...
    "%PYTHON_32BIT_EXECUTABLE%" -m venv "%VENV_NAME%"
    call "%VENV_NAME%\Scripts\activate.bat"
    echo Installiere benötigte Module...
    pip install flask flask-socketio requests pywin32
) else {
    call "%VENV_NAME%\Scripts\activate.bat"
}

:: Starte den Ring-Server
echo Starte den lokalen Server für %RING_ID%...
python ring_server.py "%RING_ID%"

endlocal
pause