# blueprints/routes_master_data.py
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, abort
import uuid
import csv
import json
from io import StringIO
from utils import _load_data, _save_data, _decode_csv_file

master_bp = Blueprint('master_bp', __name__, template_folder='../templates', url_prefix='/master')

DOGS_FILE = 'dogs.json'
HANDLERS_FILE = 'handlers.json'
CLUBS_FILE = 'clubs.json'

# ------------------------------
# Hilfsfunktionen (rein logisch)
# ------------------------------
def _normalize_text(s):
    return (s or "").strip()

def _ensure_lists(d):
    return d if isinstance(d, list) else []

def _get_club_map():
    clubs = _ensure_lists(_load_data(CLUBS_FILE))
    # erlauben sowohl {"nummer": "...", "name": "..."} als auch {"Nummer": "...", "Name": "..."}
    out = {}
    for c in clubs:
        nr = c.get('nummer') or c.get('Nummer') or ""
        name = c.get('name') or c.get('Name') or ""
        if str(nr).strip():
            out[str(nr).strip()] = name.strip()
    return out

def _handler_display_name(h):
    return f"{_normalize_text(h.get('Vorname'))} {_normalize_text(h.get('Nachname'))}".strip()

def _validate_handler(data, clubs_map):
    errors = []
    vorname = _normalize_text(data.get('Vorname'))
    nachname = _normalize_text(data.get('Nachname'))
    vereinsnummer = _normalize_text(data.get('Vereinsnummer'))
    if not vorname:
        errors.append("Vorname fehlt.")
    if not nachname:
        errors.append("Nachname fehlt.")
    if vereinsnummer and vereinsnummer not in clubs_map:
        errors.append(f"Vereinsnummer '{vereinsnummer}' existiert nicht.")
    return errors

def _validate_dog(data, handlers):
    errors = []
    liz = _normalize_text(data.get('Lizenznummer'))
    hundename = _normalize_text(data.get('Hundename'))
    handler_id = _normalize_text(data.get('Hundefuehrer_ID'))
    kategorie = _normalize_text(data.get('Kategorie'))
    klasse = _normalize_text(data.get('Klasse'))
    if not liz:
        errors.append("Lizenznummer fehlt.")
    if not hundename:
        errors.append("Hundename fehlt.")
    if not handler_id:
        errors.append("Hundeführer-ID fehlt.")
    else:
        if not any(h.get('id') == handler_id for h in handlers):
            errors.append("Hundeführer-ID verweist auf keinen existierenden Hundeführer.")
    if kategorie and kategorie not in ["Small", "Medium", "Intermediate", "Large"]:
        errors.append(f"Ungültige Kategorie '{kategorie}'.")
    if klasse and str(klasse) not in ["1", "2", "3", "Oldie"]:
        errors.append(f"Ungültige Klasse '{klasse}'.")
    return errors

def _relink_orphans(dogs, handlers):
    """Entfernt/verlinkt inkonsistente Referenzen:
       - Hunde ohne existierenden Hundeführer -> handler_id auf '' setzen.
       - Duplikate von Lizenznummern zusammenführen (erste gewinnt, spätere werden ignoriert)."""
    handler_ids = {h.get('id') for h in handlers}
    seen_licenses = set()
    cleaned = []
    for d in dogs:
        liz = _normalize_text(d.get('Lizenznummer'))
        if liz in seen_licenses:
            # Duplikat lizenznummer -> überspringen (später evtl. smarter mergen)
            continue
        seen_licenses.add(liz)
        if d.get('Hundefuehrer_ID') not in handler_ids:
            d['Hundefuehrer_ID'] = ''
        cleaned.append(d)
    return cleaned

def _sort_handlers(handlers):
    return sorted(handlers, key=lambda h: (_normalize_text(h.get('Nachname')).lower(), _normalize_text(h.get('Vorname')).lower()))

def _sort_dogs(dogs, handlers):
    handler_map = {h.get('id'): _handler_display_name(h) for h in handlers}
    return sorted(dogs, key=lambda d: (
        handler_map.get(d.get('Hundefuehrer_ID'), "zzzz").lower(),
        _normalize_text(d.get('Hundename')).lower()
    ))

# ------------------------------
# Übersicht
# ------------------------------
@master_bp.route('/')
def master_data():
    handlers = _ensure_lists(_load_data(HANDLERS_FILE))
    dogs = _ensure_lists(_load_data(DOGS_FILE))
    clubs_map = _get_club_map()
    # Konsistenz prüfen (Anzeigehinweis)
    missing_handler_refs = [d for d in dogs if d.get('Hundefuehrer_ID') and not any(h.get('id') == d.get('Hundefuehrer_ID') for h in handlers)]
    duplicate_licenses = {}
    for d in dogs:
        key = _normalize_text(d.get('Lizenznummer'))
        if not key:
            continue
        duplicate_licenses[key] = duplicate_licenses.get(key, 0) + 1
    duplicate_licenses = {k: v for k, v in duplicate_licenses.items() if v > 1}
    return render_template(
        'master_data.html',
        handlers=_sort_handlers(handlers),
        dogs=_sort_dogs(dogs, handlers),
        clubs_map=clubs_map,
        missing_handler_refs=len(missing_handler_refs),
        duplicate_licenses=duplicate_licenses
    )

# ------------------------------
# Hundeführer: Create/Update/Delete
# ------------------------------
@master_bp.route('/handler/new', methods=['GET', 'POST'])
def handler_new():
    clubs_map = _get_club_map()
    if request.method == 'POST':
        handlers = _ensure_lists(_load_data(HANDLERS_FILE))
        data = {
            'id': str(uuid.uuid4()),
            'Vorname': _normalize_text(request.form.get('Vorname')),
            'Nachname': _normalize_text(request.form.get('Nachname')),
            'Vereinsnummer': _normalize_text(request.form.get('Vereinsnummer')),
        }
        errors = _validate_handler(data, clubs_map)
        if errors:
            for e in errors: flash(e, 'danger')
            return render_template('master_data_item_form.html', item=data, item_type='handler', clubs_map=clubs_map, is_edit=False)

        handlers.append(data)
        _save_data(HANDLERS_FILE, handlers)
        flash('Hundeführer angelegt.', 'success')
        return redirect(url_for('master_bp.master_data'))
    return render_template('master_data_item_form.html', item={}, item_type='handler', clubs_map=clubs_map, is_edit=False)

@master_bp.route('/handler/edit/<handler_id>', methods=['GET', 'POST'])
def handler_edit(handler_id):
    handlers = _ensure_lists(_load_data(HANDLERS_FILE))
    handler = next((h for h in handlers if h.get('id') == handler_id), None)
    if not handler:
        abort(404)
    clubs_map = _get_club_map()
    if request.method == 'POST':
        updated = {
            'id': handler['id'],
            'Vorname': _normalize_text(request.form.get('Vorname')),
            'Nachname': _normalize_text(request.form.get('Nachname')),
            'Vereinsnummer': _normalize_text(request.form.get('Vereinsnummer')),
        }
        errors = _validate_handler(updated, clubs_map)
        if errors:
            for e in errors: flash(e, 'danger')
            return render_template('master_data_item_form.html', item=updated, item_type='handler', clubs_map=clubs_map, is_edit=True)

        # Update in place
        for k, v in updated.items():
            handler[k] = v
        _save_data(HANDLERS_FILE, handlers)
        flash('Hundeführer aktualisiert.', 'success')
        return redirect(url_for('master_bp.master_data'))
    return render_template('master_data_item_form.html', item=handler, item_type='handler', clubs_map=clubs_map, is_edit=True)

@master_bp.route('/handler/delete/<handler_id>', methods=['POST'])
def handler_delete(handler_id):
    handlers = _ensure_lists(_load_data(HANDLERS_FILE))
    dogs = _ensure_lists(_load_data(DOGS_FILE))
    if not any(h.get('id') == handler_id for h in handlers):
        abort(404)
    # Hunde, die auf diesen Handler zeigen, „entkoppeln“ statt löschen
    for d in dogs:
        if d.get('Hundefuehrer_ID') == handler_id:
            d['Hundefuehrer_ID'] = ''
    handlers = [h for h in handlers if h.get('id') != handler_id]
    _save_data(HANDLERS_FILE, handlers)
    _save_data(DOGS_FILE, dogs)
    flash('Hundeführer gelöscht. Zugehörige Hunde wurden entkoppelt.', 'success')
    return redirect(url_for('master_bp.master_data'))

# ------------------------------
# Hunde: Create/Update/Delete
# ------------------------------
@master_bp.route('/dog/new', methods=['GET', 'POST'])
def dog_new():
    handlers = _ensure_lists(_load_data(HANDLERS_FILE))
    if request.method == 'POST':
        dogs = _ensure_lists(_load_data(DOGS_FILE))
        data = {
            'Lizenznummer': _normalize_text(request.form.get('Lizenznummer')),
            'Hundename': _normalize_text(request.form.get('Hundename')),
            'Hundefuehrer_ID': _normalize_text(request.form.get('Hundefuehrer_ID')),
            'Kategorie': _normalize_text(request.form.get('Kategorie')),
            'Klasse': _normalize_text(request.form.get('Klasse')),
        }
        errors = _validate_dog(data, handlers)
        if any(d.get('Lizenznummer') == data['Lizenznummer'] for d in dogs):
            errors.append("Lizenznummer ist bereits vorhanden.")
        if errors:
            for e in errors: flash(e, 'danger')
            return render_template('master_data_item_form.html', item=data, item_type='dog', handlers=handlers, is_edit=False)

        dogs.append(data)
        _save_data(DOGS_FILE, dogs)
        flash('Hund angelegt.', 'success')
        return redirect(url_for('master_bp.master_data'))
    return render_template('master_data_item_form.html', item={}, item_type='dog', handlers=handlers, is_edit=False)

@master_bp.route('/dog/edit/<license_nr>', methods=['GET', 'POST'])
def dog_edit(license_nr):
    dogs = _ensure_lists(_load_data(DOGS_FILE))
    handlers = _ensure_lists(_load_data(HANDLERS_FILE))
    dog = next((d for d in dogs if d.get('Lizenznummer') == license_nr), None)
    if not dog:
        abort(404)
    if request.method == 'POST':
        updated = {
            'Lizenznummer': _normalize_text(request.form.get('Lizenznummer') or dog.get('Lizenznummer')),
            'Hundename': _normalize_text(request.form.get('Hundename')),
            'Hundefuehrer_ID': _normalize_text(request.form.get('Hundefuehrer_ID')),
            'Kategorie': _normalize_text(request.form.get('Kategorie')),
            'Klasse': _normalize_text(request.form.get('Klasse')),
        }
        errors = _validate_dog(updated, handlers)
        # Falls Lizenznummer geändert wurde, auf Kollision prüfen
        if updated['Lizenznummer'] != dog.get('Lizenznummer'):
            if any(d.get('Lizenznummer') == updated['Lizenznummer'] for d in dogs):
                errors.append("Neue Lizenznummer ist bereits vergeben.")
        if errors:
            for e in errors: flash(e, 'danger')
            return render_template('master_data_item_form.html', item=updated, item_type='dog', handlers=handlers, is_edit=True)

        # in place aktualisieren
        if updated['Lizenznummer'] != dog.get('Lizenznummer'):
            # Primärschlüssel-„Wechsel“: Objekt austauschen
            dogs = [d for d in dogs if d is not dog]
            dogs.append(updated)
        else:
            for k, v in updated.items():
                dog[k] = v

        _save_data(DOGS_FILE, dogs)
        flash('Hund aktualisiert.', 'success')
        return redirect(url_for('master_bp.master_data'))
    return render_template('master_data_item_form.html', item=dog, item_type='dog', handlers=handlers, is_edit=True)

@master_bp.route('/dog/delete/<license_nr>', methods=['POST'])
def dog_delete(license_nr):
    dogs = _ensure_lists(_load_data(DOGS_FILE))
    if not any(d.get('Lizenznummer') == license_nr for d in dogs):
        abort(404)
    dogs = [d for d in dogs if d.get('Lizenznummer') != license_nr]
    _save_data(DOGS_FILE, dogs)
    flash('Hund gelöscht.', 'success')
    return redirect(url_for('master_bp.master_data'))

# ------------------------------
# CSV-Import (Hundeführer/Hunde)
# ------------------------------
@master_bp.route('/import', methods=['GET', 'POST'])
def master_import():
    if request.method == 'POST':
        file = request.files.get('csv_file')
        if not file or file.filename == '':
            flash('Keine Datei ausgewählt.', 'warning')
            return redirect(url_for('master_bp.master_import'))
        content = _decode_csv_file(file)
        if content is None:
            return redirect(url_for('master_bp.master_data'))

        handlers = _ensure_lists(_load_data(HANDLERS_FILE))
        dogs = _ensure_lists(_load_data(DOGS_FILE))
        clubs_map = _get_club_map()

        # flexible Spalten: lower + strip
        reader = csv.DictReader(StringIO(content), delimiter=';')
        reader.fieldnames = [f.lower().strip() for f in reader.fieldnames]

        # unterstützte Felder
        # Hundeführer: hf-vorname, hf-name, hf-verein (Name oder Nummer)
        # Hund: h-lizenz, h-name, h-kategorie, h-kl-eingabe
        added_h = 0
        added_d = 0
        updated_h = 0
        updated_d = 0

        # Map für Hundeführer nach "vorname nachname"
        existing_handlers = {f"{_normalize_text(h.get('Vorname')).lower()} {_normalize_text(h.get('Nachname')).lower()}": h for h in handlers}
        # Map für Hunde nach Lizenznummer
        existing_dogs = { _normalize_text(d.get('Lizenznummer')): d for d in dogs }

        for row in reader:
            # Hundeführer
            hf_vor = _normalize_text(row.get('hf-vorname'))
            hf_nach = _normalize_text(row.get('hf-name'))
            if hf_vor or hf_nach:
                key = f"{hf_vor.lower()} {hf_nach.lower()}".strip()
                verein_raw = _normalize_text(row.get('hf-verein'))
                vereinsnummer = ""
                if verein_raw:
                    # Verein kann Name oder Nummer sein
                    if verein_raw in _get_club_map():
                        vereinsnummer = verein_raw
                    else:
                        # Name -> Nummer suchen (case-insensitive)
                        inv = { (v or "").lower(): k for k, v in _get_club_map().items() }
                        vereinsnummer = inv.get(verein_raw.lower(), "")
                if key in existing_handlers:
                    h = existing_handlers[key]
                    # nur aktualisieren, wenn etwas geliefert ist
                    changed = False
                    if vereinsnummer and h.get('Vereinsnummer') != vereinsnummer:
                        h['Vereinsnummer'] = vereinsnummer
                        changed = True
                    if changed:
                        updated_h += 1
                else:
                    new_h = {
                        'id': str(uuid.uuid4()),
                        'Vorname': hf_vor,
                        'Nachname': hf_nach,
                        'Vereinsnummer': vereinsnummer
                    }
                    handlers.append(new_h)
                    existing_handlers[key] = new_h
                    added_h += 1

            # Hund
            liz = _normalize_text(row.get('h-lizenz'))
            name = _normalize_text(row.get('h-name'))
            kat = _normalize_text(row.get('h-kategorie'))
            kl = _normalize_text(row.get('h-kl-eingabe'))

            handler_obj = existing_handlers.get(f"{hf_vor.lower()} {hf_nach.lower()}") if (hf_vor or hf_nach) else None
            handler_id = handler_obj.get('id') if handler_obj else ''

            if liz or name:
                if liz in existing_dogs:
                    d = existing_dogs[liz]
                    changed = False
                    if name and d.get('Hundename') != name:
                        d['Hundename'] = name; changed = True
                    if handler_id and d.get('Hundefuehrer_ID') != handler_id:
                        d['Hundefuehrer_ID'] = handler_id; changed = True
                    if kat and d.get('Kategorie') != kat:
                        d['Kategorie'] = kat; changed = True
                    if kl and str(d.get('Klasse')) != str(kl):
                        d['Klasse'] = kl; changed = True
                    if changed:
                        updated_d += 1
                else:
                    new_d = {
                        'Lizenznummer': liz,
                        'Hundename': name,
                        'Hundefuehrer_ID': handler_id,
                        'Kategorie': kat,
                        'Klasse': kl
                    }
                    dogs.append(new_d)
                    existing_dogs[liz] = new_d
                    added_d += 1

        # Konsistenz
        dogs = _relink_orphans(dogs, handlers)
        _save_data(HANDLERS_FILE, handlers)
        _save_data(DOGS_FILE, dogs)
        flash(f"Import abgeschlossen: {added_h} neue Hundeführer (+{updated_h} aktualisiert), {added_d} neue Hunde (+{updated_d} aktualisiert).", "success")
        return redirect(url_for('master_bp.master_data'))

    # GET: simple Upload-Seite wiederverwenden
    return render_template('master_data.html', import_mode=True,
                           handlers=_ensure_lists(_load_data(HANDLERS_FILE)),
                           dogs=_ensure_lists(_load_data(DOGS_FILE)),
                           clubs_map=_get_club_map(),
                           missing_handler_refs=0, duplicate_licenses={})

# ------------------------------
# Reparatur & Diagnose
# ------------------------------
@master_bp.route('/repair', methods=['POST'])
def master_repair():
    handlers = _ensure_lists(_load_data(HANDLERS_FILE))
    dogs = _ensure_lists(_load_data(DOGS_FILE))
    before_orphans = sum(1 for d in dogs if d.get('Hundefuehrer_ID') and not any(h.get('id') == d.get('Hundefuehrer_ID') for h in handlers))
    dogs = _relink_orphans(dogs, handlers)
    _save_data(DOGS_FILE, dogs)
    flash(f"Reparatur ausgeführt. {before_orphans} verwaiste Hunde-Verknüpfungen bereinigt.", "info")
    return redirect(url_for('master_bp.master_data'))

# ------------------------------
# API (z. B. für JS-Formular-Autocomplete)
# ------------------------------
@master_bp.route('/api/handlers')
def api_handlers():
    handlers = _ensure_lists(_load_data(HANDLERS_FILE))
    out = [
        {'id': h.get('id'), 'name': _handler_display_name(h), 'Vereinsnummer': h.get('Vereinsnummer', '')}
        for h in _sort_handlers(handlers)
    ]
    return jsonify(out)

@master_bp.route('/api/dogs')
def api_dogs():
    handlers = _ensure_lists(_load_data(HANDLERS_FILE))
    handler_map = {h.get('id'): _handler_display_name(h) for h in handlers}
    dogs = _ensure_lists(_load_data(DOGS_FILE))
    out = [
        {
            'Lizenznummer': d.get('Lizenznummer'),
            'Hundename': d.get('Hundename'),
            'Hundefuehrer_ID': d.get('Hundefuehrer_ID'),
            'Hundefuehrer': handler_map.get(d.get('Hundefuehrer_ID'), ''),
            'Kategorie': d.get('Kategorie', ''),
            'Klasse': d.get('Klasse', '')
        }
        for d in _sort_dogs(dogs, handlers)
    ]
    return jsonify(out)
