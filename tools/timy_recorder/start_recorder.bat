@echo off
setlocal EnableExtensions
title TIMY-Recorder (standalone)

REM Startet den eigenstaendigen TIMY-Recorder im 32-bit 'ring_env' (pywin32/ALGE-USB).
REM Zeichnet neben timy_recorder.py eine .log (Rohdaten + Berechnung) und eine .csv
REM (ein Lauf pro Zeile, inkl. Start-Intervall) auf.
REM
REM Aufruf:   start_recorder.bat               -> Ring-Label "Ring 1"
REM           start_recorder.bat "Ring 2"      -> Ring-Label "Ring 2"

cd /d "%~dp0"
set "VENV=%~dp0..\..\web_app\ring_env"
set "RING=%~1"
if "%RING%"=="" set "RING=Ring 1"

if not exist "%VENV%\Scripts\python.exe" (
    echo FEHLER: 32-bit venv ring_env nicht gefunden:
    echo   %VENV%
    echo Entweder ring_env einrichten oder ohne Hardware testen:
    echo   python timy_recorder.py --simulate
    pause
    exit /b 1
)

call "%VENV%\Scripts\activate.bat"
python -c "import struct,sys; print('Python', sys.version.split()[0], struct.calcsize('P')*8, 'bit')"

echo ============================================
echo   TIMY-Recorder  —  Ring: %RING%
echo   Strg+C beendet die Aufzeichnung.
echo ============================================
python "%~dp0timy_recorder.py" --ring "%RING%"

echo.
echo Aufzeichnung beendet. Dateien liegen in:
echo   %~dp0
pause
endlocal
