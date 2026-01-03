# blueprints/routes_events.py
from flask import Blueprint, render_template, request, redirect, url_for, flash, Response, jsonify, abort
import json
import uuid
import random
from io import StringIO
import csv
from datetime import date, datetime

from utils import (
    _load_data, _save_data, _decode_csv_file, _get_active_event_id,
    _get_concrete_run_list, _place_entries_with_distance,
    _load_settings, _calculate_timelines, get_category_sort_key, _recalculate_schedule_estimates
)
import planner.schedule_planner as schedule_planner

events_bp = Blueprint('events_bp', __name__, template_folder='../templates', url_prefix='/events')

# Daten-Dateien
EVENTS_FILE   = 'events.json'
DOGS_FILE     = 'dogs.json'
HANDLERS_FILE = 'handlers.json'
CLUBS_FILE    = 'clubs.json'
JUDGES_FILE   = 'judges.json'


# =========================================
#   Helfer: Normalisierung & CSV-Handling
# =========================================

def _norm(s: str) -> str:
    return (s or "").replace("\ufeff", "").strip()

def _lc(s: str) -> str:
    return _norm(s).lower()

CSV_ALIASES = {
    "h-kl-eingabe": {"h kl eingabe", "h-kl-eingabe", "klasse"},
    "h-lizenz":     {"h lizenz", "h-lizenz", "lizenz", "lizenznummer"},
    "h-name":       {"h name", "h-name", "hundename"},
    "hf-name":      {"hf name", "hf-name"},
    "hf-vorname":   {"hf vorname", "hf-vorname"},
    "h-kategorie":  {"h kategorie", "h-kategorie"},
    # optional
    "hf-verein":    {"hf verein", "hf-verein", "verein"},
    "hf-vereinnr":  {"hf vereinnr", "hf-vereinnr", "vereinnr", "vereinsnummer"},
}

def _normalize_header_name(name: str) -> str:
    return " ".join(_lc(name).replace("_", " ").replace("-", " ").split())

def _build_header_map(fieldnames):
    found = {}
    raw = [_normalize_header_name(f) for f in (fieldnames or [])]
    for key, aliases in CSV_ALIASES.items():
        hit = None
        for f in raw:
            if f in aliases:
                hit = f
                break
        if hit:
            found[key] = hit
    return found

def _sniff_delimiter(sample: str) -> str:
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=";,")
        return dialect.delimiter or ';'
    except Exception:
        return "," if (sample.count(",") > 0 and sample.count(";") == 0) else ";"


def _safe_update(target: dict, key: str, new_value: str):
    v = _norm(new_value)
    if v != "":
        target[key] = v

def _fullname_key(vor: str, nach: str) -> str:
    return f"{_lc(vor)} {_lc(nach)}".strip()


# =========================================
#   Helfer: Stammdaten-Bereinigung
# =========================================

def _is_event_obj(obj: dict) -> bool:
    return isinstance(obj, dict) and ("runs" in obj or "Bezeichnung" in obj)

def _is_dog_obj(obj: dict) -> bool:
    return isinstance(obj, dict) and ("Lizenznummer" in obj or "Hundename" in obj)

def _is_handler_obj(obj: dict) -> bool:
    return isinstance(obj, dict) and ("Vorname" in obj or "Nachname" in obj or "Vereinsnummer" in obj)

def _sanitize_master_data_lists(dogs_list, handlers_list):
    clean_dogs = []
    for d in dogs_list or []:
        if _is_event_obj(d):
            continue
        if _is_dog_obj(d):
            if "Lizenznummer" in d:
                d["Lizenznummer"] = _norm(d.get("Lizenznummer"))
            if "Klasse" in d:
                d["Klasse"] = str(d.get("Klasse"))
            clean_dogs.append(d)

    clean_handlers = []
    for h in handlers_list or []:
        if _is_event_obj(h):
            continue
        if _is_handler_obj(h):
            clean_handlers.append(h)

    return clean_dogs, clean_handlers

def _sanitize_and_save_master_data(dogs, handlers):
    clean_dogs, clean_handlers = _sanitize_master_data_lists(dogs, handlers)
    _save_data(DOGS_FILE, clean_dogs)
    _save_data(HANDLERS_FILE, clean_handlers)
    return len(dogs) - len(clean_dogs), len(handlers) - len(clean_handlers)


# =========================================
#   Helfer: Ring-Normalisierung
# =========================================

def _norm_ring(val, num_rings: int = 1):
    if val is None or val == "":
        return "ring_1" if num_rings == 1 else None
    if isinstance(val, int):
        idx = val
    else:
        s = _lc(str(val))
        s = s.replace("ring_", "").replace("ring", "").strip()
        try:
            idx = int(s)
        except ValueError:
            if str(val).startswith("ring_"):
                return str(val)
            return None
    if idx < 1:
        return None
    return f"ring_{idx}"

def _norm_ring_strict(val, default_one=True):
    s = ("" if val is None else str(val)).strip()
    if not s:
        return "ring_1" if default_one else None
    low = s.lower().strip()
    low = low.replace("ring ", "").replace("ring_", "").replace("ring", "").strip()
    try:
        n = int(low)
        return f"ring_{n}" if n >= 1 else ("ring_1" if default_one else None)
    except Exception:
        if s.startswith("ring_"):
            return s
        return "ring_1" if default_one else None


# =======================
#   Event-CRUD / Basics
# =======================

@events_bp.route('/')
def events_list():
    events = _load_data(EVENTS_FILE)
    active_id = _get_active_event_id()
    return render_template('events_list.html', events=events, active_event_id=active_id)

@events_bp.route('/create', methods=['GET', 'POST'])
def create_event():
    if request.method == 'POST':
        settings = _load_settings()
        num_rings = int(request.form.get('num_rings', 1))
        start_times = {f"ring_{i}": request.form.get(f"start_time_ring_{i}", '07:30') for i in range(1, num_rings + 1)}
        new_event = {
            "id": str(uuid.uuid4()),
            "Bezeichnung": request.form.get('bezeichnung'),
            "Datum": request.form.get('datum'),
            "VeranstalterClubNr": request.form.get('veranstalter_club_nr'),
            "Turniernummer": request.form.get('turniernummer'),
            "num_rings": num_rings,
            "Veranstaltungsart": request.form.get('veranstaltungsart'),
            "start_times_by_ring": start_times,
            "runs": [],
            "run_order": [],
            "start_number_schema": settings.get('start_number_schema_template', {})
        }
        for la in request.form.getlist('laufart_auto'):
            for kat in request.form.getlist('kategorien_verfuegbar'):
                for kl in request.form.getlist('klassen_verfuegbar'):
                    new_run = {
                        "id": str(uuid.uuid4()),
                        "name": f"{la} {kat} {kl}",
                        "laufart": la,
                        "kategorie": kat,
                        "klasse": kl,
                        "entries": [],
                        "laufdaten": {}
                    }
                    new_event['runs'].append(new_run)
        events = _load_data(EVENTS_FILE)
        events.append(new_event)
        _save_data(EVENTS_FILE, events)
        flash(f"Veranstaltung '{new_event['Bezeichnung']}' erfolgreich erstellt.", "success")
        return redirect(url_for('events_bp.manage_runs', event_id=new_event['id']))
    return render_template(
        'event_form.html',
        form_title="Neue Veranstaltung erstellen",
        clubs=_load_data(CLUBS_FILE),
        event={},
        today=date.today().isoformat(),
        is_edit=False,
        event_types=["Meeting", "Meisterschaft"],
        possible_classes=["1", "2", "3", "Oldie"],
        possible_categories=["Small", "Medium", "Intermediate", "Large"]
    )

@events_bp.route('/edit/<event_id>', methods=['GET', 'POST'])
def edit_event(event_id):
    events = _load_data(EVENTS_FILE)
    event = next((e for e in events if e.get('id') == event_id), None)
    if not event:
        flash("Event nicht gefunden.", "error")
        return redirect(url_for('events_bp.events_list'))
    if request.method == 'POST':
        num_rings = int(request.form.get('num_rings', 1))
        event.update({
            'Bezeichnung': request.form.get('bezeichnung'),
            'Datum': request.form.get('datum'),
            'VeranstalterClubNr': request.form.get('veranstalter_club_nr'),
            'Turniernummer': request.form.get('turniernummer'),
            'num_rings': num_rings,
            'Veranstaltungsart': request.form.get('veranstaltungsart')
        })
        event['start_times_by_ring'] = {f"ring_{i}": request.form.get(f"start_time_ring_{i}") for i in range(1, num_rings + 1)}
        _save_data(EVENTS_FILE, events)
        flash("Veranstaltung erfolgreich aktualisiert.", "success")
        return redirect(url_for('events_bp.events_list'))
    return render_template('event_form.html',
                           form_title="Veranstaltung bearbeiten",
                           event=event,
                           clubs=_load_data(CLUBS_FILE),
                           is_edit=True,
                           event_types=["Meeting", "Meisterschaft"])

@events_bp.route('/delete/<event_id>', methods=['POST'])
def delete_event(event_id):
    events = [e for e in _load_data(EVENTS_FILE) if e.get('id') != event_id]
    _save_data(EVENTS_FILE, events)
    if _get_active_event_id() == event_id:
        _save_data('active_event.json', {})
    flash("Veranstaltung wurde gelöscht.", "success")
    return redirect(url_for('events_bp.events_list'))

@events_bp.route('/set_active/<event_id>')
def set_active_event(event_id):
    _save_data('active_event.json', {'active_event_id': event_id})
    flash("Event als 'Live' markiert.", "success")
    return redirect(url_for('live_bp.live_event_dashboard'))

@events_bp.route('/clear_active')
def clear_active_event():
    _save_data('active_event.json', {})
    flash("Kein Event mehr als 'Live' markiert.", "info")
    return redirect(url_for('events_bp.events_list'))


# =======================
#   Läufe verwalten
# =======================

@events_bp.route('/manage_runs/<event_id>')
def manage_runs(event_id):
    event = next((e for e in _load_data(EVENTS_FILE) if e.get('id') == event_id), None)
    if not event:
        return redirect(url_for('events_bp.events_list'))
    judges = _load_data(JUDGES_FILE)
    return render_template('manage_runs.html', event=event, judges=judges)

@events_bp.route('/edit_run/<event_id>/<uuid:run_id>', methods=['GET', 'POST'])
def edit_run(event_id, run_id):
    run_id = str(run_id)
    events = _load_data(EVENTS_FILE)
    event = next((e for e in events if e.get('id') == event_id), None)
    run = next((r for r in event.get('runs', []) if r.get('id') == run_id), None)
    if not event or not run:
        return redirect(url_for('events_bp.events_list'))
    if request.method == 'POST':
        run.update({'name': request.form.get('name'), 'richter_id': request.form.get('richter_id')})
        laufdaten = run.get('laufdaten', {})
        laufdaten.update({
            'parcours_laenge': request.form.get('parcours_laenge'),
            'anzahl_hindernisse': request.form.get('anzahl_hindernisse')
        })
        if run.get('klasse') in ['1', 'Oldie']:
            laufdaten['sct_direkt'] = request.form.get('sct_method') == 'direct'
            laufdaten['standardzeit_sct'] = request.form.get('standardzeit_sct') if laufdaten['sct_direkt'] else ''
            laufdaten['geschwindigkeit'] = request.form.get('geschwindigkeit') if not laufdaten['sct_direkt'] else ''
        run['laufdaten'] = laufdaten
        _save_data(EVENTS_FILE, events)
        return redirect(url_for('events_bp.manage_runs', event_id=event_id))
    return render_template('run_form.html', event=event, run=run, judges=_load_data(JUDGES_FILE))

# NEU: Echte Lauf-spezifische Teilnehmerverwaltung
@events_bp.route('/manage_run_participants/<event_id>/<uuid:run_id>', methods=['GET', 'POST'])
def manage_run_participants(event_id, run_id):
    run_id = str(run_id)
    events = _load_data(EVENTS_FILE)
    event = next((e for e in events if e.get('id') == event_id), None)
    if not event:
        abort(404)
    run = next((r for r in event.get('runs', []) if r.get('id') == run_id), None)
    if not run:
        abort(404)

    dogs = [d for d in _load_data(DOGS_FILE) if isinstance(d, dict) and d.get('Lizenznummer')]
    handler_map = {h['id']: h for h in _load_data(HANDLERS_FILE) if isinstance(h, dict) and h.get('id')}

    # Liste aller passenden Hunde (gleiche Kat/Klasse)
    eligible_dogs = []
    for d in dogs:
        if _norm(d.get('Kategorie')) == _norm(run.get('kategorie')) and str(d.get('Klasse')) == str(run.get('klasse')):
            h = handler_map.get(d.get('Hundefuehrer_ID'))
            label = f"{(h.get('Vorname','')+' '+h.get('Nachname','')).strip()} mit {d.get('Hundename','')} ({d.get('Lizenznummer')})" if h else f"{d.get('Hundename','')} ({d.get('Lizenznummer')})"
            eligible_dogs.append({"license": d.get('Lizenznummer'), "label": label})

    # Bereits zugeordnete Teilnehmer
    assigned = run.get('entries', [])
    assigned_sorted = sorted(assigned, key=lambda x: (x.get('Startnummer') is None, x.get('Startnummer', 99999)))

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'add_by_license':
            lic = _norm(request.form.get('license_nr'))
            if not lic:
                flash("Lizenznummer fehlt.", "warning")
                return redirect(url_for('events_bp.manage_run_participants', event_id=event_id, run_id=run_id))

            dog = next((d for d in dogs if _norm(d.get('Lizenznummer')) == lic), None)
            if not dog:
                flash("Hund nicht gefunden.", "error")
                return redirect(url_for('events_bp.manage_run_participants', event_id=event_id, run_id=run_id))

            # nur wenn Kat/Klasse passt
            if _norm(dog.get('Kategorie')) != _norm(run.get('kategorie')) or str(dog.get('Klasse')) != str(run.get('klasse')):
                flash("Kategorie/Klasse passt für diesen Lauf nicht.", "warning")
                return redirect(url_for('events_bp.manage_run_participants', event_id=event_id, run_id=run_id))

            if any(p.get('Lizenznummer') == lic for p in run.get('entries', [])):
                flash("Teilnehmer ist bereits in diesem Lauf.", "info")
                return redirect(url_for('events_bp.manage_run_participants', event_id=event_id, run_id=run_id))

            h = handler_map.get(dog.get('Hundefuehrer_ID'))
            handler_full = f"{h.get('Vorname','')} {h.get('Nachname','')}".strip() if h else "Unbekannt"
            run.setdefault('entries', []).append({
                "Lizenznummer": lic,
                "Hundename": dog.get('Hundename'),
                "Hundefuehrer": handler_full
            })
            _save_data(EVENTS_FILE, events)
            flash("Teilnehmer hinzugefügt.", "success")
            return redirect(url_for('events_bp.manage_run_participants', event_id=event_id, run_id=run_id))

        if action == 'remove':
            lic = _norm(request.form.get('license_nr'))
            before = len(run.get('entries', []))
            run['entries'] = [p for p in run.get('entries', []) if _norm(p.get('Lizenznummer')) != lic]
            after = len(run.get('entries', []))
            _save_data(EVENTS_FILE, events)
            flash("Teilnehmer entfernt." if after < before else "Teilnehmer war nicht in diesem Lauf.", "info")
            return redirect(url_for('events_bp.manage_run_participants', event_id=event_id, run_id=run_id))

        if action == 'set_start_last':
            # Checkboxen "start_last_<license>"
            for p in run.get('entries', []):
                key = f"start_last_{p.get('Lizenznummer')}"
                p['start_last'] = request.form.get(key) == 'on'
            _save_data(EVENTS_FILE, events)
            flash("Einstellungen gespeichert.", "success")
            return redirect(url_for('events_bp.manage_run_participants', event_id=event_id, run_id=run_id))

        if action == 'assign_number':
            lic = _norm(request.form.get('license_nr'))
            num = request.form.get('new_start_number')
            if not (num and num.isdigit()):
                flash("Ungültige Startnummer.", "warning")
                return redirect(url_for('events_bp.manage_run_participants', event_id=event_id, run_id=run_id))
            num = int(num)
            if any(e.get('Startnummer') == num for e in run.get('entries', [])):
                flash("Startnummer in diesem Lauf bereits vergeben.", "error")
                return redirect(url_for('events_bp.manage_run_participants', event_id=event_id, run_id=run_id))
            found = next((e for e in run.get('entries', []) if _norm(e.get('Lizenznummer')) == lic), None)
            if found:
                found['Startnummer'] = num
                _save_data(EVENTS_FILE, events)
                flash("Startnummer gesetzt.", "success")
            else:
                flash("Teilnehmer nicht gefunden.", "error")
            return redirect(url_for('events_bp.manage_run_participants', event_id=event_id, run_id=run_id))

    return render_template('manage_run_participants.html',
                           event=event,
                           run=run,
                           eligible_dogs=sorted(eligible_dogs, key=lambda x: x['label'].lower()),
                           assigned_participants=assigned_sorted)


@events_bp.route('/import_participants/<event_id>', methods=['GET', 'POST'])
def import_participants(event_id):
    events = _load_data(EVENTS_FILE)
    event = next((e for e in events if e.get('id') == event_id), None)
    if not event:
        flash("Event nicht gefunden.", "error")
        return redirect(url_for('events_bp.events_list'))

    if request.method == 'POST':
        file = request.files.get('participant_file')
        if not file or file.filename == '':
            flash('Keine Datei ausgewählt.', 'warning')
            return redirect(request.url)

        content = _decode_csv_file(file)
        if content is None:
            return redirect(url_for('events_bp.manage_runs', event_id=event_id))

        try:
            sample = content[:4096]
            delimiter = _sniff_delimiter(sample)

            reader = csv.DictReader(StringIO(content), delimiter=delimiter)
            reader.fieldnames = [_normalize_header_name(f) for f in (reader.fieldnames or [])]
            header_map = _build_header_map(reader.fieldnames)

            required = {"h-lizenz", "h-name", "hf-vorname", "hf-name", "h-kategorie", "h-kl-eingabe"}
            if not required.issubset(header_map.keys()):
                needed = ", ".join(sorted(required))
                found = ", ".join(reader.fieldnames or [])
                flash(
                    f"Fehlende Spalten in der Teilnehmer-CSV. Benötigt: {needed}. "
                    f"Gefunden: {found}. Erkanntes Trennzeichen: '{delimiter}'.",
                    "danger"
                )
                return redirect(url_for('events_bp.manage_runs', event_id=event_id))

            dogs_raw     = _load_data(DOGS_FILE)
            handlers_raw = _load_data(HANDLERS_FILE)
            dogs, handlers = _sanitize_master_data_lists(dogs_raw, handlers_raw)

            clubs = _load_data(CLUBS_FILE)
            dog_by_license    = { _norm(d.get('Lizenznummer')): d for d in dogs if _norm(d.get('Lizenznummer')) }
            handler_by_full   = { _fullname_key(h.get('Vorname'), h.get('Nachname')): h for h in handlers }
            clubs_by_name_lc  = { _lc(c.get('name')): c.get('nummer') for c in clubs if c.get('name') }

            entries_added = 0
            dogs_created, dogs_updated = 0, 0
            handlers_created, handlers_updated = 0, 0

            def val(row, key):
                col = header_map.get(key)
                return _norm(row.get(col) if col else "")

            for row in reader:
                lic    = val(row, "h-lizenz")
                dname  = val(row, "h-name")
                hvn    = val(row, "hf-vorname")
                hnn    = val(row, "hf-name")
                kat    = val(row, "h-kategorie")
                kl     = val(row, "h-kl-eingabe")
                verein = val(row, "hf-verein")
                vnr    = val(row, "hf-vereinnr")

                if not lic or not hvn or not hnn:
                    continue

                hk = _fullname_key(hvn, hnn)
                handler = handler_by_full.get(hk)
                if not handler:
                    handler = {
                        'id': str(uuid.uuid4()),
                        'Vorname': hvn,
                        'Nachname': hnn,
                        'Vereinsnummer': ''
                    }
                    if vnr:
                        handler['Vereinsnummer'] = vnr
                    elif verein:
                        looked = clubs_by_name_lc.get(_lc(verein), '')
                        if looked:
                            handler['Vereinsnummer'] = looked
                    handlers.append(handler)
                    handler_by_full[hk] = handler
                    handlers_created += 1
                else:
                    _safe_update(handler, 'Vorname', hvn)
                    _safe_update(handler, 'Nachname', hnn)
                    if vnr:
                        _safe_update(handler, 'Vereinsnummer', vnr)
                    elif verein:
                        looked = clubs_by_name_lc.get(_lc(verein), '')
                        if looked:
                            _safe_update(handler, 'Vereinsnummer', looked)
                    handlers_updated += 1

                handler_id = handler['id']

                dog = dog_by_license.get(lic)
                if not dog:
                    dog = {
                        'Lizenznummer': lic,
                        'Hundename': dname or lic,
                        'Hundefuehrer_ID': handler_id,
                        'Kategorie': kat,
                        'Klasse': str(kl)
                    }
                    dogs.append(dog)
                    dog_by_license[lic] = dog
                    dogs_created += 1
                else:
                    _safe_update(dog, 'Hundename', dname)
                    _safe_update(dog, 'Kategorie', kat)
                    if 'Klasse' in dog:
                        _safe_update(dog, 'Klasse', str(kl))
                    else:
                        dog['Klasse'] = str(kl)
                    if _norm(dog.get('Hundefuehrer_ID')) != handler_id:
                        dog['Hundefuehrer_ID'] = handler_id
                    dogs_updated += 1

                show_handler = f"{handler.get('Vorname','').strip()} {handler.get('Nachname','').strip()}".strip()
                show_dog = dog.get('Hundename') or dname or lic

                for run in event.get('runs', []):
                    if ( _norm(run.get('kategorie')) == _norm(dog.get('Kategorie') or kat) and
                         str(run.get('klasse')) == str(dog.get('Klasse') or kl) ):
                        existing = next((p for p in run.get('entries', []) if p.get('Lizenznummer') == lic), None)
                        if existing:
                            existing['Hundename'] = show_dog
                            existing['Hundefuehrer'] = show_handler
                        else:
                            run.setdefault('entries', []).append({
                                "Lizenznummer": lic,
                                "Hundename": show_dog,
                                "Hundefuehrer": show_handler
                            })
                            entries_added += 1

            _sanitize_and_save_master_data(dogs, handlers)
            _save_data(EVENTS_FILE, events)

            flash(
                f"{entries_added} Teilnahmen hinzugefügt. "
                f"Hunde: +{dogs_created}/↑{dogs_updated}, "
                f"Hundeführer: +{handlers_created}/↑{handlers_updated}.",
                "success"
            )
        except Exception as e:
            flash(f"Ein Fehler ist aufgetreten: {e}", "error")

        return redirect(url_for('events_bp.manage_runs', event_id=event_id))

    return render_template('import_participants_event.html', event=event)


@events_bp.route('/repair_master_data')
def repair_master_data():
    dogs_raw = _load_data(DOGS_FILE)
    handlers_raw = _load_data(HANDLERS_FILE)
    removed_dogs, removed_handlers = 0, 0
    if isinstance(dogs_raw, list) and isinstance(handlers_raw, list):
        before_d = len(dogs_raw)
        before_h = len(handlers_raw)
        _sanitize_and_save_master_data(dogs_raw, handlers_raw)
        after_d = len(_load_data(DOGS_FILE))
        after_h = len(_load_data(HANDLERS_FILE))
        removed_dogs = before_d - after_d
        removed_handlers = before_h - after_h
    flash(f"Stammdaten bereinigt. Entfernt: Hunde={removed_dogs}, Hundeführer={removed_handlers}.", "success")
    return redirect(url_for('events_bp.events_list'))


@events_bp.route('/manage_all_participants/<event_id>', methods=['GET', 'POST'])
def manage_all_participants(event_id):
    events = _load_data(EVENTS_FILE)
    event = next((e for e in events if e.get('id') == event_id), None)
    if not event:
        abort(404)

    if request.method == 'POST':
        if request.form.get('action') == 'add_participant':
            license_nr = request.form.get('license_number')
            dog = next((d for d in _load_data(DOGS_FILE) if d.get('Lizenznummer') == license_nr), None)
            if dog:
                handler = next((h for h in _load_data(HANDLERS_FILE) if h.get('id') == dog.get('Hundefuehrer_ID')), None)
                handler_fullname = f"{handler.get('Vorname','')} {handler.get('Nachname','')}".strip() if handler else "Unbekannt"
                added_count = 0
                for run in event.get('runs', []):
                    if run.get('kategorie') == dog.get('Kategorie') and str(run.get('klasse')) == str(dog.get('Klasse')) and not any(p.get('Lizenznummer') == license_nr for p in run.get('entries', [])):
                        run['entries'].append({"Lizenznummer": license_nr, "Hundename": dog.get('Hundename'), "Hundefuehrer": handler_fullname})
                        added_count += 1
                _save_data(EVENTS_FILE, events)
                flash(f"Teilnehmer zu {added_count} Läufen hinzugefügt.", "success")
            else:
                flash("Hund nicht gefunden.", "error")

        if request.form.get('save_start_last'):
            start_last_licenses = request.form.getlist('start_last')
            for run in event.get('runs', []):
                for p in run.get('entries', []):
                    p['start_last'] = p.get('Lizenznummer') in start_last_licenses
            _save_data(EVENTS_FILE, events)
            flash("Option 'Startet am Schluss' gespeichert.", "success")

        return redirect(url_for('events_bp.manage_all_participants', event_id=event_id))

    all_entries = {p['Lizenznummer']: p for r in event.get('runs', []) for p in r.get('entries', [])}.values()
    assigned = sorted([p for p in all_entries if p.get('Startnummer')], key=lambda x: x.get('Startnummer', 0))
    unassigned = sorted([p for p in all_entries if not p.get('Startnummer')], key=lambda x: x.get('Hundefuehrer', '').lower())
    dogs_data = _load_data(DOGS_FILE)
    handler_map = {h['id']: h for h in _load_data(HANDLERS_FILE)}
    all_dogs_with_handlers = []
    for d in dogs_data:
        h = handler_map.get(d.get('Hundefuehrer_ID'))
        if h:
            all_dogs_with_handlers.append({
                'license': d.get('Lizenznummer'),
                'name': f"{h.get('Vorname','')} {h.get('Nachname','')} mit {d.get('Hundename','')} ({d.get('Lizenznummer','')})".strip()
            })
    return render_template('manage_all_participants.html', event=event, assigned_participants=assigned, unassigned_participants=unassigned, all_dogs_with_handlers=all_dogs_with_handlers)


@events_bp.route('/assign_start_number/<event_id>', methods=['POST'])
def assign_start_number(event_id):
    events = _load_data(EVENTS_FILE)
    event = next((e for e in events if e.get('id') == event_id), None)
    if not event:
        abort(404)
    license_nr = request.form.get('license_nr')
    new_start_number = request.form.get('new_start_number')
    if not new_start_number or not new_start_number.isdigit():
        flash("Ungültige Startnummer.", "error")
    else:
        new_start_number = int(new_start_number)
        is_taken = any(p.get('Startnummer') == new_start_number for r in event.get('runs', []) for p in r.get('entries', []))
        if is_taken:
            flash(f"Startnummer {new_start_number} ist bereits vergeben.", "error")
        else:
            found = False
            for run in event.get('runs', []):
                for p in run.get('entries', []):
                    if p.get('Lizenznummer') == license_nr:
                        p['Startnummer'] = new_start_number
                        found = True
            if found:
                _save_data(EVENTS_FILE, events)
                flash(f"Startnummer {new_start_number} wurde zugewiesen.", "success")
            else:
                flash("Teilnehmer nicht gefunden.", "error")
    return redirect(url_for('events_bp.manage_all_participants', event_id=event_id))


@events_bp.route('/swap_start_numbers/<event_id>', methods=['POST'])
def swap_start_numbers(event_id):
    events = _load_data(EVENTS_FILE)
    event = next((e for e in events if e.get('id') == event_id), None)
    if not event:
        abort(404)
    num1_str = request.form.get('swap_num1')
    num2_str = request.form.get('swap_num2')
    if not (num1_str and num2_str and num1_str.isdigit() and num2_str.isdigit()):
        flash("Ungültige Eingabe. Bitte nur Zahlen eingeben.", "error")
        return redirect(url_for('events_bp.manage_all_participants', event_id=event_id))
    num1, num2 = int(num1_str), int(num2_str)
    lic1, lic2 = None, None
    all_participants = {p['Lizenznummer']: p for r in event.get('runs', []) for p in r.get('entries', []) if p.get('Startnummer')}
    for lic, p_data in all_participants.items():
        if p_data.get('Startnummer') == num1:
            lic1 = lic
        if p_data.get('Startnummer') == num2:
            lic2 = lic
    if lic1 and lic2:
        for run in event.get('runs', []):
            for p in run.get('entries', []):
                if p.get('Lizenznummer') == lic1:
                    p['Startnummer'] = num2
                elif p.get('Lizenznummer') == lic2:
                    p['Startnummer'] = num1
        _save_data(EVENTS_FILE, events)
        flash(f"Startnummern {num1} und {num2} wurden erfolgreich getauscht.", "success")
    else:
        flash("Eine oder beide Startnummern wurden nicht gefunden.", "error")
    return redirect(url_for('events_bp.manage_all_participants', event_id=event_id))


# =========================
#   Zeitplan & Startnummer
# =========================

@events_bp.route('/plan_schedule/<event_id>')
def plan_schedule(event_id):
    event = next((e for e in _load_data(EVENTS_FILE) if e.get('id') == event_id), None)
    if not event:
        return redirect(url_for('events_bp.events_list'))
    settings = _load_settings()
    start_times_by_ring = event.get('start_times_by_ring', {}) or {}
    schedule = schedule_planner.ensure_schedule_root(event_id, event.get('num_rings', 1), start_times_by_ring, event.get('schedule'))
    schedule = schedule_planner.ensure_run_titles(schedule)
    schedule['meta']['updated_by'] = 'system'
    event['schedule'] = schedule
    event['start_times_by_ring'] = {f"ring_{k}": v.get('start_time', '07:30') for k, v in (schedule.get('rings') or {}).items()}
    _recalculate_schedule_estimates(event, schedule, settings)
    timelines_by_ring = _calculate_timelines(event)
    unique_participants = {}
    dog_map = {d['Lizenznummer']: d for d in _load_data(DOGS_FILE) if isinstance(d, dict) and d.get('Lizenznummer')}
    all_entries_with_start_num = [entry for run in event.get('runs', []) for entry in run.get('entries', []) if entry.get('Startnummer')]
    for entry in all_entries_with_start_num:
        license_nr = entry.get('Lizenznummer')
        if license_nr and license_nr not in unique_participants:
            details = entry.copy()
            dog_info = dog_map.get(license_nr, {})
            details['Kategorie'], details['Klasse'] = dog_info.get('Kategorie'), dog_info.get('Klasse')
            unique_participants[license_nr] = details
    preview_list = sorted(unique_participants.values(), key=lambda x: int(x.get('Startnummer', 9999)))
    laufarten = sorted(list(set(r['laufart'] for r in event.get('runs', []))))
    kategorien = sorted(list(set(r['kategorie'] for r in event.get('runs', []))), key=get_category_sort_key)
    klassen = sorted(list(set(str(r['klasse']) for r in event.get('runs', []))))
    # Robust gegen ältere Datenstrukturen, damit das Richter-Dropdown gefüllt wird
    judges_raw = _load_data(JUDGES_FILE) or []
    judges = []
    for j in judges_raw:
        if not isinstance(j, dict):
            continue
        judges.append({
            'id': j.get('id'),
            'firstname': j.get('firstname') or j.get('vorname') or j.get('Vorname'),
            'lastname': j.get('lastname') or j.get('nachname') or j.get('Nachname'),
        })
    return render_template('plan_schedule.html',
                           event=event,
                           laufarten=laufarten,
                           kategorien=kategorien,
                           klassen=klassen,
                           judges=judges,
                           possible_classes=["1", "2", "3", "Oldie"],
                           possible_categories=["Small", "Medium", "Intermediate", "Large"],
                           num_rings=event.get('num_rings', 1),
                           preview_list=preview_list,
                           timelines_by_ring=timelines_by_ring,
                           schedule=schedule,
                           rank_announcement_default=settings.get('schedule_planning', {}).get('rank_announcement_default_seconds', 300))

@events_bp.route('/save_schedule/<event_id>', methods=['POST'])
def save_schedule(event_id):
    events = _load_data(EVENTS_FILE)
    event = next((e for e in events if e.get('id') == event_id), None)
    if not event:
        flash("Event nicht gefunden.", "error")
        return redirect(url_for('events_bp.events_list'))

    form_data = request.form.to_dict()

    # Startzeiten pro Ring speichern
    start_times = event.get('start_times_by_ring', {}) or {}
    for key, value in form_data.items():
        if key.startswith('start_time_ring_'):
            ring_key = key.replace('start_time_ring_', 'ring_')
            start_times[ring_key] = value
    event['start_times_by_ring'] = start_times

    schedule_raw = (form_data.get('schedule_json') or form_data.get('run_order_data') or "").strip()
    schedule_payload = None
    if schedule_raw:
        try:
            parsed = json.loads(schedule_raw)
            if isinstance(parsed, dict):
                schedule_payload = parsed
        except Exception:
            schedule_payload = None

    num_rings = event.get('num_rings', 1)
    settings = _load_settings()
    schedule_data = schedule_planner.ensure_schedule_root(event_id, num_rings, start_times, schedule_payload or event.get('schedule'))
    schedule_data = schedule_planner.ensure_run_titles(schedule_data)
    schedule_data['meta']['last_updated'] = datetime.utcnow().isoformat()
    schedule_data['meta']['updated_by'] = 'user'
    _recalculate_schedule_estimates(event, schedule_data, settings)

    event['schedule'] = schedule_data
    event['start_times_by_ring'] = start_times
    event['run_order'] = []

    _save_data(EVENTS_FILE, events)
    flash("Zeitplan erfolgreich gespeichert.", "success")
    return redirect(url_for('events_bp.plan_schedule', event_id=event_id))


@events_bp.route('/save_schema/<event_id>', methods=['POST'])
def save_schema(event_id):
    events = _load_data(EVENTS_FILE)
    event = next((e for e in events if e['id'] == event_id), None)
    if event:
        schema = {k: int(v) for k, v in request.form.items() if v.isdigit()}
        event['start_number_schema'] = schema
        _save_data(EVENTS_FILE, events)
        flash("Startnummern-Schema erfolgreich gespeichert.", "success")
    return redirect(url_for('events_bp.plan_schedule', event_id=event_id))

@events_bp.route('/load_schema_template/<event_id>', methods=['POST'])
def load_schema_template(event_id):
    events = _load_data(EVENTS_FILE)
    event = next((e for e in events if e['id'] == event_id), None)
    if event:
        settings = _load_settings()
        event['start_number_schema'] = settings.get('start_number_schema_template', {})
        _save_data(EVENTS_FILE, events)
        flash("Startnummern-Schema aus Vorlage geladen.", "success")
    return redirect(url_for('events_bp.plan_schedule', event_id=event_id))

@events_bp.route('/generate_startlist/<event_id>', methods=['POST'])
def generate_startlist(event_id):
    events = _load_data(EVENTS_FILE)
    dogs = [d for d in _load_data(DOGS_FILE) if isinstance(d, dict) and d.get('Lizenznummer')]
    handler_map = {h['id']: h for h in _load_data(HANDLERS_FILE) if isinstance(h, dict) and h.get('id')}
    event = next((e for e in events if e.get('id') == event_id), None)
    if not event:
        return redirect(url_for('events_bp.events_list'))

    # vorhandene Startnummern löschen
    for run in event.get('runs', []):
        for entry in run.get('entries', []):
            if 'Startnummer' in entry:
                del entry['Startnummer']

    runs_in_schedule_order = _get_concrete_run_list(event)
    all_entries_in_schedule_order = [
        entry
        for run in runs_in_schedule_order
        if run.get('laufart') not in ['Pause', 'Umbau', 'Briefing', 'Vorbereitung', 'Grossring']
        for entry in run.get('entries', [])
    ]
    random.shuffle(all_entries_in_schedule_order)

    # handler_id anreichern (für Abstandslogik)
    dog_map = {d['Lizenznummer']: d for d in dogs}
    for entry in all_entries_in_schedule_order:
        lic = entry.get('Lizenznummer')
        d = dog_map.get(lic, {})
        hid = d.get('Hundefuehrer_ID')
        if hid:
            entry['handler_id'] = hid

    flash("Startreihenfolge wurde zufällig gemischt.", "info")

    handler_distance = int(request.form.get('handler_distance', 20))
    final_timeline = _place_entries_with_distance(all_entries_in_schedule_order, handler_distance)

    schema_counter = event.get('start_number_schema', {}).copy()
    if not schema_counter:
        flash("Fehler: Kein Startnummern-Schema definiert.", "error")
        return redirect(url_for('events_bp.plan_schedule', event_id=event_id))

    participant_number_map = {}
    unique_entries = {e['Lizenznummer']: e for e in final_timeline}.values()
    dog_map = {d['Lizenznummer']: d for d in dogs}

    for entry in unique_entries:
        license_nr = entry['Lizenznummer']
        dog_info = dog_map.get(license_nr, {})
        kategorie, klasse = dog_info.get('Kategorie'), str(dog_info.get('Klasse'))
        schema_key = f"{kategorie}-{klasse}" if kategorie and klasse else "Default"
        if schema_key in schema_counter:
            start_number = schema_counter[schema_key]
            participant_number_map[license_nr] = start_number
            schema_counter[schema_key] += 1
        else:
            participant_number_map[license_nr] = 9999

    for run in event.get('runs', []):
        for entry in run.get('entries', []):
            if entry['Lizenznummer'] in participant_number_map:
                entry['Startnummer'] = participant_number_map[entry['Lizenznummer']]

    _save_data(EVENTS_FILE, events)
    flash(f"{len(participant_number_map)} Startnummern erfolgreich vergeben.", "success")
    return redirect(url_for('events_bp.plan_schedule', event_id=event_id))


# =======================
#   Export / Import
# =======================

@events_bp.route('/export_package/<event_id>')
def export_event_package(event_id):
    event = next((e for e in _load_data(EVENTS_FILE) if e.get('id') == event_id), None)
    if not event:
        abort(404)
    return Response(json.dumps(event, indent=4, ensure_ascii=False),
                    mimetype="application/json",
                    headers={"Content-disposition": f"attachment; filename=event_package_{event_id}.json"})

@events_bp.route('/import_package', methods=['GET', 'POST'])
def import_event_package():
    if request.method == 'POST':
        file = request.files.get('package_file')
        if not file or file.filename == '':
            flash('Keine Datei ausgewählt.', 'warning')
            return redirect(request.url)
        try:
            imported_event = json.load(file)
            if 'id' not in imported_event or 'Bezeichnung' not in imported_event or 'runs' not in imported_event:
                flash('Die Datei scheint kein gültiges Event-Paket zu sein.', 'danger')
                return redirect(request.url)
            all_events = _load_data(EVENTS_FILE)
            imported_event['id'] = str(uuid.uuid4())
            imported_event['Bezeichnung'] = f"{imported_event['Bezeichnung']} (Importiert)"
            all_events.append(imported_event)
            _save_data(EVENTS_FILE, all_events)
            flash(f"Event '{imported_event['Bezeichnung']}' erfolgreich importiert.", 'success')
            return redirect(url_for('events_bp.events_list'))
        except Exception as e:
            flash(f'Fehler beim Importieren des Pakets: {e}', 'danger')
            return redirect(request.url)
    return render_template('import_package.html')


# =======================

@events_bp.route('/api/get_starter_count/<event_id>', methods=['POST'])
def get_starter_count(event_id):
    import math
    event = next((e for e in _load_data(EVENTS_FILE) if e.get('id') == event_id), None)
    if not event:
        return jsonify({"error": "Event not found"}), 404
    data = request.json
    runs_in_block = [
        r for r in event.get('runs', [])
        if (data.get('laufart') == 'Alle' or r.get('laufart') == data.get('laufart'))
        and (data.get('kategorie') == 'Alle' or r.get('kategorie') == data.get('kategorie'))
        and (data.get('klasse') == 'Alle' or str(r.get('klasse')) == str(data.get('klasse')))
    ]
    num_starters = sum(len(r.get('entries', [])) for r in runs_in_block)
    briefing_duration = math.ceil(num_starters / 50.0) * 10 if num_starters > 0 else 10
    return jsonify({"starter_count": num_starters, "briefing_duration": briefing_duration})

# === BEGIN apply_fix_0011 (AUTO-ADDED) ======================================
from flask import jsonify
# === BEGIN ring-api helpers (replaced cleanly) ===============================

@events_bp.route('/api/get_run_details/<event_id>/<run_id>', methods=['GET'])
def api_get_run_details(event_id, run_id):
    """Liefert die Entries eines Laufs für das Teilnehmer-UI (und zeigt Kat/Kl an)."""
    all_events = _load_data(EVENTS_FILE)
    event = next((e for e in all_events if isinstance(e, dict) and e.get('id') == event_id), None)
    if not event:
        return jsonify(success=False, message="Event nicht gefunden"), 404

    run = None
    for r in event.get('runs', []):
        if str(r.get('id')) == str(run_id):
            run = r
            break
    if not run:
        return jsonify(success=False, message="Lauf nicht gefunden"), 404

    entries = list(run.get('entries', []))

    # Kat/Kl pro Entry aus dogs.json ergänzen (falls vorhanden)
    try:
        dogs = [d for d in _load_data(DOGS_FILE) if isinstance(d, dict)]
        dog_map = { str(d.get('Lizenznummer')): d for d in dogs if d.get('Lizenznummer') }
        for e in entries:
            lic = str(e.get('Lizenznummer', '')).strip()
            dog = dog_map.get(lic)
            if dog:
                if 'Kategorie' not in e or not e.get('Kategorie'):
                    e['Kategorie'] = dog.get('Kategorie')
                if 'Klasse' not in e or not e.get('Klasse'):
                    e['Klasse'] = str(dog.get('Klasse')) if dog.get('Klasse') is not None else None
    except Exception:
        pass

    run_meta = {
        'laufart': run.get('laufart'),
        'kategorie': run.get('kategorie'),
        'klasse': run.get('klasse')
    }

    return jsonify(success=True, data={'entries': entries, 'run': run_meta})

@events_bp.route('/remove_participant_from_event/<event_id>/<license_nr>', methods=['POST'])
def remove_participant_from_event(event_id, license_nr):
    """Entfernt einen Teilnehmer aus ALLEN Läufen des Events und speichert."""
    event_data, source = _load_event_by_id(event_id)
    if not event_data:
        return jsonify(success=False, message="Event nicht gefunden"), 404

    removed_count = 0
    for r in event_data.get('runs', []):
        before = len(r.get('entries', []))
        r['entries'] = [e for e in r.get('entries', []) if str(e.get('Lizenznummer', '')) != str(license_nr)]
        removed_count += (before - len(r['entries']))

    _save_event_by_source(event_id, event_data, source)
    return jsonify(success=True, removed=removed_count)

def _load_event_by_id(event_id: str):
    """Versucht das Event zu laden (per-file oder zentrale Liste)."""
    from pathlib import Path
    PROJECT_ROOT = Path(__file__).resolve().parent
    per_file = PROJECT_ROOT / 'data' / 'events' / f'{event_id}.json'
    # 1) Direktdatei {id}.json
    if per_file.exists():
        try:
            with per_file.open('r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, dict) and data.get('id') == event_id:
                return data, 'per_file'
            if isinstance(data, list):
                for ev in data:
                    if isinstance(ev, dict) and ev.get('id') == event_id:
                        return ev, 'per_file_list'
        except Exception:
            pass

    # 2) Zentrales events.json
    events_json = PROJECT_ROOT / 'data' / 'events.json'
    if events_json.exists():
        try:
            with events_json.open('r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, list):
                for ev in data:
                    if isinstance(ev, dict) and ev.get('id') == event_id:
                        return ev, 'events_list'
            elif isinstance(data, dict) and data.get('id') == event_id:
                return data, 'events_json_dict'
        except Exception:
            pass

    # 3) Fallback: alle Dateien im Verzeichnis durchsuchen
    events_dir = PROJECT_ROOT / 'data' / 'events'
    if events_dir.exists() and events_dir.is_dir():
        for p in events_dir.glob('*.json'):
            try:
                with p.open('r', encoding='utf-8') as f:
                    data = json.load(f)
                if isinstance(data, dict) and data.get('id') == event_id:
                    return data, f'per_file({p.name})'
                if isinstance(data, list):
                    for ev in data:
                        if isinstance(ev, dict) and ev.get('id') == event_id:
                            return ev, f'per_file_list({p.name})'
            except Exception:
                continue
    return None, ''

def _save_event_by_source(event_id: str, event_obj: dict, source_flag: str) -> None:
    """Speichert das Event basierend auf seiner Quelle zurück."""
    from pathlib import Path
    PROJECT_ROOT = Path(__file__).resolve().parent
    events_dir = PROJECT_ROOT / 'data' / 'events'
    events_dir.mkdir(parents=True, exist_ok=True)
    events_json = PROJECT_ROOT / 'data' / 'events.json'

    def _write_json(p: Path, data):
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open('w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    if source_flag == 'per_file':
        _write_json(events_dir / f'{event_id}.json', event_obj)
        return
    if source_flag.startswith('per_file(') or source_flag.startswith('per_file_list('):
        name = source_flag[source_flag.find('(')+1: source_flag.rfind(')')]
        _write_json(events_dir / name, event_obj)
        return
    if source_flag == 'per_file_list':
        _write_json(events_dir / f'{event_id}.json', event_obj)
        return
    if source_flag == 'events_list':
        if events_json.exists():
            try:
                with events_json.open('r', encoding='utf-8') as f:
                    data = json.load(f)
                if isinstance(data, list):
                    for i, ev in enumerate(data):
                        if isinstance(ev, dict) and ev.get('id') == event_id:
                            data[i] = event_obj
                            _write_json(events_json, data)
                            return
            except Exception:
                pass
        _write_json(events_dir / f'{event_id}.json', event_obj)
        return
    if source_flag == 'events_json_dict':
        _write_json(events_json, event_obj)
        return

    # Default-Fallback
    _write_json(events_dir / f'{event_id}.json', event_obj)
# === END ring-api helpers ====================================================

@events_bp.route('/api/list_runs/<event_id>', methods=['GET'])
def api_list_runs(event_id):
    """Liste der Läufe für ein Event (optional nach Ring gefiltert). Query: ?ring=1 (oder ring_1)
    Antwort:
        {
          "success": true,
          "runs": [
            {"id": "...", "name": "...", "assigned_ring": "ring_1" | null}
          ]
        }
    """
    events = _load_data(EVENTS_FILE)
    event = next((e for e in events if e.get('id') == event_id), None)
    if not event:
        return jsonify(success=False, message='Event nicht gefunden'), 404

    ring_q = (request.args.get('ring') or '').strip()
    ring_key = ''
    if ring_q:
        try:
            ring_key = f"ring_{int(str(ring_q).replace('ring_', '').replace('ring','').strip())}"
        except Exception:
            ring_key = str(ring_q)

    out = []
    for r in event.get('runs', []):
        assigned = r.get('assigned_ring')
        assigned_key = _norm_ring(assigned, event.get('num_rings', 1)) if assigned else None or ''
        if ring_key and assigned and assigned != ring_key:
            continue
        out.append({
            'id': r.get('id'),
            'name': r.get('name') or f"{r.get('laufart','')} {r.get('kategorie','')} {r.get('klasse','')}",
            'assigned_ring': assigned or None
        })
    return jsonify(success=True, runs=out)

def _ring_label_for_display(ring_id: str) -> str:
    if not ring_id:
        return "Ring 1"
    part = ring_id.replace("ring_", "")
    return f"Ring {part}"
