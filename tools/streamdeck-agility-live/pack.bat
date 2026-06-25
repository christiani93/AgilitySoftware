@echo off
setlocal

echo.
echo ============================================
echo  Agility Live - Plugin packen (.streamDeckPlugin)
echo ============================================
echo.

set "PLUGIN_SRC=%~dp0tech.z-b.agility-live.sdPlugin"
set "TMP_ZIP=%~dp0tech.z-b.agility-live.zip"
set "OUT_ZIP=%~dp0tech.z-b.agility-live.streamDeckPlugin"

if not exist "%PLUGIN_SRC%" (
    echo FEHLER: Plugin-Ordner nicht gefunden:
    echo   %PLUGIN_SRC%
    goto :end
)

if exist "%TMP_ZIP%" del "%TMP_ZIP%"
if exist "%OUT_ZIP%" del "%OUT_ZIP%"

REM Plugin-Ordner inkl. Wrapper packen (Stream-Deck erwartet 'XXX.sdPlugin\'
REM als Top-Level-Verzeichnis im ZIP, nicht direkt manifest.json)
echo Packe %PLUGIN_SRC% nach %TMP_ZIP% ...
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
    "Compress-Archive -Path '%PLUGIN_SRC%' -DestinationPath '%TMP_ZIP%' -Force"

if not exist "%TMP_ZIP%" (
    echo FEHLER: Pack fehlgeschlagen.
    goto :end
)

REM .zip -> .streamDeckPlugin (Stream Deck App erkennt die Extension)
ren "%TMP_ZIP%" "tech.z-b.agility-live.streamDeckPlugin"

if not exist "%OUT_ZIP%" (
    echo FEHLER: Umbenennen fehlgeschlagen.
    goto :end
)

echo.
echo ============================================
echo  Fertig: %OUT_ZIP%
echo ============================================
echo.
echo Auf dem Ziel-PC: Doppelklick auf die .streamDeckPlugin-Datei
echo  -^> Stream Deck App fragt nach Installation, fertig.
echo.
echo Alternative: install.bat im gleichen Ordner direkt ausfuehren.
echo.

:end
pause
endlocal
