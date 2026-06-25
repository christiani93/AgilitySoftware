# AgilitySoftware - EXE-Builds

Hier liegen die Build-Skripte für die zwei verteilbaren EXEs:

| EXE                  | Quelle (venv)                 | Python   | Beschreibung                       |
|----------------------|-------------------------------|----------|------------------------------------|
| `AgilitySoftware.exe`| `web_app\flask_env` (Junction)| 64-bit   | Hauptserver (Flask, Port 5000)     |
| `AgilityRing.exe`    | `web_app\ring_env` (Junction) | 32-bit   | Ring-Server + Tkinter-Launcher     |

**Warum 2 EXEs?** Der Ring-Server steuert die TIMY-Hardware über `pywin32`/COM
und braucht zwingend 32-bit Python. Der Hauptserver läuft schneller und ohne
Hardware unter 64-bit. PyInstaller kann beide nicht in eine EXE bündeln –
das ist eine Architektur-Konstante.

## venv-Setup (einmalig pro PC)

Aus Architekturgründen liegen beide venvs **außerhalb von OneDrive** unter
`%USERPROFILE%\.venvs\AgilitySoftware\`. Im Projekt zeigen Junctions darauf:

```
web_app\flask_env  ->  C:\Users\chris\.venvs\AgilitySoftware\flask_env  (64-bit)
web_app\ring_env   ->  C:\Users\chris\.venvs\AgilitySoftware\ring_env   (32-bit)
```

Setup falls noch nicht vorhanden (PowerShell):

```powershell
# 64-bit venv für Hauptserver
py -3 -m venv "$env:USERPROFILE\.venvs\AgilitySoftware\flask_env"
& "$env:USERPROFILE\.venvs\AgilitySoftware\flask_env\Scripts\python.exe" -m pip install -r web_app\requirements.txt

# 32-bit venv für Ring-Server (Python 3.13 32-bit muss installiert sein)
& "C:\Users\chris\AppData\Local\Programs\Python\Python313-32\python.exe" -m venv "$env:USERPROFILE\.venvs\AgilitySoftware\ring_env"
& "$env:USERPROFILE\.venvs\AgilitySoftware\ring_env\Scripts\python.exe" -m pip install pyinstaller flask flask-socketio requests pywin32

# Junctions
cmd /c mklink /J "web_app\flask_env" "$env:USERPROFILE\.venvs\AgilitySoftware\flask_env"
cmd /c mklink /J "web_app\ring_env"  "$env:USERPROFILE\.venvs\AgilitySoftware\ring_env"
```

## Build

```bat
REM Hauptserver bauen
installer\build_main.bat

REM Ring-Server bauen
installer\build_ring.bat
```

Der Build läuft **außerhalb von OneDrive** in `%LOCALAPPDATA%\AgilityBuild\`
(damit OneDrive nicht jeden Temp-File synchronisiert). Die fertige EXE wird
nach `dist\AgilitySoftware.exe` bzw. `dist\AgilityRing.exe` zurückkopiert.

## Distribution

### Hauptserver-PC
- `AgilitySoftware.exe` an einen lokalen Ort kopieren (z.B. `C:\Agility\`).
- Beim Start öffnet sich automatisch ein App-Fenster (Edge WebView2) mit der
  Oberfläche – kein Standardbrowser nötig. Die Konsole bleibt als Log-Fenster
  offen und zeigt zusätzlich die eigene LAN-IP an, die in den Ring-PCs
  einzutragen ist.
- Daten landen standardmäßig in `<EXE-Ordner>\data\`.
- Für NAS-Speicher: `set AGILITY_DATA_DIR=\\NAS\Agility\data` vor EXE-Start.
- Headless-Modus (z.B. Server-PC im Schrank, Zugriff nur via Browser von
  anderen Geräten): `set AGILITY_NO_WINDOW=1` – dann startet kein App-Fenster.

### Ring-PCs (jeder Ring eigener PC)
- `AgilityRing.exe` auf jeden Ring-PC kopieren.
- Beim ersten Start öffnet sich das Konfig-Fenster:
  - Ring-Nr (1, 2 oder 3)
  - Hauptserver-IP (steht im Banner des Hauptservers)
- Wird in `ring_config.json` neben der EXE gespeichert und beim nächsten
  Start vorausgefüllt.

## Port-Konvention

| Komponente  | Port  |
|-------------|-------|
| Hauptserver | 5000  |
| Ring 1      | 5001  |
| Ring 2      | 5002  |
| Ring 3      | 5003  |

Allgemein: **Ring-Port = 5000 + Ring-Nr**.

## Update-Mechanismus

Beide EXEs prüfen beim Start gegen die GitHub-Releases-API
(`christiani93/AgilitySoftware`, Repo via Env `AGILITY_UPDATE_REPO` änderbar):

- Bei verfügbarem Update zeigt die Konsole einen Banner mit
  installierter & neuer Version + Download-Link.
- Es wird **nichts automatisch installiert** – der User lädt das neue EXE
  bewusst selbst herunter (wichtig: nicht am Veranstaltungstag updaten).
- Bei Offline / Fehler wird der Check still übersprungen; der Start gelingt
  auch ohne Internet.
- Deaktivieren: `set AGILITY_NO_UPDATE_CHECK=1`.

Release-Workflow (für Maintainer):

1. `APP_VERSION` in `web_app/app.py` (Hauptserver) bzw. `RING_VERSION` in
   `web_app/ring_server/ring_launcher.py` erhöhen.
2. EXEs lokal bauen (`build_main.bat`, `build_ring.bat`).
3. In GitHub einen neuen Release anlegen, Tag `v<version>` (z.B. `v4.5`),
   beide EXEs als Assets hochladen.
4. Die Asset-Namen sollten `AgilitySoftware` bzw. `AgilityRing` im Namen
   tragen – dann findet `updater.py` den passenden Download-Link
   automatisch.
