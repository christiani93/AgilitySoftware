@echo off
chcp 65001 >nul
title Agility Web-App (DEBUG)
echo === DEBUG-START ===

if not exist "flask_env\Scripts\activate.bat" (
  echo [FEHLER] venv nicht gefunden: flask_env\Scripts\activate.bat
  echo Bitte erst das Hauptskript ausführen, damit das venv angelegt wird.
  pause
  exit /b 1
)

call flask_env\Scripts\activate.bat
set APP_RELOAD=0
set APP_DEBUG=1
set PYTHONIOENCODING=UTF-8

echo Starte app.py ohne Reloader ...
python app.py
echo === Prozess beendet (Exitcode %ERRORLEVEL%) ===
pause
