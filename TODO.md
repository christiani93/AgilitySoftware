# AgilitySoftware — Offene Punkte

> Persistente ToDo-Liste fuer dieses Projekt. Wird beim Wechsel ins Projekt von
> Claude gelesen. Bei Aenderungen manuell aktuell halten.

Stand: 2026-08-16

## Crashguard-Rollout — ✅ ERLEDIGT (2026-08-16)

Client scharf via **gitignorierte `crashguard.local.bat`** (enthält `CRASHGUARD_URL` +
`CRASHGUARD_TOKEN`, Secret bleibt aus Git). Die Prod-Start-Skripte laden sie per `call`:
`Start_AgilitySoftware.bat`, `Start_Launcher.bat`, `Start_Ring_1/2/3.bat` (+ die Launcher-
Generatoren, damit neu-erzeugte Ring-Skripte die Zeile behalten). Dev/Test-Skripte
(`Start_Ring_dev*.bat`, `Start_Launcher_DEBUG.bat`, `run_tests.bat`, `web_app/start_dev*.bat`)
setzen `CRASHGUARD_DISABLE=1` → kein Reporting aus Entwicklung/pytest.

- **Pro Prod-PC muss `crashguard.local.bat` vorhanden sein** (via OneDrive-Sync, NICHT Git).
- Offline-first: ohne Internet landen Reports in der lokalen Retry-Queue (kein Datenverlust,
  werden beim nächsten Online-Zustand nachgereicht).

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
