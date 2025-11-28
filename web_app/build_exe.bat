@echo off
setlocal

:: ====================================================================================
:: AgilitySoftware Build-Skript
::
:: Dieses Skript erstellt eine einzelne .exe-Datei aus Ihrer Flask-Anwendung.
:: WICHTIG: Führen Sie zuerst start_dev.bat aus, um sicherzustellen,
:: dass alle Module in der virtuellen Umgebung installiert sind.
:: ====================================================================================

:: Name der Haupt-Python-Datei
set "FLASK_APP_FILE=app.py"

:: Name des Ordners der virtuellen Umgebung
set "VENV_NAME=flask_env"

:: Name für die finale .exe-Datei
set "EXE_NAME=AgilitySuite"

:: ====================================================================================

echo.
echo =========================================================
echo Erstelle ausfuehrbare .exe-Datei...
echo =========================================================
echo.

:: Aktiviere die virtuelle Umgebung
call "%VENV_NAME%\Scripts\activate.bat"
if errorlevel 1 (
    echo FEHLER: Konnte die virtuelle Umgebung nicht aktivieren.
    echo Fuehren Sie zuerst 'start_dev.bat' aus.
    pause
    exit /b 1
)

echo Virtuelle Umgebung ist aktiv.
echo.
echo Starte PyInstaller...
echo Dies kann einige Minuten dauern.
echo.

:: PyInstaller-Befehl zum Erstellen einer einzelnen .exe-Datei
:: --onefile: Bündelt alles in eine einzige .exe.
:: --windowed: Versteckt das Konsolenfenster, wenn die .exe gestartet wird.
:: --add-data: Bündelt die 'templates' und 'static' Ordner mit der Anwendung.
::             Das Format ist 'Quelle;Ziel'.
:: --add-data: Bündelt ebenfalls den 'data' Ordner mit.
:: --name: Legt den Namen der finalen .exe fest.

pyinstaller --onefile --windowed --add-data "templates;templates" --add-data "static;static" --add-data "data;data" --name "%EXE_NAME%" "%FLASK_APP_FILE%"

if errorlevel 1 (
    echo.
    echo =========================================================
    echo FEHLER: PyInstaller konnte die .exe-Datei nicht erstellen.
    echo Pruefen Sie die Fehlermeldungen oben.
    echo =========================================================
) else (
    echo.
    echo =========================================================
    echo ERFOLG!
    echo Die Datei '%EXE_NAME%.exe' wurde im 'dist'-Ordner erstellt.
    echo =========================================================
)

echo.
endlocal
pause
