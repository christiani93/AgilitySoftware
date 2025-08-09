@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul

REM =============================================================================
REM AgilitySoftware Webanwendung Start-Skript (stabil, mit Auto-Git & Diagnose)
REM =============================================================================

REM ---------- Projektordner = Ordner dieser BAT ----------
set "PROJECT_DIR=%~dp0"
set "PROJECT_DIR=%PROJECT_DIR:~0,-1%"
cd /d "%PROJECT_DIR%" || (
  echo [FEHLER] Projektordner nicht erreichbar: %PROJECT_DIR%
  goto :HALT
)

REM ---------- Logging ----------
set "LOG_FILE=%PROJECT_DIR%\start_dev.log"
> "%LOG_FILE%" echo ===== Start: %date% %time% =====
call :LOG "[INFO] PROJECT_DIR=%PROJECT_DIR%"

REM ---------- Konfiguration ----------
set "PYTHON_313_PATH=C:\Users\chris\AppData\Local\Programs\Python\Python313"
set "VENV_NAME=flask_env"
set "FLASK_APP_FILE=app.py"
set "PIP_PACKAGES=Flask openpyxl Flask-SocketIO pyinstaller gevent gevent-websocket pywin32 requests"

REM Git
set "USE_GIT=1"
set "GIT_BRANCH=main"
set "GIT_REMOTE_URL=https://github.com/christiani93/AgilitySoftware.git"
set "DO_GIT_PULL=1"
set "DO_GIT_PUSH=1"
set "COMMIT_PREFIX=Dev-Update"

REM venv-Handling (1 = wie bisher jede Session neu aufsetzen; 0 = behalten)
set "RECREATE_VENV=1"

REM Abgeleitet
set "VENV_ACTIVATE=%PROJECT_DIR%\%VENV_NAME%\Scripts\activate.bat"

REM ---------- Dateiliste & Basisprüfung ----------
call :LOG "[INFO] Datei-Liste (Top-Level):"
dir /b >>"%LOG_FILE%" 2>&1
if not exist "%FLASK_APP_FILE%" (
  call :LOG "[FEHLER] Startdatei fehlt: %PROJECT_DIR%\%FLASK_APP_FILE%"
  echo [FEHLER] Startdatei fehlt: %FLASK_APP_FILE%
  goto :HALT
)

REM =============================================================================
REM 0) Git: Auto-Konfiguration + Pull/Push (keine Interaktion)
REM =============================================================================
if "%USE_GIT%"=="1" (
  where git >nul 2>&1 || (
    call :LOG "[FEHLER] Git nicht installiert. https://git-scm.com/download/win"
    echo [FEHLER] Git nicht installiert. Siehe Log.
    goto :HALT
  )

  REM --- Git Identity IMMER setzen (failsafe) ---
  call :LOG "[INFO] setze Git user.name / user.email (global, failsafe)"
  git config --global user.name "Christian Braunschweiler" >>"%LOG_FILE%" 2>&1
  git config --global user.email "christiani93@gmail.com"   >>"%LOG_FILE%" 2>&1

  REM --- Repo initialisieren, wenn keins vorhanden ---
  if not exist ".git" (
    call :LOG "[INFO] git init im %PROJECT_DIR%"
    git init >>"%LOG_FILE%" 2>&1 || (call :LOG "[FEHLER] git init fehlgeschlagen." & goto :HALT)
    git branch -M %GIT_BRANCH% >>"%LOG_FILE%" 2>&1
    if not "%GIT_REMOTE_URL%"=="" (
      git remote add origin "%GIT_REMOTE_URL%" >>"%LOG_FILE%" 2>&1
      if errorlevel 1 call :LOG "[HINWEIS] origin evtl. schon gesetzt."
    )
    git add -A >>"%LOG_FILE%" 2>&1
    git commit -m "Initial commit (auto start_dev)" >>"%LOG_FILE%" 2>&1
  )

  REM --- Optionaler Pull vor Start ---
  if "%DO_GIT_PULL%"=="1" (
    call :LOG "[INFO] git pull --rebase --autostash"
    set "HAS_CHANGES="
    for /f "delims=" %%s in ('git status --porcelain 2^>nul') do set HAS_CHANGES=1
    if defined HAS_CHANGES git stash push -u -m "temp-stash-before-pull" >>"%LOG_FILE%" 2>&1

    git fetch --all >>"%LOG_FILE%" 2>&1
    git checkout %GIT_BRANCH% >>"%LOG_FILE%" 2>&1
    git pull --rebase --autostash >>"%LOG_FILE%" 2>&1
    if errorlevel 1 (
      call :LOG "[WARNUNG] pull-Konflikt/Fehler. Details im Log."
      for /f "delims=" %%S in ('git stash list ^| find /c "temp-stash-before-pull"') do set STASH_COUNT=%%S
      if not "%STASH_COUNT%"=="0" git stash pop >>"%LOG_FILE%" 2>&1
    ) else (
      for /f "delims=" %%S in ('git stash list ^| find /c "temp-stash-before-pull"') do set STASH_COUNT=%%S
      if not "%STASH_COUNT%"=="0" git stash pop >>"%LOG_FILE%" 2>&1
    )
  )
)

REM =============================================================================
REM 1) Bereinigen (venv + __pycache__)
REM =============================================================================
echo.
echo [SCHRITT 1/5] Bereinige alte virtuelle Umgebung und Caches...
if "%RECREATE_VENV%"=="1" (
  if exist "%VENV_NAME%\" (
    echo Loesche vorhandene virtuelle Umgebung "%VENV_NAME%"...
    rmdir /s /q "%VENV_NAME%"
    if exist "%VENV_NAME%\" (
      call :LOG "[FEHLER] Konnte venv nicht loeschen."
      echo FEHLER: Konnte venv nicht loeschen.
      goto :HALT
    )
  )
) else (
  echo [INFO] RECREATE_VENV=0 -> ueberspringe venv-Loeschung.
)

echo Loesche Python Cache-Verzeichnisse (__pycache__)...
for /d /r . %%d in (__pycache__) do (
  if exist "%%d" rmdir /s /q "%%d"
)
echo Bereinigung abgeschlossen.

REM =============================================================================
REM 2) venv erstellen (oder vorhanden)
REM =============================================================================
echo.
echo [SCHRITT 2/5] Erstelle/Pruefe virtuelle Umgebung "%VENV_NAME%"...
if not exist "%VENV_NAME%\Scripts\activate.bat" (
  if exist "%PYTHON_313_PATH%\python.exe" (
    "%PYTHON_313_PATH%\python.exe" -m venv "%VENV_NAME%"
  ) else (
    call :LOG "[HINWEIS] PYTHON_313_PATH nicht gefunden. Versuche System-Python."
    python -V >nul 2>&1 || (echo FEHLER: Kein Python gefunden. Pfad pruefen. & goto :HALT)
    python -m venv "%VENV_NAME%"
  )
)
if not exist "%VENV_ACTIVATE%" (
  echo FEHLER: venv konnte nicht erstellt werden.
  goto :HALT
)
echo Virtuelle Umgebung bereit.

REM =============================================================================
REM 3) venv aktivieren + Pakete installieren
REM =============================================================================
echo.
echo [SCHRITT 3/5] Aktiviere Umgebung und installiere Module...
call "%VENV_ACTIVATE%" || (echo FEHLER: venv-Aktivierung fehlgeschlagen. & goto :HALT)

python --version
pip --version

echo Installiere Pakete: %PIP_PACKAGES%
pip install --upgrade pip >>"%LOG_FILE%" 2>&1
pip install %PIP_PACKAGES% >>"%LOG_FILE%" 2>&1
if errorlevel 1 (
  echo FEHLER: Paket-Installation fehlgeschlagen. Details in %LOG_FILE%
  goto :HALT
)

REM pywin32 Post-Install (silent best effort)
for /f "delims=" %%P in ('python -c "import sys,site;print(site.getsitepackages()[0])"') do set "SITEPKG=%%P"
if exist "%SITEPKG%\pywin32_postinstall.py" (
  python "%SITEPKG%\pywin32_postinstall.py" -install >>"%LOG_FILE%" 2>&1
)

REM =============================================================================
REM 4) requirements.txt schreiben
REM =============================================================================
echo.
echo [SCHRITT 4/5] Erzeuge/Aktualisiere requirements.txt ...
pip freeze > requirements.txt
if errorlevel 1 (
  echo WARNUNG: requirements.txt konnte nicht erzeugt werden.
) else (
  echo requirements.txt aktualisiert.
)

REM =============================================================================
REM 5) Flask starten
REM =============================================================================
echo.
echo [SCHRITT 5/5] Starte die Flask-Webanwendung...
set "FLASK_APP=%FLASK_APP_FILE%"
python -m flask run
set "RC=%ERRORLEVEL%"
echo.
echo =========================================================
echo Flask-Anwendung beendet. Exitcode: %RC%
echo =========================================================

REM =============================================================================
REM 6) Optional: Push nach Beendigung
REM =============================================================================
if "%USE_GIT%"=="1" if "%DO_GIT_PUSH%"=="1" (
  call :LOG "[INFO] pruefe lokale Aenderungen fuer Push (Post-Run)"
  set "HAS_CHANGES="
  for /f "delims=" %%s in ('git status --porcelain 2^>nul') do set HAS_CHANGES=1
  if defined HAS_CHANGES (
    git add -A >>"%LOG_FILE%" 2>&1
    set "COMMIT_MSG=%COMMIT_PREFIX% %date% %time%"
    git commit -m "%COMMIT_MSG%" >>"%LOG_FILE%" 2>&1
    git rev-parse --abbrev-ref --symbolic-full-name @{u} >nul 2>&1
    if errorlevel 1 ( git push -u origin %GIT_BRANCH% ) else ( git push )
  ) else (
    call :LOG "[INFO] keine Aenderungen zu pushen."
  )
)

goto :ENDE

:LOG
echo %~1
>>"%LOG_FILE%" echo %date% %time% %~1
goto :eof

:HALT
echo.
echo [LOG] Vollstaendiges Log: %LOG_FILE%
echo Druecke eine Taste, um das Fenster zu schliessen...
pause >nul
exit /b 1

:ENDE
echo.
echo [LOG] Vollstaendiges Log: %LOG_FILE%
echo Druecke eine Taste, um das Fenster zu schliessen...
pause >nul
endlocal
