@echo off
setlocal

:: =========================================================
:: Timy Raw Data Viewer - Start-Skript
:: Zeigt die unverarbeiteten Daten vom ALGE Timy an.
:: =========================================================

:: ====================================================================
:: KONFIGURATION - BITTE HIER ANPASSEN
:: ====================================================================
:: Trage hier den vollständigen Pfad zu deiner 32-bit python.exe ein.
set "PYTHON_32BIT_EXECUTABLE=C:\Users\chris\AppData\Local\Programs\Python\Python313-32\python.exe"
:: ====================================================================

chcp 65001 > nul
cd /d "%~dp0"

echo --- Timy Raw Data Viewer ---
echo.

:: Prüfen, ob der Python-Pfad existiert
if not exist "%PYTHON_32BIT_EXECUTABLE%" (
    echo FEHLER: Die angegebene Python-Datei wurde nicht gefunden:
    echo %PYTHON_32BIT_EXECUTABLE%
    echo.
    echo Bitte ueberpruefen Sie den Pfad in diesem Skript.
    pause
    exit /b 1
)

set "VENV_NAME=raw_data_viewer_env"

:: Virtuelle Umgebung erstellen/aktivieren
if not exist "%VENV_NAME%\Scripts\activate.bat" (
    echo Erstelle neue virtuelle 32-bit Umgebung...
    "%PYTHON_32BIT_EXECUTABLE%" -m venv "%VENV_NAME%"
    call "%VENV_NAME%\Scripts\activate.bat"
    echo Installiere 'pywin32'...
    pip install pywin32
) else (
    call "%VENV_NAME%\Scripts\activate.bat"
)
echo.

:: Starte das Python-Skript
echo Starte den Raw Data Viewer...
echo (Fenster mit CTRL+C schliessen)
echo =========================================================
python show_raw_data.py

echo.
echo =========================================================
echo Viewer wurde beendet.
echo =========================================================
pause