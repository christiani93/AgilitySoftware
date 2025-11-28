@echo off
setlocal EnableExtensions EnableDelayedExpansion

rem ===================== Benutzer-Optionen =====================
set "KEEP_CONSOLE=1"
set "KEEP_CONSOLE_FLAG=K"     rem K = Fenster offen, C = Fenster schliessen
set "CLEAN_MODE=ALWAYS"       rem ALWAYS oder NEVER
set "PIP_NO_CACHE_DIR=1"      rem Pip-Cache deaktivieren

rem ===================== Konfiguration =====================
set "VENV64=flask_env"        rem 64-bit venv für Web-App
set "VENV32=ring_env32"       rem 32-bit venv für Ring_Server
set "FLASK_APP_FILE=app.py"
set "DEFAULT_PKGS64=Flask openpyxl Flask-SocketIO gevent gevent-websocket pywin32 requests"
set "DEFAULT_PKGS32=pyserial"

rem ===================== Setup / Logging =====================
chcp 65001 >nul
cd /d "%~dp0"
set "_LOG=%~dp0start_dev.log"
call :log "=== Start: %DATE% %TIME% ==="
call :log "[INFO] PROJECT_DIR=%CD%"
call :log "[INFO] Git wird NICHT aktualisiert/benutzt."

rem ===================== Python x64 & x86 sicherstellen =====================
set "PY64="
set "PY32="
call :find_python64
call :find_python32

if not defined PY64 (
  call :log "[INFO] Python 64-bit nicht gefunden. Installiere via winget (User, x64, silent)..."
  where winget >nul 2>&1 || ( call :err "winget nicht gefunden. Bitte Python manuell installieren (python.org) und erneut starten." )
  winget install --id Python.Python.3.13 --source winget --scope user --architecture x64 --accept-package-agreements --accept-source-agreements -e --silent
  if errorlevel 1 (
    call :log "[WARN] 3.13 x64 fehlgeschlagen, versuche generisches Python.Python (x64)..."
    winget install --id Python.Python --source winget --scope user --architecture x64 --accept-package-agreements --accept-source-agreements --silent
  )
  call :find_python64
  if not defined PY64 call :err "Python 64-bit konnte nicht installiert/gefunden werden."
) else (
  where winget >nul 2>&1 && (
    call :log "[INFO] Prüfe Upgrade für Python 64-bit (best effort)..."
    winget upgrade --id Python.Python.3.13 --source winget --scope user --architecture x64 --accept-package-agreements --accept-source-agreements -e --silent >nul 2>nul
  )
)

if not defined PY32 (
  call :log "[INFO] Python 32-bit nicht gefunden. Installiere via winget (User, x86, silent)..."
  where winget >nul 2>&1 || ( call :err "winget nicht gefunden. Bitte Python 32-bit manuell installieren und erneut starten." )
  winget install --id Python.Python.3.13 --source winget --scope user --architecture x86 --accept-package-agreements --accept-source-agreements -e --silent
  if errorlevel 1 (
    call :log "[WARN] 3.13 x86 fehlgeschlagen, versuche generisches Python.Python (x86)..."
    winget install --id Python.Python --source winget --scope user --architecture x86 --accept-package-agreements --accept-source-agreements --silent
  )
  call :find_python32
  if not defined PY32 call :err "Python 32-bit konnte nicht installiert/gefunden werden."
) else (
  where winget >nul 2>&1 && (
    call :log "[INFO] Prüfe Upgrade für Python 32-bit (best effort)..."
    winget upgrade --id Python.Python.3.13 --source winget --scope user --architecture x86 --accept-package-agreements --accept-source-agreements -e --silent >nul 2>nul
  )
)

rem ===================== Clean / Temp löschen =====================
if /I "%CLEAN_MODE%"=="ALWAYS" (
  call :log "[CLEAN] Lösche venvs und temporäre Dateien ..."
  2>nul rmdir /s /q "%VENV64%"
  2>nul rmdir /s /q "%VENV32%"
  for /d /r %%D in (__pycache__) do 2>nul rmdir /s /q "%%D"
  for /r %%F in (*.pyc) do 2>nul del /f /q "%%F"
  if exist ".pytest_cache" 2>nul rmdir /s /q ".pytest_cache"
  if exist "build"         2>nul rmdir /s /q "build"
  if exist "dist"          2>nul rmdir /s /q "dist"
  for /r %%S in (*.spec) do 2>nul del /f /q "%%S"
  if exist "%_LOG%"        2>nul del /f /q "%_LOG%"
)

rem ===================== venv (64-bit) für Web-App =====================
call :log "[SCHRITT 1a/5] venv (x64) prüfen: %VENV64%"
call :log "[INFO] Erzeuge venv (x64) ..."
"%PY64%" -m venv "%VENV64%" || ( call :err "venv (x64) Erstellung fehlgeschlagen." )
call "%VENV64%\Scripts\activate.bat" || ( call :err "venv (x64) Aktivierung fehlgeschlagen." )

call :log "[SCHRITT 2a/5] Python/Pip Version (x64)"
python --version
pip --version

call :log "[SCHRITT 3a/5] pip/setuptools/wheel Upgrade (x64)"
if not "%PIP_NO_CACHE_DIR%"=="1" python -m pip cache purge
python -m pip install --upgrade pip setuptools wheel

if exist requirements.txt (
  call :log "[INFO] requirements.txt installieren/aktualisieren (x64)"
  python -m pip install -r requirements.txt --upgrade
) else (
  call :log "[INFO] Keine requirements.txt – installiere Default-Pakete (x64)"
  python -m pip install %DEFAULT_PKGS64%
)

rem ===================== venv (32-bit) für Ring_Server =====================
call :log "[SCHRITT 1b/5] venv (x86) prüfen: %VENV32%"
call :log "[INFO] Erzeuge venv (x86) ..."
"%PY32%" -m venv "%VENV32%" || ( call :err "venv (x86) Erstellung fehlgeschlagen." )
call "%VENV32%\Scripts\activate.bat" || ( call :err "venv (x86) Aktivierung fehlgeschlagen." )

call :log "[SCHRITT 2b/5] Python/Pip Version (x86)"
python --version
pip --version

call :log "[SCHRITT 3b/5] pip/setuptools/wheel Upgrade (x86)"
if not "%PIP_NO_CACHE_DIR%"=="1" python -m pip cache purge
python -m pip install --upgrade pip setuptools wheel

if exist "ring_server\requirements.txt" (
  call :log "[INFO] ring_server\requirements.txt installieren (x86)"
  python -m pip install -r "ring_server\requirements.txt" --upgrade
) else if exist "requirements_ring.txt" (
  call :log "[INFO] requirements_ring.txt installieren (x86)"
  python -m pip install -r "requirements_ring.txt" --upgrade
) else (
  call :log "[INFO] Keine Ring-Requirements – installiere Minimalpakete (x86): pyserial"
  python -m pip install %DEFAULT_PKGS32%
)

if exist "%VENV32%\Scripts\deactivate.bat" call "%VENV32%\Scripts\deactivate.bat"

rem ===================== Optionale Auto-Patches =====================
call :log "[SCHRITT 4/5] Optionale Auto-Patches (apply_fix_*.py) – falls vorhanden (x64)"
call "%VENV64%\Scripts\activate.bat" || ( call :err "venv (x64) Aktivierung fehlgeschlagen." )
set "PATCH_FOUND=0"
for %%F in (apply_fix_*.py) do (
  set "PATCH_FOUND=1"
  call :log "[INFO] Starte Patch-Script: %%F"
  python "%%F"
  if errorlevel 1 (
    call :log "[WARN] Patch fehlgeschlagen und wird übersprungen: %%F"
  )
)
if "x%PATCH_FOUND%"=="x0" call :log "[INFO] Keine apply_fix_*.py gefunden."

REM ===================== Starte Web-App (x64) =====================
call "%VENV64%\Scripts\activate.bat" || ( call :err "venv (x64) Aktivierung vor Start fehlgeschlagen." )

REM /K = Konsole offen lassen, /C = schließen
set "_CMD_SWITCH=/C"
if /I "%KEEP_CONSOLE_FLAG%"=="K" set "_CMD_SWITCH=/K"

REM eigenes Fenster für die Web-App
start "Agility Web-App" cmd %_CMD_SWITCH% /v:on /c call "%VENV64%\Scripts\activate.bat" ^& set FLASK_DEBUG=1 ^& python "app.py"

REM ===================== Starte Ring_Server (x86) =====================
REM Versuche zuerst Unterordner ring_server\ring_server.py, sonst Root ring_server.py
if exist "ring_server\ring_server.py" (
    start "Ring_Server" cmd %_CMD_SWITCH% /v:on /c call "%VENV32%\Scripts\activate.bat" ^& python "ring_server\ring_server.py"
) else if exist "ring_server.py" (
    start "Ring_Server" cmd %_CMD_SWITCH% /v:on /c call "%VENV32%\Scripts\activate.bat" ^& python "ring_server.py"
) else (
    call :log "[INFO] Kein ring_server.py gefunden – überspringe Ring_Server Start."
)

)

call :log "=== Startskript beendet ==="
goto :eof


rem ===================== Hilfs-Labels =====================
:log
rem %~1 = Nachricht
set "_MSG=%~1"
echo %_MSG%
if defined _LOG >>"%_LOG%" echo %_MSG%
goto :eof

:err
rem %~1 = Fehlermeldung
echo [FEHLER] %~1
if defined _LOG >>"%_LOG%" echo [FEHLER] %~1
pause
exit /b 1

:find_python64
set "PY64="
rem Bevorzugt 3.13 x64 in Standard-Userpfad
for %%P in ("%LOCALAPPDATA%\Programs\Python\Python313\python.exe") do (
  if exist "%%~fP" set "PY64=%%~fP"
)
if not defined PY64 (
  rem Fallback: py-Launcher (x64)
  for /f "delims=" %%P in ('where py 2^>nul') do (
    py -3.13-64 -c "import sys;print(sys.executable)" >"%TEMP%\py64.txt" 2>nul
    if exist "%TEMP%\py64.txt" (
      set /p PY64=<"%TEMP%\py64.txt"
      del "%TEMP%\py64.txt" >nul 2>&1
    )
  )
)
if not defined PY64 (
  rem Letzter Fallback: erstes python im PATH
  for /f "delims=" %%P in ('where python 2^>nul') do (
    set "PY64=%%~fP"
    goto :eof
  )
)
goto :eof

:find_python32
set "PY32="
rem Bevorzugt 3.13 x86 in Standard-Userpfad
for %%P in ("%LOCALAPPDATA%\Programs\Python\Python313-32\python.exe") do (
  if exist "%%~fP" set "PY32=%%~fP"
)
if not defined PY32 (
  rem Fallback: py-Launcher (x86)
  for /f "delims=" %%P in ('where py 2^>nul') do (
    py -3.13-32 -c "import sys;print(sys.executable)" >"%TEMP%\py32.txt" 2>nul
    if exist "%TEMP%\py32.txt" (
      set /p PY32=<"%TEMP%\py32.txt"
      del "%TEMP%\py32.txt" >nul 2>&1
    )
  )
)
goto :eof
