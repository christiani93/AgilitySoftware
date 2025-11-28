# blueprints/routes_master_data.py
from flask import Blueprint, render_template, request, redirect, url_for, flash
from utils import _load_data, _save_data, _decode_csv_file
import uuid
from io import StringIO
import csv

master_data_bp = Blueprint('master_data_bp', __name__, template_folder='../templates')

# Dateinamen als Konstanten
CLUBS_FILE = 'clubs.json'
DOGS_FILE = 'dogs.json'
HANDLERS_FILE = 'handlers.json'
JUDGES_FILE = 'judges.json'

# Datenmodell-Konfiguration für die gesamte Anwendung
DATA_CONFIG = {
    'clubs': {'file': CLUBS_FILE, 'title': 'Vereine', 'fields': {'nummer': 'Nummer', 'name': 'Name'}, 'id_field': 'nummer', 'import_info': 'Spalten: Nr;Name. Ersetzt alle vorhandenen Daten.'},
    'dogs': {'file': DOGS_FILE, 'title': 'Hunde', 'fields': {'Lizenznummer': 'Lizenznummer', 'Hundename': 'Hundename', 'Hundefuehrer_ID': 'Hundeführer ID', 'Kategorie': 'Kategorie', 'Klasse': 'Klasse'}, 'id_field': 'Lizenznummer', 'import_info': 'Spalten: H-Lizenz;H-Name;... Aktualisiert Hunde & Hundeführer.'},
    'handlers': {'file': HANDLERS_FILE, 'title': 'Hundeführer', 'fields': {'id': 'ID', 'Vorname': 'Vorname', 'Nachname': 'Nachname', 'Vereinsnummer': 'Vereinsnummer'}, 'id_field': 'id', 'import_info': 'Nutzt die gleiche Datei wie Hunde-Import. Aktualisiert Hunde & Hundeführer.'},
    'judges': {'file': JUDGES_FILE, 'title': 'Richter', 'fields': {'id': 'ID', 'firstname': 'Vorname', 'lastname': 'Nachname'}, 'id_field': 'id', 'import_info': 'Spalten: ID;Vorname;Name. Ersetzt alle vorhandenen Daten.'},
}

@master_data_bp.route('/master_data')
def master_data():
    active_tab = request.args.get('type', 'judges')
    all_judges = _load_data(DATA_CONFIG['judges']['file'])
    all_clubs = _load_data(DATA_CONFIG['clubs']['file'])
    all_handlers = _load_data(DATA_CONFIG['handlers']['file'])
    all_dogs = _load_data(DATA_CONFIG['dogs']['file'])
    return render_template('master_data.html',
                           judges=all_judges,
                           clubs=all_clubs,
                           handlers=all_handlers,
                           dogs=all_dogs,
                           active_tab=active_tab)

@master_data_bp.route('/add/<data_type>', methods=['GET', 'POST'])
def add_item(data_type):
    config = DATA_CONFIG.get(data_type)
    if not config:
        return redirect(url_for('master_data_bp.master_data'))
    if request.method == 'POST':
        data = _load_data(config['file'])
        new_item = {field: request.form.get(field) for field in config['fields']}
        if 'id' in new_item and config['id_field'] == 'id':
             if not new_item.get('id'):
                new_item['id'] = str(uuid.uuid4())
        data.append(new_item)
        _save_data(config['file'], data)
        flash(f'Neuer Eintrag für {config["title"]} erfolgreich hinzugefügt.', 'success')
        return redirect(url_for('master_data_bp.master_data', type=data_type))

    form_context = {}
    if data_type == 'handlers':
        form_context['clubs'] = _load_data(CLUBS_FILE)
    if data_type == 'dogs':
        form_context['handlers'] = _load_data(HANDLERS_FILE)
    return render_template('master_data_item_form.html', action='add', data_type=data_type, config=config, item={}, **form_context)

@master_data_bp.route('/edit/<data_type>/<item_id>', methods=['GET', 'POST'])
def edit_item(data_type, item_id):
    config = DATA_CONFIG.get(data_type)
    if not config:
        return redirect(url_for('master_data_bp.master_data'))
    data = _load_data(config['file'])
    item = next((d for d in data if str(d.get(config['id_field'])) == str(item_id)), None)
    if item is None:
        flash('Eintrag nicht gefunden.', 'danger')
        return redirect(url_for('master_data_bp.master_data', type=data_type))
    if request.method == 'POST':
        for field in config['fields']:
            if field in request.form:
                item[field] = request.form[field]
        _save_data(config['file'], data)
        flash(f'Eintrag für {config["title"]} erfolgreich aktualisiert.', 'success')
        return redirect(url_for('master_data_bp.master_data', type=data_type))

    form_context = {}
    if data_type == 'handlers':
        form_context['clubs'] = _load_data(CLUBS_FILE)
    if data_type == 'dogs':
        form_context['handlers'] = _load_data(HANDLERS_FILE)
    return render_template('master_data_item_form.html', action='edit', data_type=data_type, config=config, item=item, **form_context)

@master_data_bp.route('/import', methods=['POST'])
def import_master_data():
    data_type = request.form.get('data_type')
    file = request.files.get('file')
    if not file or file.filename == '':
        flash('Keine Datei für den Import ausgewählt.', 'warning')
        return redirect(url_for('master_data_bp.master_data', type=data_type))

    content = _decode_csv_file(file)
    if not content:
        flash('Die hochgeladene Datei konnte nicht gelesen oder dekodiert werden.', 'danger')
        return redirect(url_for('master_data_bp.master_data', type=data_type))

    reader = csv.DictReader(StringIO(content), delimiter=';')
    if not reader.fieldnames:
        flash('Die CSV-Datei ist leer oder hat keine Kopfzeile.', 'danger')
        return redirect(url_for('master_data_bp.master_data', type=data_type))

    reader.fieldnames = [field.lower().strip().replace('.', '') for field in reader.fieldnames]

    try:
        if data_type == 'clubs':
            # KORREKTUR: Erwartet jetzt 'name' (Einzahl)
            required_cols = {'nr', 'name'}
            if not required_cols.issubset(reader.fieldnames):
                flash(f"Fehlende Spalten für Vereine. Benötigt: {required_cols}", 'danger')
                return redirect(url_for('master_data_bp.master_data', type=data_type))

            # Liest aus 'name' (Einzahl)
            new_items = [{'nummer': row.get('nr').strip(), 'name': row.get('name').strip()} for row in reader if row.get('nr') and row.get('name')]
            _save_data(CLUBS_FILE, new_items)
            flash(f'{len(new_items)} Vereine importiert (überschrieben).', 'success')

        elif data_type == 'judges':
            # KORREKTUR: Erwartet jetzt 'vorname' (Einzahl)
            required_cols = {'id', 'vorname', 'name'}
            if not required_cols.issubset(reader.fieldnames):
                flash(f"Fehlende Spalten für Richter. Benötigt: {required_cols}", 'danger')
                return redirect(url_for('master_data_bp.master_data', type=data_type))

            new_items = []
            for row in reader:
                if row.get('id') and row.get('vorname') and row.get('name'):
                    new_items.append({
                        'id': row.get('id').strip(),
                        # Liest aus 'vorname' (Einzahl)
                        'firstname': row.get('vorname').strip(),
                        'lastname': row.get('name').strip()
                    })
            _save_data(JUDGES_FILE, new_items)
            flash(f'{len(new_items)} Richter importiert (überschrieben).', 'success')

        elif data_type in ['dogs', 'handlers']:
            required_cols = {'h-lizenz', 'h-name', 'hf-vorname', 'hf-name', 'h-kategorie', 'h-kl-eingabe'}
            if not required_cols.issubset(reader.fieldnames):
                flash(f"Fehlende Spalten für Hunde/Hundeführer. Benötigt: {', '.join(required_cols)}", 'danger')
                return redirect(url_for('master_data_bp.master_data', type=data_type))

            dogs, handlers, clubs = _load_data(DOGS_FILE), _load_data(HANDLERS_FILE), _load_data(CLUBS_FILE)
            clubs_map_by_name = {c.get('name', '').lower(): c.get('nummer') for c in clubs}
            existing_dogs = {d.get('Lizenznummer') for d in dogs}
            existing_handlers = {f"{h.get('Vorname', '')} {h.get('Nachname', '')}".lower(): h.get('id') for h in handlers}

            dogs_added, handlers_added = 0, 0
            for row in reader:
                handler_firstname = row.get('hf-vorname', '').strip()
                handler_lastname = row.get('hf-name', '').strip()
                license_nr = row.get('h-lizenz', '').strip()

                if not all([handler_firstname, handler_lastname, license_nr]):
                    continue

                handler_fullname_lower = f"{handler_firstname} {handler_lastname}".lower()
                if handler_fullname_lower not in existing_handlers:
                    handler_id = str(uuid.uuid4())
                    verein_name = row.get('hf-verein', '').strip()
                    verein_nr = clubs_map_by_name.get(verein_name.lower(), '')
                    handlers.append({'id': handler_id, 'Vorname': handler_firstname, 'Nachname': handler_lastname, 'Vereinsnummer': verein_nr})
                    existing_handlers[handler_fullname_lower] = handler_id
                    handlers_added += 1

                handler_id = existing_handlers[handler_fullname_lower]
                if license_nr not in existing_dogs:
                    dogs.append({
                        'Lizenznummer': license_nr,
                        'Hundename': row.get('h-name', '').strip(),
                        'Hundefuehrer_ID': handler_id,
                        'Kategorie': row.get('h-kategorie', '').strip(),
                        'Klasse': row.get('h-kl-eingabe', '').strip()
                    })
                    existing_dogs.add(license_nr)
                    dogs_added += 1

            _save_data(HANDLERS_FILE, handlers)
            _save_data(DOGS_FILE, dogs)
            flash(f"Stammdaten aktualisiert: {dogs_added} neue Hunde und {handlers_added} neue Hundeführer hinzugefügt.", "success")

    except Exception as e:
        flash(f"Ein unerwarteter Fehler ist beim Import aufgetreten: {e}", "danger")

    return redirect(url_for('master_data_bp.master_data', type=data_type))
