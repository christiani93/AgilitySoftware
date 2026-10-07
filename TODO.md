# AgilitySoftware — Offene Punkte

> Persistente ToDo-Liste fuer dieses Projekt. Wird beim Wechsel ins Projekt von
> Claude gelesen. Bei Aenderungen manuell aktuell halten.

Stand: 2026-10-07

## Halloween Cup KO-System (Deadline 30.10.–01.11.2026) — IN ARBEIT auf Branch `feature/ko-cup`

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
- [ ] AgilityRing.exe: GUI-Launcher von Chris starten/prüfen (headless nicht testbar)

## PDF-/Design-Arbeit (geplant ab 07.10.2026)

- [~] **Rangliste-PDF** `print_ranking_pdf.html` (Software→Portal-Upload, feature/ko-cup, **UNCOMMITTED**):
      an SportyDog-Vorlage angeglichen (Logo-Header, Laufvorgaben-Box 2×3, m/s-Spalten, Statistik mit %).
      Session 2 (2026-10-07): Spalten **Start-Nr. + Liz. entfernt** (12 statt 14 Spalten); **Banner
      "OFFIZIELLE/VORLÄUFIGE RANGLISTE" oben entfernt**; Statistik-Block-Abstände gefixt (`&nbsp;` zwischen
      Label/Wert + `.stats-block td` horizontales Padding, da `table{width:100%}` das Box-Padding überrennt).
      Headless-Render: `flask_env`-Python + Test-Client `/live/preview_ranking_pdf/<eid>/<rid>?final=1`,
      Rastern mit `pymupdf` (neu in flask_env installiert). → **noch committen auf feature/ko-cup**.
- [ ] **Rangliste-PDF BUG — Fusszeile allein auf Seite 2** bei grossen Läufen (Large 3, 30+ Zeilen):
      Tabelle+Statistik passen auf Seite 1 (Ende y≈789/842pt), aber der `display:table`-Footer wird
      komplett auf Seite 2 geschoben (xhtml2pdf bricht display:table nicht um) → fast leere 2. Seite.
      User-Entscheid offen: Abstände enger / Footer als normaler Flow / akzeptieren.
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
