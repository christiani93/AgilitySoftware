@echo on
setlocal EnableExtensions EnableDelayedExpansion
title AgilitySoftware Launcher DEBUG
cd /d "%~dp0"
echo SCRIPT=%~f0
echo DP0=%~dp0
echo CD=%CD%
echo.

set "SCRIPT_DIR=%~dp0"
set "IS_UNC=0"
set "ROOT_DIR=%SCRIPT_DIR%"

echo ============================================
echo   AgilitySoftware Launcher - Diagnose
echo ============================================
echo SCRIPT_DIR: %SCRIPT_DIR%
echo Current CD: %CD%

if "%SCRIPT_DIR:~0,2%"=="\\" set "IS_UNC=1"
echo UNC erkannt: %IS_UNC%

if "%IS_UNC%"=="1" (
    echo UNC-Start erkannt. Versuche Mapping auf V: ...
    set "UNC_SHARE=%SCRIPT_DIR%"
    if /i "%UNC_SHARE:~-1%"=="\" set "UNC_SHARE=%UNC_SHARE:~0,-1%"
    echo UNC_SHARE: %UNC_SHARE%

    set "V_STATUS="
    set "V_REMOTE="
    for /f "tokens=1,2,3,*" %%A in ('net use ^| findstr /i "^V:"') do (
        set "V_STATUS=%%A"
        set "V_REMOTE=%%D"
    )

    if not defined V_STATUS (
        echo V: ist frei. Mappe V: -> %UNC_SHARE%
        net use V: "%UNC_SHARE%" /persistent:no >nul 2>&1
        if errorlevel 1 (
            echo FEHLER: Mapping auf V: fehlgeschlagen.
            pause
            exit /b 1
        )
        set "ROOT_DIR=V:\"
    ) else (
        echo V: ist belegt.
        echo V: zeigt auf: %V_REMOTE%
        if /i "%V_REMOTE%"=="%UNC_SHARE%" (
            echo V: zeigt bereits auf das gleiche Share. Verwende V:.
            set "ROOT_DIR=V:\"
        ) else (
            echo FEHLER: V: ist belegt und zeigt auf ein anderes Share.
            echo Bitte V: freigeben oder Launcher lokal starten.
            pause
            exit /b 1
        )
    )
) else (
    echo Kein UNC-Start erkannt.
)

echo ROOT_DIR: %ROOT_DIR%
cd /d "%ROOT_DIR%"
if errorlevel 1 (
    echo FEHLER: Konnte nicht in ROOT_DIR wechseln.
    pause
    exit /b 1
)
echo Aktuelles CD nach Wechsel: %CD%
echo.
pause

:menu
cls
echo ============================================
echo        AgilitySoftware - Launcher
echo ============================================
echo.
echo  [1] Hauptsystem starten      (Start_AgilitySoftware.bat)
echo  [2] Ring 1 starten           (Start_Ring_1.bat)
echo  [3] Ring 2 starten           (Start_Ring_2.bat)
echo  [4] Ring 3 starten           (Start_Ring_3.bat)
echo  [5] Alle Ringe starten       (1, 2, 3 nacheinander)
echo  [D] Ring-DEV starten         (Start_Ring_dev.bat, eigenes Fenster)
echo  [S] Server-IP setzen und Ring-Skripte neu erzeugen
echo  [C] Python-Check
echo  [Q] Beenden
echo.
choice /c 12345DSCQ /n /m "Auswahl: "

set "opt=%errorlevel%"

if "%opt%"=="1" goto main
if "%opt%"=="2" goto ring1
if "%opt%"=="3" goto ring2
if "%opt%"=="4" goto ring3
if "%opt%"=="5" goto all_rings
if "%opt%"=="6" goto dev_ring
if "%opt%"=="7" goto setup_rings
if "%opt%"=="8" goto check_python
if "%opt%"=="9" goto quit

goto menu

:main
cls
echo ============================================
echo   Hauptsystem starten
echo ============================================
echo.
if exist "%ROOT_DIR%Start_AgilitySoftware.bat" (
    echo Starte Hauptsystem in eigenem Fenster...
    echo.
    start "Agility Main" cmd /k "cd /d \"%ROOT_DIR%\" && \"%ROOT_DIR%Start_AgilitySoftware.bat\""
) else (
    echo FEHLER: Start_AgilitySoftware.bat nicht gefunden.
)
echo.
pause
goto menu

:ring1
if exist "%ROOT_DIR%Start_Ring_1.bat" (
    echo Starte Ring 1...
    start "Ring 1" cmd /k "cd /d \"%ROOT_DIR%\" && \"%ROOT_DIR%Start_Ring_1.bat\""
) else (
    echo FEHLER: Start_Ring_1.bat nicht gefunden.
    echo Tipp: Im Launcher Option [S] ausfuehren, um die Skripte zu erzeugen.
)
pause
goto menu

:ring2
if exist "%ROOT_DIR%Start_Ring_2.bat" (
    echo Starte Ring 2...
    start "Ring 2" cmd /k "cd /d \"%ROOT_DIR%\" && \"%ROOT_DIR%Start_Ring_2.bat\""
) else (
    echo FEHLER: Start_Ring_2.bat nicht gefunden.
    echo Tipp: Im Launcher Option [S] ausfuehren, um die Skripte zu erzeugen.
)
pause
goto menu

:ring3
if exist "%ROOT_DIR%Start_Ring_3.bat" (
    echo Starte Ring 3...
    start "Ring 3" cmd /k "cd /d \"%ROOT_DIR%\" && \"%ROOT_DIR%Start_Ring_3.bat\""
) else (
    echo FEHLER: Start_Ring_3.bat nicht gefunden.
    echo Tipp: Im Launcher Option [S] ausfuehren, um die Skripte zu erzeugen.
)
pause
goto menu

:all_rings
echo Starte alle Ringe (1-3)...
if exist "%ROOT_DIR%Start_Ring_1.bat" start "Ring 1" cmd /k "cd /d \"%ROOT_DIR%\" && \"%ROOT_DIR%Start_Ring_1.bat\""
if exist "%ROOT_DIR%Start_Ring_2.bat" start "Ring 2" cmd /k "cd /d \"%ROOT_DIR%\" && \"%ROOT_DIR%Start_Ring_2.bat\""
if exist "%ROOT_DIR%Start_Ring_3.bat" start "Ring 3" cmd /k "cd /d \"%ROOT_DIR%\" && \"%ROOT_DIR%Start_Ring_3.bat\""
echo Alle vorhandenen Ring-Skripte wurden gestartet (sofern vorhanden).
pause
goto menu

:dev_ring
cls
echo ============================================
echo   DEV-Ring (Start_Ring_dev.bat)
echo ============================================
echo.
if exist "%ROOT_DIR%Start_Ring_dev.bat" (
    echo Starte DEV-Ring in eigenem Fenster...
    echo.
    start "Ring DEV" cmd /k "cd /d \"%ROOT_DIR%\" && \"%ROOT_DIR%Start_Ring_dev.bat\""
) else (
    echo FEHLER: Start_Ring_dev.bat nicht gefunden.
)
echo.
pause
goto menu

:setup_rings
cls
echo ============================================
echo   Server-IP setzen und Ring-Skripte erzeugen
echo ============================================
echo.
echo Aktuelle Empfehlung:
echo  - DEV: 127.0.0.1
echo  - PROD: IP des Server-PCs (z.B. 192.168.0.10)
echo.
set "SERVER_IP="
set /p SERVER_IP=Bitte IP des Servers eingeben (Enter = 127.0.0.1): 

if "%SERVER_IP%"=="" set "SERVER_IP=127.0.0.1"

echo.
echo Verwende Server-IP: %SERVER_IP%
echo.
echo ACHTUNG: Start_Ring_1.bat, Start_Ring_2.bat, Start_Ring_3.bat
echo werden jetzt NEU erzeugt (ueberschrieben).
echo.
pause

call :write_ring_script 1 5001
call :write_ring_script 2 5002
call :write_ring_script 3 5003

echo.
echo Ring-Skripte wurden erzeugt/aktualisiert.
pause
goto menu

:write_ring_script
set "RING_NO=%1"
set "RING_PORT=%2"
set "RING_FILE=%ROOT_DIR%Start_Ring_%RING_NO%.bat"

(
echo @echo off
echo setlocal EnableExtensions EnableDelayedExpansion
echo.
echo echo ============================================
echo echo   AgilitySoftware - Ring %RING_NO% ^(venv^)
echo echo   ^(Ring-Server + Ring-PC Ansicht^)
echo echo ============================================
echo echo.
echo.
echo set "SERVER_IP=%SERVER_IP%"
echo set "RING_NUMBER=%RING_NO%"
echo set "RING_LABEL=Ring %RING_NO%"
echo set "RING_PORT=%RING_PORT%"
echo set "PY32=C:\Users\chris\AppData\Local\Programs\Python\Python313-32\python.exe"
echo.
echo cd /d "%%~dp0"
echo.
echo if not exist "web_app" ^(
echo   echo FEHLER: Ordner web_app wurde nicht gefunden.
echo   echo Pfad: %%CD%%\web_app
echo   pause
echo   exit /b 1
echo ^)
echo.
echo cd web_app
echo.
echo if not exist "ring_server\ring_server.py" ^(
echo   echo FEHLER: ring_server\ring_server.py wurde nicht gefunden.
echo   echo Pfad: %%CD%%\ring_server\ring_server.py
echo   pause
echo   exit /b 1
echo ^)
echo.
echo if not exist "%%PY32%%" ^(
echo   echo FEHLER: Python 32-bit wurde nicht gefunden:
echo   echo   %%PY32%%
echo   pause
echo   exit /b 1
echo ^)
echo.
echo echo [RING%RING_NO%] Verwende Python 32-bit: %%PY32%%
echo echo [RING%RING_NO%] Pruefe virtuelle Umgebung ring_env ...
echo.
echo set "RING_ENV_DIR=%%CD%%\ring_env"
echo set "RING_ENV_PY=%%RING_ENV_DIR%%\Scripts\python.exe"
echo.
echo if not exist "%%RING_ENV_PY%%" ^(
echo   echo [RING%RING_NO%] Erstelle neue venv in ring_env ...
echo   "%%PY32%%" -m venv "%%RING_ENV_DIR%%"
echo ^)
echo.
echo if not exist "%%RING_ENV_PY%%" ^(
echo   echo FEHLER: ring_env konnte nicht erstellt werden.
echo   pause
echo   exit /b 1
echo ^)
echo.
echo echo [RING%RING_NO%] Aktualisiere Pakete in ring_env ...
echo "%%RING_ENV_PY%%" -m pip install --upgrade pip
echo "%%RING_ENV_PY%%" -m pip install flask flask-socketio requests pywin32
echo.
echo echo [RING%RING_NO%] Starte Ring-Server "%%RING_LABEL%%" auf Port %%RING_PORT%% ...
echo cd ring_server
echo.
echo echo --- Ring-Server laeuft. Zum Beenden STRG+C druecken. ---
echo.
echo "%%RING_ENV_PY%%" ring_server.py --ring "%%RING_LABEL%%" --port %%RING_PORT%%
echo.
echo echo [RING%RING_NO%] Ring-Server wurde beendet.
echo pause
echo endlocal
echo exit /b 0
) > "%RING_FILE%"

goto :eof

:check_python
cls
echo ============================================
echo   Python-Check
echo ============================================
echo.

echo [WEB] Pruefe "py" (Launcher fuer 64-bit Python)...
where py 2^>nul
if errorlevel 1 (
    echo   -> py wurde NICHT gefunden.
) else (
    echo   -> py ist vorhanden.
)

echo.
echo [RING] Pruefe Python 32-bit fuer Timy...
set "PY32=C:\Users\chris\AppData\Local\Programs\Python\Python313-32\python.exe"
if exist "%PY32%" (
    echo   -> 32-bit Python gefunden:
    echo      %PY32%
) else (
    echo   -> 32-bit Python wurde NICHT gefunden.
    echo      Bitte Python 3.13 32-bit installieren und Pfad anpassen.
)

echo.
echo Hinweis:
echo  - Web-App nutzt "py -3" ueber Start_AgilitySoftware.bat
echo  - Ring-Server nutzen "%PY32%" in den generierten Start_Ring_*.bat
echo.
pause
goto menu

:quit
endlocal
echo Launcher beendet.
pause
exit /b 0
