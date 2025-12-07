@echo off
setlocal

REM In den Ordner wechseln, in dem diese BAT-Datei liegt
cd /d "%~dp0"

echo Aktiviere virtuelle Umgebung...
call "flask_env\Scripts\activate.bat"

echo Starte Pytest...
pytest -q

echo.
echo Tests abgeschlossen. Druecken Sie eine Taste, um dieses Fenster zu schliessen.
pause

endlocal
