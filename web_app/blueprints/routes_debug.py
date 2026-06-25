# blueprints/routes_debug.py
import json
import os
import random
import math
import uuid

from flask import Blueprint, Response, redirect, url_for, flash, abort, request
from utils import _load_data, _save_data, _load_settings, _to_float, debug_tools_enabled

debug_bp = Blueprint('debug_bp', __name__)

# Routes, die NICHT vom Debug-Toggle betroffen sind (legitimer Export für Vergleich/Portal).
_DEBUG_GATE_EXEMPT = {'debug_bp.export_event_package'}


@debug_bp.before_request
def _gate_debug_tools():
    """Sperrt Debug-Generatoren/Test-Importe wenn ENABLE_DEBUG_TOOLS=0 (Produktion)."""
    if request.endpoint in _DEBUG_GATE_EXEMPT:
        return
    if not debug_tools_enabled():
        abort(404)


def _project_data_path(*parts) -> str:
    """Pfad innerhalb von web_app/data/..."""
    here = os.path.dirname(os.path.abspath(__file__))
    web_app = os.path.dirname(here)
    return os.path.join(web_app, 'data', *parts)


# ---------------------------------------------------------------------------
# FMBB-Test-Event-Generator
# ---------------------------------------------------------------------------

FMBB_DEMO_BREEDS_BELG = ["Berger belge Malinois", "Belgischer Schäferhund Tervueren",
                         "Berger belge Groenendael", "Malinois"]
FMBB_DEMO_BREEDS_OTHER = ["Border Collie", "Australian Shepherd", "Sheltie",
                           "Jack Russell Terrier", "Mischling", "Papillon"]


def _make_demo_entry(lic: int, kategorie: str, klasse: str,
                     is_belgier: bool, is_fmbb_marked: bool) -> dict:
    """Eine Demo-Anmeldung mit Lizenz, Hund, Hundeführer."""
    breed = (random.choice(FMBB_DEMO_BREEDS_BELG) if is_belgier
             else random.choice(FMBB_DEMO_BREEDS_OTHER))
    return {
        "Startnummer":  None,
        "Lizenznummer": str(lic),
        "Hundename":    f"DemoHund{lic}",
        "Rasse":        breed,
        "Kategorie":    kategorie,
        "Klasse":       klasse,
        "Vorname":      f"Vorname{lic}",
        "Nachname":     f"Nachname{lic}",
        "is_fmbb":      is_fmbb_marked,
        "result":       {},
    }


@debug_bp.route('/debug/generate_fmbb_test_event')
def generate_fmbb_test_event():
    """
    Erzeugt ein vollständiges FMBB-Demo-Event:
      - Veranstaltungsart "SKBS-SM" (für Doppelnutzungs-Demo)
      - fmbb_quali_active = True
      - Pro Kategorie S/M/I/L und Klasse 2,3 je 1 Agility + 1 Jumping = 16 Läufe
      - 8 Teilnehmer pro Lauf, davon 30% Belgier mit is_fmbb=True und
        weitere ~10% Belgier ohne FMBB-Markierung (Edge-Case)
      - Anschliessend Resultate generieren via bestehende Funktion
    """
    events = _load_data('events.json')

    # Lizenz-Pool: gleiche Hunde nehmen ggf. mehrere Anmeldungen
    # Wir generieren einen Pool und ziehen für jeden Lauf eine Stichprobe daraus.
    licence_pool = list(range(20001, 20081))  # 80 Hunde
    random.shuffle(licence_pool)

    # 30% Belgier-Pool, der is_fmbb=True ist (offizielle SKBS-Anmeldung)
    fmbb_licences = set(licence_pool[:24])
    # 10% weitere Belgier, die NICHT FMBB-angemeldet sind (Filter-Edge-Case)
    other_belgier_licences = set(licence_pool[24:32])

    runs = []
    for kategorie in ["Small", "Medium", "Intermediate", "Large"]:
        for klasse in ["2", "3"]:
            # Stichprobe Teilnehmer für diese Klassen-Kombination
            sample_size = 8
            sample = random.sample(licence_pool, sample_size)

            for laufart in ["Agility", "Jumping"]:
                entries = []
                for lic in sample:
                    is_fmbb_marked = lic in fmbb_licences
                    is_belgier = is_fmbb_marked or lic in other_belgier_licences
                    entries.append(_make_demo_entry(lic, kategorie, klasse,
                                                    is_belgier, is_fmbb_marked))

                runs.append({
                    "id":         uuid.uuid4().hex,
                    "name":       f"{laufart} {kategorie} K{klasse}",
                    "kategorie":  kategorie,
                    "klasse":     klasse,
                    "laufart":    laufart,
                    "richter_id": "",
                    "laufdaten":  {},
                    "entries":    entries,
                })

    event_id = uuid.uuid4().hex
    new_event = {
        "id":                  event_id,
        "Bezeichnung":         "FMBB-Demo Münsingen (Generator)",
        "Datum":               "2026-12-05",
        "Veranstaltungsart":   "SKBS-SM",
        "fmbb_quali_active":   True,
        "runs":                runs,
        "skbs_sm_config":      {},
    }

    events.append(new_event)
    _save_data('events.json', events)

    # Resultate generieren via bestehende Funktion-Logik (inline, da generate_test_results
    # mit Redirect arbeitet — wir nutzen die gleiche Logik direkt)
    settings = _load_settings()
    for run in new_event['runs']:
        laenge = random.randint(150, 220)
        hindernisse = random.randint(18, 22)
        run['laufdaten']['parcours_laenge'] = laenge
        run['laufdaten']['anzahl_hindernisse'] = hindernisse
        speed = settings.get('sct_factors', {}).get(run['laufart'], {}).get(run['klasse'], 3.5)
        sct = laenge / speed
        run['laufdaten']['standardzeit_sct'] = round(sct, 2)
        for entry in run['entries']:
            if random.random() < 0.1:
                entry['result'] = {'disqualifikation': random.choice(['DIS', 'ABR'])}
                continue
            zeit = round(random.uniform(sct - 5, sct + 15), 2)
            fehler = random.choice([0, 0, 0, 1, 1, 2]) if random.random() < 0.4 else 0
            verweigerungen = 1 if random.random() < 0.15 else 0
            entry['result'] = {
                'zeit':             f"{zeit:.2f}",
                'fehler':           fehler,
                'verweigerungen':   verweigerungen,
                'disqualifikation': None,
            }
    _save_data('events.json', events)

    flash(
        f"FMBB-Demo-Event erstellt: '{new_event['Bezeichnung']}' "
        f"({len(runs)} Läufe, {sum(len(r['entries']) for r in runs)} Anmeldungen, "
        f"{sum(1 for r in runs for e in r['entries'] if e.get('is_fmbb'))} FMBB-markiert). "
        f"Resultate generiert.",
        "success",
    )
    return redirect(url_for('events_bp.manage_runs', event_id=event_id))

@debug_bp.route('/debug/generate_results/<event_id>')
def generate_test_results(event_id):
    events = _load_data('events.json')
    event = next((e for e in events if e.get('id') == event_id), None)
    if not event: abort(404)
    settings = _load_settings()
    for run in event.get('runs', []):
        if run.get('laufart') in ['Pause', 'Umbau', 'Briefing', 'Vorbereitung', 'Grossring']: continue
        laufdaten = run.get('laufdaten', {})
        laenge = _to_float(laufdaten.get('parcours_laenge'), 0.0) or random.randint(150, 220)
        hindernisse = int(laufdaten.get('anzahl_hindernisse', 0)) or random.randint(18, 22)
        run['laufdaten']['parcours_laenge'] = laenge
        run['laufdaten']['anzahl_hindernisse'] = hindernisse
        klasse = str(run.get('klasse'))
        laufart = run.get('laufart')
        raw_sct = laufdaten.get('standardzeit_sct')
        sct = _to_float(raw_sct, None)
        if sct is None:
            if klasse in ['1', 'Oldie']:
                sct = laenge / 2.8
            elif klasse in ['2', '3']:
                speed = settings.get('sct_factors', {}).get(laufart, {}).get(klasse, 3.5)
                sct = laenge / speed
            else:
                sct = laenge / 3.0
        run['laufdaten']['standardzeit_sct'] = round(sct, 2)
        for entry in run.get('entries', []):
            if random.random() < 0.1:
                entry['result'] = {'disqualifikation': random.choice(['DIS', 'ABR'])}
                continue
            zeit = round(random.uniform(sct - 5, sct + 15), 2)
            fehler = 0
            if random.random() < 0.4: fehler = random.choice([1, 1, 2])
            verweigerungen = 0
            if random.random() < 0.15: verweigerungen = 1
            entry['result'] = {
                'zeit': f"{zeit:.2f}",
                'fehler': fehler,
                'verweigerungen': verweigerungen,
                'disqualifikation': None
            }
    _save_data('events.json', events)
    flash(f"Test-Resultate für das Event '{event.get('Bezeichnung')}' wurden erfolgreich generiert.", "success")
    return redirect(url_for('events_bp.manage_runs', event_id=event_id))


# ---------------------------------------------------------------------------
# Aaretaler-Demo-Event aus echten PDF-Startlisten
# ---------------------------------------------------------------------------

@debug_bp.route('/debug/generate_aaretaler_demo')
def generate_aaretaler_demo_event():
    """
    Lädt die echten Startlisten der Aaretaler-Veranstaltung 20.06.2026 aus
    data/test_data/aaretaler_startlists.json und erzeugt ein vollständiges
    Test-Event mit:
      - Veranstaltungsart "SKBS-SM" (für Doppelnutzungs-Demo SKBS+FMBB)
      - fmbb_quali_active=True
      - Pro Klasse 1/2/3 × Kategorie S/M/I/L × Lauf Agi/Jump → bis zu 24 Läufe
      - Echte Teilnehmer (Lizenznummern, Hund, Rasse) aus den PDFs
      - 20% der Klasse-2/3-Teams werden mit is_fmbb=True markiert (Demo)
      - Resultate generiert
    """
    data_path = _project_data_path('test_data', 'aaretaler_startlists.json')
    if not os.path.isfile(data_path):
        flash(f"Test-Daten nicht gefunden: {data_path}. "
              f"Bitte tools/parse_startlists.py ausführen.", "danger")
        return redirect(url_for('events_bp.events_list'))

    with open(data_path, encoding='utf-8') as f:
        data = json.load(f)

    events = _load_data('events.json')

    # Sammle alle FMBB-Kandidaten (Klasse 2+3) für die Markierung später
    fmbb_candidate_licenses: list[str] = []
    for klasse in ('2', '3'):
        for cat_entries in data['classes'].get(klasse, {}).values():
            for e in cat_entries:
                fmbb_candidate_licenses.append(e['lizenz'])

    # 20% der Kandidaten zufällig als FMBB markieren (Demo)
    random.seed(20260620)   # deterministisch für reproduzierbare Demo
    fmbb_count = max(1, int(len(fmbb_candidate_licenses) * 0.20))
    fmbb_marked = set(random.sample(fmbb_candidate_licenses, fmbb_count))

    # Saturday-Zeitplan (siehe Bild 20./21. Juni 2026)
    # Mapping (klasse, laufart) → (start_at, judge_id)
    JUDGE_GLUR  = "2477"   # Philipp Glur (in judges.json bereits vorhanden)
    JUDGE_BEITL = "8146"   # Alex Beitl
    SCHEDULE = {
        ("1", "Jumping"): ("08:00", JUDGE_GLUR),
        ("1", "Agility"): ("09:05", JUDGE_BEITL),
        ("1", "Open"):    ("09:50", JUDGE_BEITL),   # 2nd chance
        ("2", "Agility"): ("10:45", JUDGE_GLUR),
        ("3", "Agility"): ("12:20", JUDGE_GLUR),
        ("2", "Jumping"): ("14:50", JUDGE_BEITL),
        ("3", "Jumping"): ("16:25", JUDGE_BEITL),
    }

    # Pro Klasse × Kategorie × Lauf einen Run anlegen.
    # Klasse 1 hat zusätzlich 'Open' (2nd Chance).
    runs = []
    for klasse, by_cat in data['classes'].items():
        for kategorie in ('Small', 'Medium', 'Intermediate', 'Large'):
            cat_entries = by_cat.get(kategorie, [])
            if not cat_entries:
                continue
            laufarten = ('Agility', 'Jumping', 'Open') if klasse == '1' else ('Agility', 'Jumping')
            for laufart in laufarten:
                _, judge_id = SCHEDULE.get((klasse, laufart), ("", ""))
                entries = []
                for src in cat_entries:
                    lic = src['lizenz']
                    parts = src['name'].split(' ', 1)
                    vorname = parts[1] if len(parts) > 1 else ''
                    nachname = parts[0]
                    entries.append({
                        'Startnummer':           src['snr'],
                        'startnummer_offiziell': src['snr'],   # UI liest dieses Feld
                        'Lizenznummer':          lic,
                        'Hundename':             src['hund'] or f"Hund_{lic}",
                        'Hundefuehrer':          f"{vorname} {nachname}".strip(),
                        'Rasse':                 src['rasse'] or '',
                        'Kategorie':             kategorie,
                        'Klasse':                klasse,
                        'Vorname':               vorname,
                        'Nachname':              nachname,
                        'registriert':           True,    # Demo: alle als bestätigt
                        'is_fmbb':               lic in fmbb_marked,
                        'result':                {},
                    })
                runs.append({
                    'id':         uuid.uuid4().hex,
                    'name':       f"{laufart} {kategorie} K{klasse}",
                    'kategorie':  kategorie,
                    'klasse':     klasse,
                    'laufart':    laufart,
                    'judge_id':   judge_id,
                    'richter_id': judge_id,
                    'laufdaten':  {},
                    'entries':    entries,
                })

    # Zeitplan-Blöcke (1 Ring, alle Kategorien pro Klasse+Lauf in einem Block)
    blocks = []
    for (klasse, laufart), (start_at, judge_id) in SCHEDULE.items():
        # Block nur erzeugen wenn die Klasse Daten hat
        if klasse not in data['classes']:
            continue
        blocks.append({
            'id':              f"blk_{uuid.uuid4().hex[:8]}",
            'type':            'run',
            'title':           f"{laufart} – Klasse {klasse}",
            'run_format':      'normal',
            'timing_run_type': laufart.lower(),
            'size_category':   '',
            'size_categories': ['Small', 'Medium', 'Intermediate', 'Large'],
            'classes':         [klasse],
            'judge_id':        judge_id,
            'sort': {
                'primary':   {'field': 'startnummer', 'direction': 'asc'},
                'secondary': {'field': 'none', 'direction': 'asc'},
            },
            'estimated': {
                'participants_total': 0,
                'changeover_seconds': 0,
                'briefing_seconds':   0,
                'prep_pause_seconds': 0,
                'run_seconds':        0,
                'total_seconds':      0,
            },
            'notes':    '',
            'start_at': start_at,
        })
    # Nach start_at sortieren
    blocks.sort(key=lambda b: b['start_at'])

    schedule_data = {
        'rings': {
            '1': {'start_time': '07:30', 'blocks': blocks},
        },
        'meta': {
            'last_updated': '',
            'updated_by':   'aaretaler_demo_generator',
        },
    }

    event_id = uuid.uuid4().hex
    external_id = uuid.uuid4().hex
    new_event = {
        'id':                  event_id,
        'external_id':         external_id,        # für Portal-Sync (ResultExport)
        'Bezeichnung':         f"{data['event_name']} ({data['event_date']}) — Demo",
        'Datum':               data.get('event_date', '2026-06-20'),
        'Ort':                 data.get('event_location', ''),
        'Veranstaltungsart':   'SKBS-SM',
        'fmbb_quali_active':   True,
        'num_rings':           1,
        'start_times_by_ring': {'ring_1': '07:30'},
        'runs':                runs,
        'schedule':            schedule_data,
        'skbs_sm_config':      {},
    }
    # Lauf-Stammdaten (Parcourslaenge / SCT) trotzdem belegen, damit der
    # User morgen direkt Resultate eintragen kann ohne erst manuell SCT
    # setzen zu muessen. Aber KEINE result-Dicts auf entries — diese fuellt
    # der User morgen ein (oder via Live-Mode).
    settings = _load_settings()
    for run in new_event['runs']:
        laenge = random.randint(150, 220)
        hindernisse = random.randint(18, 22)
        run['laufdaten']['parcours_laenge'] = laenge
        run['laufdaten']['anzahl_hindernisse'] = hindernisse
        speed = settings.get('sct_factors', {}).get(run['laufart'], {}).get(run['klasse'], 3.5)
        sct = laenge / speed
        run['laufdaten']['standardzeit_sct'] = round(sct, 2)
        # entries bleiben absichtlich ohne 'result' (leer)

    events.append(new_event)
    _save_data('events.json', events)

    total_entries = sum(len(r['entries']) for r in runs)
    total_fmbb = sum(1 for r in runs for e in r['entries'] if e.get('is_fmbb'))
    flash(
        f"Aaretaler-Demo-Event erstellt: '{new_event['Bezeichnung']}' "
        f"({len(runs)} Läufe, {total_entries} Anmeldungen, "
        f"{total_fmbb} FMBB-markiert). Resultate noch leer — bitte manuell eintragen.",
        "success",
    )
    # Portal-Sync-Hinweis: Damit ResultExport ans Portal funktioniert, muss
    # dort ein Event mit derselben external_id existieren (is_test=True,
    # nicht öffentlich). Anlegen via:
    flash(
        f"Portal-Sync vorbereiten (optional): external_id={external_id}. "
        f"Auf dem Portal aufrufen: "
        f"/admin/exchange/debug/ensure_test_event/{external_id}?key=<admin-key>",
        "info",
    )
    return redirect(url_for('events_bp.manage_runs', event_id=event_id))


# ---------------------------------------------------------------------------
# Event-Package-Export als ZIP (für Portal-Import)
# ---------------------------------------------------------------------------

@debug_bp.route('/debug/export_event_package/<event_id>')
def export_event_package(event_id):
    """
    Lädt das angegebene Event als eventexport.v1.zip herunter.
    Diese Datei kann dann im Portal unter /admin/exchange/event-package/import
    hochgeladen werden — das Portal erstellt/aktualisiert das Event idempotent.
    """
    from portal_sync import build_event_export_zip

    events = _load_data('events.json')
    event = next((e for e in events if e.get('id') == event_id), None)
    if not event:
        abort(404)

    zip_bytes = build_event_export_zip(event)
    from utils import _safe_http_filename
    safe_name = _safe_http_filename(event.get('Bezeichnung') or event_id)
    filename = f"eventexport_{safe_name}.zip"
    return Response(
        zip_bytes,
        mimetype='application/zip',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'},
    )
