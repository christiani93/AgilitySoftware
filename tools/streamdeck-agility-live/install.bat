@echo off
setlocal

echo.
echo ============================================
echo  Agility Live - Stream Deck Plugin Setup
echo ============================================
echo.
echo Taste druecken um zu starten...
pause > nul

set "PLUGIN_SRC=%~dp0tech.z-b.agility-live.sdPlugin"
set "PLUGIN_DST=%APPDATA%\Elgato\StreamDeck\Plugins\tech.z-b.agility-live.sdPlugin"

echo Quelle: %PLUGIN_SRC%
echo Ziel:   %PLUGIN_DST%
echo.

if not exist "%PLUGIN_SRC%" (
    echo FEHLER: Plugin-Quellordner nicht gefunden:
    echo   %PLUGIN_SRC%
    goto :end
)

REM --- Stream Deck beenden ----------------------------------------------------
echo [1/3] Stream Deck wird beendet (falls laufend)...
taskkill /IM "StreamDeck.exe" /F >nul 2>&1
ping -n 4 127.0.0.1 >nul

REM --- Alte Installation entfernen --------------------------------------------
if exist "%PLUGIN_DST%" (
    echo Alte Plugin-Version wird entfernt...
    rd /s /q "%PLUGIN_DST%"
)

REM --- Plugin kopieren --------------------------------------------------------
echo [2/3] Plugin wird kopiert...
robocopy "%PLUGIN_SRC%" "%PLUGIN_DST%" /E /NFL /NDL /NJH /NJS /nc /ns /np
if %errorlevel% geq 8 (
    echo.
    echo FEHLER: Kopieren fehlgeschlagen!
    echo Tipp: Stream Deck App schliessen und Skript erneut ausfuehren.
    goto :end
)

REM --- Stream Deck starten ----------------------------------------------------
echo [3/3] Stream Deck wird gestartet...
if exist "%PROGRAMFILES%\Elgato\StreamDeck\StreamDeck.exe" (
    start "" "%PROGRAMFILES%\Elgato\StreamDeck\StreamDeck.exe"
) else if exist "%PROGRAMFILES(X86)%\Elgato\StreamDeck\StreamDeck.exe" (
    start "" "%PROGRAMFILES(X86)%\Elgato\StreamDeck\StreamDeck.exe"
) else if exist "%LOCALAPPDATA%\Programs\StreamDeck\StreamDeck.exe" (
    start "" "%LOCALAPPDATA%\Programs\StreamDeck\StreamDeck.exe"
) else (
    echo Stream Deck nicht gefunden - bitte manuell starten.
)

echo.
echo ============================================
echo  Installation abgeschlossen!
echo ============================================
echo.
echo Naechste Schritte:
echo  1. Stream Deck App oeffnen
echo  2. In der Plugin-Liste links: Kategorie "Agility" auswaehlen
echo  3. Aktion "Verbindung ^& Ring" auf einen Button ziehen
echo  4. Property Inspector oeffnen, Host/Port/Ring eintragen
echo  5. Aktionen "Startfreigabe" / "Fehler" / "Verweigerung"
echo     auf weitere Buttons ziehen - fertig.
echo.
echo  Hauptserver:   Host = localhost, Port = 5000
echo  Ring-PC:       Host = IP des Hauptservers, Port = 5001-5003
echo.

:end
echo.
pause
endlocal
