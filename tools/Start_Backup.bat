@echo off
setlocal
title AgilitySoftware - events.json Backup (alle 5 Min)

REM ============================================================
REM  Rotierendes Backup der AgilitySoftware-Nutzdaten.
REM  Liest nur -> stoert den laufenden Server (EXE) NICHT.
REM  Standard: EXE-Datenverzeichnis dist\data.
REM  Dieses Fenster offen lassen, solange gesichert werden soll.
REM  Beenden mit Strg+C oder Fenster schliessen.
REM ============================================================

REM Ins Projekt-Hauptverzeichnis wechseln (diese .bat liegt in tools\)
cd /d "%~dp0.."

set "PY=web_app\flask_env\Scripts\python.exe"

if not exist "%PY%" (
  echo FEHLER: Python-Umgebung nicht gefunden: %PY%
  echo Bitte pruefen, ob flask_env existiert.
  pause
  exit /b 1
)

if not exist "dist\data" (
  echo WARNUNG: dist\data existiert nicht - laeuft die EXE schon mindestens einmal?
  echo Starte trotzdem; das Backup legt los, sobald events.json da ist.
)

echo.
echo Starte Backup: dist\data  ->  C:\Users\chris\AgilityBackups\auto
echo Alle 5 Minuten, 24 Staende je Datei. Fenster offen lassen.
echo.

"%PY%" -I tools\backup_events.py --data-dir dist\data %*

echo.
echo Backup-Prozess beendet.
pause
