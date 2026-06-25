# AgilitySoftware — Offene Punkte

> Persistente ToDo-Liste fuer dieses Projekt. Wird beim Wechsel ins Projekt von
> Claude gelesen. Bei Aenderungen manuell aktuell halten.

Stand: 2026-05-30

## Crashguard-Rollout

Code (`crashguard.py` im Projekt-Root) ist eingebaut. **Lokales Projekt** — kein
Server-`.env`-Eintrag, sondern Env-Vars beim Start setzen.

- [ ] In den `Start_*.bat`-Skripten (Hauptserver + Ring-PCs) ergaenzen:
  ```bat
  set CRASHGUARD_URL=https://admin.z-b.tech
  set CRASHGUARD_TOKEN=<token-aus-AdminPortal-Setup>
  ```
  Betroffen: `Start_AgilitySoftware.bat`, `Start_Launcher.bat`, `Start_Ring_1.bat`, `Start_Ring_2.bat`, `Start_Ring_3.bat`
- [ ] Achtung: **Offline-first**! Wenn Turnier ohne Internet laeuft, fallen Reports in die lokale Retry-Queue (kein Datenverlust, werden beim naechsten Online-Zustand nachgereicht). Funktion bleibt unbeeintraechtigt.
- [ ] DEV-PC: `CRASHGUARD_DISABLE=1` setzen, damit Debug/pytest nicht reported

## Aktive Entwicklung / offene Testplaene

→ Siehe Markdown-Dateien im Repo-Root:
- [`TESTPLAN_ACCEPTANCE.md`](TESTPLAN_ACCEPTANCE.md) — allgemeiner Acceptance-Testplan
- [`TESTPLAN_SCHEDULE_ACCEPTANCE.md`](TESTPLAN_SCHEDULE_ACCEPTANCE.md) — Scheduling-Acceptance
- [`EVENTEXPORT_IMPORT.md`](EVENTEXPORT_IMPORT.md) — Event-Paket-Format zu/von AgilityPortal
- [`Turnierstart.md`](Turnierstart.md) — Ablauf am Turniertag

Letzte Commits zeigen:
- SM-Modus: CSV-Export Finallisten + Qualifikationsberechnung
- i18n: Flask-Babel + DE/FR-Translations (Drucksprache-Setting fuer Print-Routes)
- TKAMO-Lizenzcheck-Workflow (forced workflow, zwei CSV-Versionen, echtes TKAMO-Format)

## Hardware-Constraints (NICHT brechen)

- **venv heisst `flask_env`** (NICHT `.venv`!)
- TIMY-Zeitmessungs-Hardware via `pywin32`
- Multi-Server: Hauptserver 5000 + Ring-PCs 5001-5003

## Architektur-Notiz

- **Lokal, offline-first** — Turnier MUSS ohne Internet laufen
- Sister-Projekt: **AgilityPortal** (online-offline-pair). Event-Paket Pre/During/Post via `EVENTEXPORT_IMPORT.md`
- **KEINE direkte Verbindung zu VAR/VAR-System** — das laeuft ueber Fremdsoftware
- Folgt TKAMO-Reglemente
