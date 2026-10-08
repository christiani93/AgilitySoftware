# AgilitySoftware — Offene Punkte

> Persistente ToDo-Liste fuer dieses Projekt. Wird beim Wechsel ins Projekt von
> Claude gelesen. Bei Aenderungen manuell aktuell halten.

Stand: 2026-10-08

## ⏳ Ring-Reassign-Fix + Event-Liste-Fix + DEV-GUI-Bat (2026-10-08 Abend) — NICHT committed

- [x] `ring_server.py`: Handler `reassign_current_starter` (`handle_reassign`) ergänzt →
      LINKE "Starter: #N"-Nummer am Ring-PC-Panel folgt jetzt dem "Zeit zuweisen"-Button
      (ohne Timer-Reset). War die dritte, bisher ungefixte "aktueller Starter"-Quelle
      (lokaler Ring-Server-State, NICHT Hauptserver). Memory `reference_ring_state_dual_mechanism`.
- [x] `events_list.html`: Fallback-Label für Events ohne `Bezeichnung` (Alt-Schema) →
      titellose Zeile jetzt sichtbar + löschbar. Memory `project_titleless_event_diagnosis`.
- [x] **NEU `Start_Ring_dev_gui.bat`** (Projekt-Root): startet Ring-Server MIT GUI aus
      Quellcode via `ring_launcher.py` (wie EXE, ohne Build). Memory `reference_ring_build_and_dev_run`.
- [x] **AgilityRing.exe neu gebaut** (2026-10-08 21:05, enthält handle_reassign) → `dist/AgilityRing.exe`.
- [ ] **COMMIT** dieser 3 Änderungen (ring_server.py, events_list.html, Start_Ring_dev_gui.bat).
- [ ] **GitHub-Push** (zusammen mit dem schon offenen Push unten).
- [ ] Mehrring-Realtest: linke Nummer folgt Reassign auf echtem Ring-PC.

## ✅ Druck-Fixes Runde 2 + EXE-Build (2026-10-08 Abend) — COMMITTED + EXE GEBAUT

Zweite Druck-Feedback-Runde committed (`d125eb7`/`f2e9b4e`/`2fc5ea7`, `main`), 170 Tests grün,
EXE neu gebaut. Details Memory `project_print_fixes_20261008`, `project_software_exe_build`.
- [x] `master_steward_list.html` (Einweiserliste): Laufvorgaben-Tabelle (Parcours/SCT/MCT/Richter/
      Unterschrift) ENTFERNT (nicht benötigt).
- [x] Zeitpläne (`print/schedule` + Sammeldruck `.sec-schedule`): Schrift/Padding verkleinert →
      ~25 Läufe/Seite inkl. Kategorie-Unterzeile. Briefing/Umbau unverändert.
- [x] Schreiberlisten (`scribe_list` + `_by_schedule` + Sammeldruck `.sec-scribe`): kompakter →
      ~20 Teilnehmer/Seite.
- [x] „DIS/ABR"-Spaltenkopf übersetzbar (`{{ _('DIS/ABR') }}`; FR=DIS/ABD, EN=DIS/WD, DE-Fallback)
      + msgid in de/en/fr .po + `pybabel compile`.
- [x] `print/all`: Einweiser- + Ringbüro-Bündel banden `_print_header` GAR NICHT ein → keine Logos.
      Jetzt pro Ring in `page-table/thead`-Technik → Logo auf jeder Seite. Startlisten-Bündel ebenso.
- [x] **AgilitySoftware.exe neu gebaut** aus HEAD `2fc5ea7` (64-bit, Smoke HTTP 200). AgilityRing.exe
      NICHT neu (keine Ring-Änderungen).
- [ ] **GitHub-Push**: origin/main=`49b5972`; lokal voraus mit `bc37976`/`1262f44`/`f9618e2`/
      `41dfbad`/`d125eb7`/`f2e9b4e`/`2fc5ea7`. Noch pushen.

## ✅ Läufig-Toggle Software (2026-10-08) — COMMITTED (`41dfbad` + Teil-3-Erweiterung)

- [x] Route `POST /events/api/toggle_in_season/<event_id>/<license_nr>` (flippt `is_in_season` in
      allen Läufen der Hündin). UI-Button + Badge in `manage_run_participants.html` (`41dfbad`) UND
      zusätzlich in `manage_all_participants.html` (Teil 3). Test `test_toggle_in_season.py`.

## ✅ Druck/Export/Richter-Fix-Runde 1 (2026-10-08) — COMMITTED (`f9618e2`), in EXE

Erste Runde committed als `f9618e2`; Portal-Teil (`ring_start_times`) deployed (44c100c→991578f).
Alle Fixes in der 2fc5ea7-EXE enthalten. Details in Memory `project_print_fixes_20261008`.
- [x] Logo-Größen (global im `_print_header.html`), Logos an 6 Druck-Routen ergänzt
- [x] Übersetzungen: Zeit/Fehler/Verw./Laufvorgaben + Umbau/Lauf/Start/Ende (fr/en .po + compile)
- [x] Ausland-Kennzeichnung Startliste (is_foreign/foreign_cc; `_()` NICHT im Python!)
- [x] print/all: Trennung Zeitplan↔Listen + Laufvorgaben bei Ringschreiberlisten
- [x] Zeitplan auf 1 Seite verkleinert
- [x] manage_runs: doppelter Export-Button bereinigt (JSON raus, ZIP bleibt)
- [x] Richter „richtet Lauf": Sync Block↔Lauf (Lauf=SSoT) in Import/edit_run/save_schedule
- [x] Portal (anderes Repo): `ring_start_times` im eventexport → DEPLOYED; Event-9-Reimport erledigt
- [x] **COMMIT** (Software `f9618e2` + Portal) — erledigt
- [x] **EXE-Rebuild** — erledigt (2fc5ea7-EXE)
- [x] **Portal-Deploy** für Startzeit-Fix — erledigt

### Offene Features (User-Freigabe)
- [x] (9) Echter Läufigkeits-Toggle in Software — erledigt (`41dfbad`, s.o.)
- [ ] (10) „Ist anwesend"-Richterliste am Event (wie Portal `EventJudge`) — neues Datenmodell + UI
- [ ] (11) Software-Zeitplan/Richter an Portal-Architektur angleichen (gemeinsame Logik, nur JSON vs SQL) — eigenes Refactoring-Projekt

## ✅ ERLEDIGT: EXE-Rebuild für KO-System-Button (2026-10-08)

Commit **`9c737d7`** (feature/ko-cup) "KO-System-Button im Ring-Dashboard" ist
committed + lokal getestet. BEIDE EXE **im Vordergrund neu gebaut** aus HEAD
`9c737d7`:
- [x] **AgilityRing.exe** (32-bit, `web_app/ring_env` + `installer/AgilityRing.spec`)
      → `dist/` Stand 07:46 — neuer Tkinter-Button "KO-System öffnen".
- [x] **AgilitySoftware.exe** (64-bit, `web_app/flask_env` + `installer/AgilitySoftware.spec`)
      → `dist/` Stand 07:45 — neue Route `/ring_pc_ko/<ring>`. Headless-Smoke:
      `/health`→200, `/ring_pc_ko/1` ohne aktives Event →404 wie erwartet.
- Mechanik dokumentiert in Memory `project_exe_rebuild_20261008`.

## Halloween Cup KO-System (Deadline 30.10.–01.11.2026) — IN ARBEIT auf Branch `feature/ko-cup`

- [x] Ring-PC KO-System-Button: Tkinter-Dashboard hat jetzt 2. Button "KO-System
      öffnen" → Hauptserver-Route `/ring_pc_ko/<ring>` löst aktives Event auf und
      leitet auf `/ko-cup/ring/<event_id>?ring=N` weiter (`9c737d7`, EXE-Rebuild offen, s.o.)

Architektur entschieden (06.10.): **Variante B** — KO offline in AgilitySoftware mit TIMY,
Portal nur read-only Live-Anzeige. Finalisten-Transfer an `eventexport.v1` inkl. **Startnummer**
(tiefere Nr. → Ring 1).

- [x] Phase 1: KO-Bracket-Engine + Management-UI (`b14673a`)
- [x] Diagnose-Recorder im Ring-Server (C0/C1/RT-Paarung + delta_vs_timy) (`7769d89`)
- [x] Scheduling Schritt 1: echte TIMY-Startzeit ins Result (`788706a`)
- [ ] Phase 2: TIMY-Live Duell-Eingabe, 2-Ring-Wiring
- [ ] Phase 3: Finalisten-Sync inkl. Startnummer an eventexport anhängen
- [ ] Phase 4+: Print/Export Siegerehrung/Rangliste
- [ ] Generalprobe ~25./26.10.2026
- [ ] Branch `feature/ko-cup` nach `main` mergen (aktuell 3 Commits voraus, ungemerged)
- [ ] 1/100-Bug weiterbeobachten: Recorder zeigt `delta_vs_timy=0` (TIMY-Zeit korrekt),
      Fehlerquelle vermutlich im Software-Pfad danach — am HCS-Wochenende (1 Ring, EXE) weiter aufzeichnen

## Team-Challenge (Edelweiss, 2er-Teams)

Reglement bestätigt (DIS-Team hinter Nicht-DIS via Sentinel 999, Zeitfehler normal eingerechnet).

- [x] Software P1+P2 (Team-Logik) fertig & getestet (2026-10-06)
- [x] Portal P5 (Team-Model + Admin-UI) fertig & getestet — **noch NICHT prod-deployed**
- [ ] P3/P4/P6: Sync Portal↔Software, EventRuns, Ranglisten (geplant erst Januar)

## Scheduling-Optimierung

- [x] Plan entschieden: Ø Sek/Starter **pro Klasse** (nicht Kategorie), direkt gemessen,
      keine Regression; neue Kategorie-Umbaupause
- [x] Standalone TIMY-Recorder gebaut (`tools/timy_recorder`, log+csv, replay/simulate getestet)
- [ ] Schritt 2+3: Intervall-Auswertung, Portal `run_time_config` pro Disziplin×Klasse (nach HCS)

## EXE-Build

- [x] Neu gebaut für HCS-/Jump-Wochenende: `AgilitySoftware.exe` (64-bit) + `AgilityRing.exe` (32-bit/TIMY)
- [x] `AgilitySoftware.exe` neu gebaut 2026-10-07 14:13 aus feature/ko-cup (Logo-Startlisten `45dcdaa`,
      Datenverlust-Fix `6d57db4`, CDN-Vendoring `07ead9b`, Rangliste-PDF `15ce585`). `flask_env` war leer →
      mit Python 3.13 64-bit + `web_app/requirements.txt` neu erstellt. Smoke-getestet (Startliste 200,
      Rangliste `%PDF-`, Daten intakt). Backup alte EXE: `dist/AgilitySoftware_prebuild_20261007.exe.bak`
      (gitignored, nach Bestätigung löschbar).
- [ ] AgilityRing.exe: GUI-Launcher von Chris starten/prüfen (headless nicht testbar); ist von 07.10. 09:29
      (vor CDN-Vendoring 12:15 — für Startlisten-Druck irrelevant, bei Bedarf rebuilden)
- [ ] feature/ko-cup → main mergen (Software)

## PDF-/Design-Arbeit (geplant ab 07.10.2026)

- [x] **Sammeldruck** `print_all` (`/print/all/<event_id>`, `print/all.html`) — ein Druckauftrag, drei
      Bündel mit Titelseiten: (1) Teilnehmerinfo (Alle Ringe) = Zeitplan + Startlisten, (2) Einweiser
      (pro Ring) = Ring-Zeitplan + Einweiserliste nach Ringzeitplan, (3) Ringbüro (pro Ring) = Ring-Zeitplan
      + Ringschreiberliste nach Ringzeitplan. CSS pro Layout gescopt (.sec-schedule/-startlist/-steward/-scribe).
      Button auf `print/index.html`. Smoke-Test `tests_pure/test_print_all_route.py`. feature/ko-cup, braucht EXE-Rebuild.
- [x] **Rangliste-PDF** `print_ranking_pdf.html` (Software→Portal-Upload) — COMMITTED `15ce585`
      (feature/ko-cup, in neuer EXE; noch NICHT nach main gemerged): an SportyDog-Vorlage angeglichen
      (Logo-Header, Laufvorgaben-Box 2×3, m/s-Spalten, Statistik mit %); Start-Nr. + Liz. entfernt (12 Spalten);
      Banner oben entfernt; Statistik-Abstände gefixt.
- [x] **Rangliste-PDF BUG — Fusszeile allein auf Seite 2** GEFIXT (`15ce585`): Footer von `display:table`
      auf echtes `<table>` (td `border-top`) → kein Orphan mehr; Zeilen gestrafft (`padding:1pt` +
      `line-height:1.1`). 30 realistische Teams (sogar 40) auf 1 Seite; nur Worst-Case (jede Zeile bricht
      um) → 2 Seiten (vom User akzeptiert). Verifiziert via pisa+pymupdf-Harness in `%LOCALAPPDATA%\AgilityBuild`.
- [x] **Siegerehrungsliste** `print_award_list.html` überarbeitet (2026-10-07, `31f185f`, nur lokal):
      Kategorie-Sortierung L→I→M→S; echte Logos via neuem Helper `utils.get_event_logo_data_uris()`
      + `_print_header.html` (`<img>` mit Platzhalter-Fallback); Seiten-Überlappung behoben
      (fixed-Header verworfen → Flow + Browser-Kopf/Fuss); `fitContentToPages()` Zoom auf 1–2 Seiten;
      Bootstrap-CDN entfernt (offline-tauglich); **DIS-Läufe ausgeblendet** (positiv-check `platz is
      number and >0`, da `platz` bei DIS defined-but-None). ← **User-Review im Dev ausstehend**
- [x] **KO-Druck** `ko_cup_print.html` (2026-10-07, `f851c00`+`e8d8d5c`, nur lokal): geteilter Logo-Header;
      Reihenfolge Endrangliste→Duell-Laufzettel; **CATEGORY_ORDER S-M-I-L** (bewusst ANDERS als
      Siegerliste L-I-M-S — Large-Final zuletzt; nur Anzeige, nicht Bracket-Mathe).
- [x] **NEU Ring-Startlisten** `/ko-cup/rings_print/<event_id>` + `ko_cup_rings_print.html` + Helper
      `_event_ring_startlists`: kombiniert über ALLE Kategorien, Sortierung `(-phase, cat_rank,
      type_rank, matchup_no)`. Link ab `ko_cup_config.html`. 141/141 Tests grün.
- [x] Ring-Startlisten verfeinert (2026-10-07, nur lokal): nur **Lauf 1** gelistet (bei Lauf 2
      wechseln dieselben Teams intern den Ring, kein eigener Eintrag nötig — Spalte "Lauf" entfernt);
      innerhalb der Finalrunde **Spiel um Platz 3 vor dem Final** (Grosses Finale läuft als letztes
      Duell).
- [ ] Ring-Startlisten: generische Annäherung, KEIN exaktes Ring-Auslastungs-Balancing wie
      handgemachte Excel-Ablauftabelle (Foto) — bei Bedarf explizitere Scheduling-Regel definieren.
- [x] **Direkter Startlisten-Link am Ring-PC** (2026-10-07, nur lokal): `ko_cup_ring.html` hat jetzt
      Button "📋 Startliste Ring N" → `/ko-cup/rings_print/<event_id>#ring-N` (neuer Tab), Sprungmarke
      `id="ring-N"` in `ko_cup_rings_print.html`. Vorher nur über Admin-Config erreichbar. 142/142 Tests grün.
- [ ] **Edelweiss: Agi+Jumping pro Team direkt nacheinander** (aufgefallen 2026-10-07): bei Edelweiss
      (Team-Challenge) müssen die beiden Läufe eines Teams (Agility + Jumping) im Zeitplan unmittelbar
      hintereinander kommen, nicht wie bisher nach Klasse getrennt in eigenen Blöcken. Technische
      Anpassung an der Zeitplan-/Laufreihenfolge-Logik noch offen — siehe Memory
      `project_schedule_optimization` + `project_team_challenge_status`.
- [ ] **KO-Schlüssel-Einstellung (UI)**: Finalisten-Ableitung in `ko_qualification.py` nutzt aktuell
      fest `DEFAULT_SCHLUESSEL` (2026). Noch keine Oberfläche, um den Schlüssel pro Event
      einzustellen/überschreiben (welche Läufe zählen, Anzahl Finalisten je Kategorie). Später
      nachrüsten — für HCS reicht der Default.
- [ ] Logo-Übergabe Portal→Software: Pipeline ist BEREITS komplett (Export packt `logos/*`, Import
      entpackt nach `data/logos/<event_id>/`) — bestehende Events haben noch keine Logos; nach
      erneutem Export/Import erscheinen sie. Logo-Grösse im Kopf ggf. feinjustieren.
- [ ] `ko_cup_rankings.html` (Bildschirm/Bootstrap): sauberes Offline-Druckbild erst beim CDN-Umbau.
- [ ] Offline-CDN generell: `layout.html` zieht Bootstrap/Font-Awesome/socket.io von CDN →
      lokale Bundles ablegen (ganze Software-UI offline unformatiert)
- [x] **Startlisten: Logo-Header** (2026-10-07, nur lokal): `print_startlists` + `print_startlists_by_schedule`
      (routes_print.py) gaben bisher KEIN Eventlogo an `_print_header.html` weiter (im Unterschied zu
      den KO-Drucksachen) — jetzt via `get_event_logo_data_uris()` wie dort. Templates hatten das
      Overlap-Problem (position:fixed) NICHT, nutzen bereits die Tabellen-Wiederhol-Kopfzeile. 146/146
      Tests grün (neu: `test_print_startlists_route.py`).
- [ ] Startlisten/Steward/Marshall/Teilnehmer/Zeitplan: gemeinsames Druck-Design-System — Rest offen:
      `print_marshall_list.html`, `print_ranking_single.html`, `print/participant_list.html` haben noch
      das alte `position:fixed`-Overlap-Problem (siehe `print_award_list.html`-Fix als Vorlage); deren
      Routen übergeben zudem ebenfalls keine Logos. `startlist_print.html`/`startlist_print_all.html`
      sind toter Code (keine Route verweist mehr drauf) — Aufräumen separat prüfen.

## Offene Branches / Reglement-Sprints

- [ ] Branch `claude/vibrant-swartz` prüfen und mergen — P1-Fixes: manage_runs Ring-Anzeige,
      live-set, MCT Klasse 1, DNS-Status (deckt sich mit länger offenen P1-Bugs, siehe Memory
      `master-todo-list`)
- [ ] SKBS-SM + FMBB-Quali Münsingen fertigstellen (Deadline 05.–06.12.2026, Doppelnutzungs-Event) —
      siehe AgilityPortal `DEV_PLAN.md` + Memory `project_implementation_plan_dec2026`
- [ ] Edelweiss Challenge: Berechnungsmodul bauen, sobald Reglement geklärt ist (Deadline 08.–10.01.2027)

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
