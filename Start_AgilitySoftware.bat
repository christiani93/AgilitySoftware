@echo off
setlocal EnableExtensions EnableDelayedExpansion

echo ============================================
echo   AgilitySoftware - Hauptsystem starten
echo   (Autoupdate + Web-App + Browser)
echo ============================================
echo.

REM ------------------------------------------------
REM 1) Zum Projekt-Root wechseln (Ordner dieser BAT-Datei)
REM ------------------------------------------------
cd /d "%~dp0"

REM ------------------------------------------------
REM 2) Autoupdate per git (falls Repo geklont ist)
REM ------------------------------------------------
if exist ".git" (
  echo [UPDATE] Hole aktuelle Version von GitHub...
  git pull
) else (
  echo [UPDATE] Kein .git-Ordner gefunden - Autoupdate wird uebersprungen.
)

REM ------------------------------------------------
REM 3) In web_app wechseln
REM ------------------------------------------------
if not exist "web_app" (
  echo FEHLER: Ordner "web_app" wurde nicht gefunden!
  echo Erwarteter Pfad: %CD%\web_app
  pause
  exit /b 1
)

cd web_app

if not exist "app.py" (
  echo FEHLER: app.py wurde nicht gefunden!
  echo Erwarteter Pfad: %CD%\app.py
  pause
  exit /b 1
)

REM ------------------------------------------------
REM 4) Virtuelle Umgebung fuer Web-App pruefen/erstellen
REM ------------------------------------------------
echo [WEB] Pruefe virtuelle Umgebung "flask_env"...

if not exist "flask_env\Scripts\python.exe" (
  echo [WEB] Erstelle neue virtuelle Umgebung...
  py -3 -m venv flask_env
)

if not exist "flask_env\Scripts\activate.bat" (
  echo [WEB] venv scheint defekt - baue neu...
  rmdir /s /q flask_env
  py -3 -m venv flask_env
)

call flask_env\Scripts\activate.bat
if errorlevel 1 (
  echo FEHLER: Konnte flask_env nicht aktivieren.
  pause
  exit /b 1
)

REM ------------------------------------------------
REM 5) Abhaengigkeiten aktualisieren
REM ------------------------------------------------
echo [WEB] Aktualisiere Python-Pakete...
python -m pip install --upgrade pip

if exist requirements.txt (
  echo [WEB] Installiere Pakete aus requirements.txt...
  python -m pip install -r requirements.txt
) else (
  echo [WEB] Keine requirements.txt gefunden – installiere Basis-Pakete...
  python -m pip install flask flask-socketio requests pywin32
)

REM ------------------------------------------------
REM 6) Web-App in neuem Fenster starten
REM ------------------------------------------------
echo [WEB] Starte Web-App auf Port 5000...

set "CURDIR=%CD%"

start "Agility Web" cmd /k "cd /d \"%CURDIR%\" & call flask_env\Scripts\activate.bat & python app.py & echo. & echo [WEB] Flask wurde beendet. & pause"

REM ------------------------------------------------
REM 7) Browser auf localhost:5000 oeffnen
REM ------------------------------------------------
echo [WEB] Oeffne Browser auf http://localhost:5000 ...
start "" "http://localhost:5000"

echo.
echo ============================================
echo   Hauptsystem wurde gestartet.
echo   Falls keine Seite erscheint:
echo   - Pruefe das Fenster "Agility Web" auf Fehler.
echo ============================================
echo.
pause

endlocal
exit /b 0
