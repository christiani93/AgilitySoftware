@echo off
echo ================================
echo  Ring 1 DEV - Minimalstart
echo ================================
echo.

REM 1) In den ring_server-Ordner wechseln
cd /d "C:\Users\chris\OneDrive\Dokumente\AgilitySoftware\web_app\ring_server"

if not exist "ring_server.py" (
  echo FEHLER: ring_server.py nicht gefunden!
  echo Erwarteter Pfad: %CD%\ring_server.py
  pause
  exit /b 1
)

REM 2) Ring-Server direkt mit 32-bit Python starten
echo Starte Ring-Server mit Python 32-bit...
"C:\Users\chris\AppData\Local\Programs\Python\Python313-32\python.exe" ring_server.py --ring "Ring 1" --port 5001

echo.
echo Ring-Server wurde beendet.
pause
