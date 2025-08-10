@echo off
setlocal ENABLEDELAYEDEXPANSION

:: ============================================================================
:: AgilitySoftware – Startskript (Auto-Update + Dev-Start)
:: Tested on: Windows 10/11, PowerShell/CMD launch
:: ============================================================================
:: KONFIGURATION
:: ============================================================================
set "PYTHON_313_PATH=C:\Users\chris\AppData\Local\Programs\Python\Python313"
set "VENV_NAME=flask_env"
set "FLASK_APP_FILE=app.py"

:: Git-Konfiguration
set "GIT_REMOTE_URL=https://github.com/christiani93/AgilitySoftware.git"
set "GIT_USER_NAME=Christian Imhof"
set "GIT_USER_EMAIL=christiani93@gmail.com"

:: Auto-Update vom Remote (1 = an, 0 = aus)
set "AUTO_UPDATE=1"
:: Update-Strategie: pull (sicher) oder hard (erzwingt Stand von origin/main)
set "UPDATE_STRATEGY=pull"

:: ============================================================================
:: ENDE KONFIG
:: ============================================================================

:: UTF-8 für die Konsole
chcp 65001 > nul

echo.
echo =========================================================
echo  AgilitySoftware - Dev Start (mit Auto-Update)
echo  Projektpfad: %~dp0
echo =========================================================
echo.

:: Ins Projektverzeichnis wechseln
cd /d "%~dp0"

:: Ein paar Hilfsfunktionen
set "_LOG=%~dp0start_dev.log"
call :log "=== Start: %DATE% %TIME% ==="
call :log "[INFO] PROJECT_DIR=%CD%"

:: --------------------------------------------------------------------------
:: Git vorbereiten (Repo, Remote, User, .gitignore)
:: --------------------------------------------------------------------------
where git >nul 2>&1 || (
  call :err "Git wurde nicht gefunden. Bitte Git installieren (https://git-scm.com/) und erneut starten."
  pause & exit /b 1
)

:: user.name / user.email global setzen (idempotent)
call :log "[INFO] setze Git user.name / user.email (global)"
git config --global user.name "%GIT_USER_NAME%" 1>nul 2>nul
git config --global user.email "%GIT_USER_EMAIL%" 1>nul 2>nul

:: Repo initialisieren, falls nicht vorhanden
if not exist ".git\" (
  call :log "[INFO] git init im %CD%"
  git init || (call :err "git init fehlgeschlagen." & pause & exit /b 1)
)

:: Remote origin setzen/prüfen
for /f "usebackq tokens=1,2,3" %%A in (`git remote -v`) do (
  if /i "%%A"=="origin" (
    set "HAB_ORIGIN=1"
  )
)
if not defined HAB_ORIGIN (
  call :log "[INFO] setze origin: %GIT_REMOTE_URL%"
  git remote add origin "%GIT_REMOTE_URL%" 1>nul 2>nul
)

:: sinnvolle .gitignore anlegen/aktualisieren (falls fehlt)
if not exist ".gitignore" (
  > ".gitignore" (
    echo %VENV_NAME%/
    echo ring_server_env_32bit/
    echo raw_data_viewer_env/
    echo build/
    echo dist/
    echo __pycache__/
    echo *.log
    echo *.spec
  )
  git add .gitignore 1>nul 2>nul
  git commit -m "Add .gitignore (env/build/log/cache)" 1>nul 2>nul
)

:: --------------------------------------------------------------------------
:: Auto-Update (optional)
:: --------------------------------------------------------------------------
if "%AUTO_UPDATE%"=="1" (
  call :log "[INFO] Auto-Update aktiv: Strategie=%UPDATE_STRATEGY%"

  :: laufende Rebase-Reste aufräumen
  if exist ".git\rebase-merge" (
    call :log "[HINWEIS] Entferne alten rebase-merge Ordner"
    rmdir /s /q ".git\rebase-merge" 2>nul
  )

  :: auf main wechseln/erstellen
  git rev-parse --verify main 1>nul 2>nul || git checkout -b main 1>nul 2>nul
  git checkout main 1>nul 2>nul

  :: Upstream setzen (falls noch nicht gesetzt)
  git rev-parse --abbrev-ref --symbolic-full-name @{u} 1>nul 2>nul
  if errorlevel 1 (
    git branch --set-upstream-to=origin/main main 1>nul 2>nul
  )

  :: Status notieren (nur zu Info)
  call :log "[INFO] git status (Kurzform):"
  git status -s

  :: Start-Log aus dem Index entfernen (falls je committet)
  git rm --cached -r --quiet start_dev.log 2>nul

  :: Pull/Hard-Reset
  if /i "%UPDATE_STRATEGY%"=="hard" (
    call :log "[INFO] git fetch --all && reset --hard origin/main"
    git fetch --all
    git reset --hard origin/main || call :log "[WARN] reset --hard nicht möglich."
  ) else (
    call :log "[INFO] git pull --rebase --autostash"
    git pull --rebase --autostash origin main
    if errorlevel 1 (
      call :log "[WARNUNG] Pull/Rebase fehlgeschlagen, versuche Reparatur..."
      git rebase --abort 1>nul 2>nul
      git fetch origin
      git pull --rebase --autostash origin main || call :log "[WARNUNG] Pull weiterhin fehlgeschlagen."
    )
  )

  :: Abschlussinfo
  call :log "[INFO] git log --oneline -1:"
  git log --oneline -1
) else (
  call :log "[INFO] Auto-Update ist deaktiviert."
)

:: --------------------------------------------------------------------------
:: Python/venv vorbereiten
:: --------------------------------------------------------------------------
call :log "[SCHRITT 2/5] Erstelle/Pruefe virtuelle Umgebung ""%VENV_NAME%""..."
if not exist "%VENV_NAME%\Scripts\activate.bat" (
  if not exist "%PYTHON_313_PATH%\python.exe" (
    call :err "Python 3.13 unter %PYTHON_313_PATH% nicht gefunden. Pfad anpassen!"
    pause & exit /b 1
  )
  "%PYTHON_313_PATH%\python.exe" -m venv "%VENV_NAME%" || (
    call :err "Konnte venv nicht erstellen."
    pause & exit /b 1
  )
)
call :log "Virtuelle Umgebung bereit."

:: aktivieren
call "%VENV_NAME%\Scripts\activate.bat"
if errorlevel 1 (
  call :err "Konnte venv nicht aktivieren."
  pause & exit /b 1
)

:: pip / python Version
call :log "[SCHRITT 3/5] Aktiviere Umgebung und installiere Module..."
python --version
pip --version

:: requirements installieren (idempotent)
if exist requirements.txt (
  call :log "Installiere Pakete aus requirements.txt ..."
  pip install -r requirements.txt
) else (
  call :log "requirements.txt fehlt – installiere Standardpakete und erzeuge requirements.txt"
  pip install Flask openpyxl Flask-SocketIO pyinstaller gevent gevent-websocket pywin32 requests
  pip freeze > requirements.txt
)

:: --------------------------------------------------------------------------
:: Start der Flask-Anwendung
:: --------------------------------------------------------------------------
call :log "[SCHRITT 5/5] Starte die Flask-Webanwendung..."
set "FLASK_APP=%FLASK_APP_FILE%"

:: WICHTIG: SocketIO benötigt gevent/gevent-websocket – sind oben im Install
python -m flask run
set "_EXITCODE=%ERRORLEVEL%"

echo.
echo =========================================================
echo Flask-Anwendung beendet. Exitcode: %_EXITCODE%
echo =========================================================
echo.

call :log "========================================================="
call :log "Flask-Anwendung beendet. Exitcode: %_EXITCODE%"
call :log "========================================================="
echo [LOG] Vollstaendiges Log: %_LOG%
echo.
pause
exit /b 0

:: ============================================================================
:: Hilfs-Labels
:: ============================================================================
:log
  set "_msg=%~1"
  >> "%_LOG%" echo %DATE% %TIME% %_msg%
  echo %~1
  exit /b

:err
  set "_msg=%~1"
  >> "%_LOG%" echo %DATE% %TIME% [FEHLER] %_msg%
  echo [FEHLER] %~1
  exit /b
