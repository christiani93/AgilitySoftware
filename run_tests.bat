@echo off
setlocal

REM In den Ordner wechseln, in dem diese BAT-Datei liegt (AgilitySoftware)
cd /d "%~dp0"

REM Jetzt in den web_app-Ordner wechseln, wo app.py und flask_env liegen
cd web_app

echo Aktiviere virtuelle Umgebung...
call "flask_env\Scripts\activate.bat"

echo Starte Pytest...
pytest -q

echo.
echo Tests abgeschlossen. Druecken Sie eine Taste, um dieses Fenster zu schliessen.
pause

endlocal
