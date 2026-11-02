"""
SM Einzel – Blueprint für SM-Verwaltung und -Auswertung.
"""
import csv
import io

from flask import (Blueprint, render_template, request, redirect,
                   url_for, flash, abort, Response)

from utils import _load_data, _save_data, _load_settings, recalc_and_store, _safe_http_filename
from sm_qualification import (
    calculate_sm_qualification, get_sm_runs,
    CATEGORIES, SM_RUN_TYPES,
)
from sm_import import (
    build_sm_event_from_participants, build_sm_event_from_csvs, apply_sm_startnumbers,
)

sm_bp = Blueprint('sm_bp', __name__, template_folder='../templates', url_prefix='/sm')

EVENTS_FILE = 'events.json'


# ── Helfer ────────────────────────────────────────────────────────────────────

def _get_event(event_id: str):
    events = _load_data(EVENTS_FILE)
    event  = next((e for e in events if e.get('id') == event_id), None)
    return events, event


# ── Routen ────────────────────────────────────────────────────────────────────

@sm_bp.route('/import-participants', methods=['GET', 'POST'])
def sm_import_participants():
    """Teilnehmer-Import: Anmeldeliste (CSV) → SM-Event mit Quali-Läufen je Kategorie.
    Noch ohne Startnummern/Ergebnisse. Gleiche Event-ID überschreibt ein vorhandenes Event."""
    if request.method == 'POST':
        file = request.files.get('csv')
        if not file or not file.filename:
            flash('Keine Datei gewählt.', 'warning')
            return redirect(url_for('sm_bp.sm_import_participants'))
        event_id = (request.form.get('event_id') or '').strip() or 'SM_IMPORT'
        bezeichnung = (request.form.get('bezeichnung') or '').strip() or 'TKAMO-SM (Teilnehmer-Import)'
        datum = (request.form.get('datum') or '').strip()
        try:
            event, stats = build_sm_event_from_participants(
                file.read(), event_id=event_id, bezeichnung=bezeichnung, datum=datum)
        except Exception as exc:  # pragma: no cover - defensiver Pfad
            flash(f'Import fehlgeschlagen: {exc}', 'danger')
            return redirect(url_for('sm_bp.sm_import_participants'))

        events = [e for e in _load_data(EVENTS_FILE) if e.get('id') != event_id]
        events.append(event)
        _save_data(EVENTS_FILE, events)

        parts = ", ".join(f"{k} {v}" for k, v in stats.items() if not k.startswith('_'))
        flash(f"{stats['_total']} Teilnehmer importiert ({parts}). "
              f"Startnummern und Ergebnisse folgen später.", 'success')
        return redirect(url_for('sm_bp.sm_dashboard', event_id=event_id))

    return render_template('sm_import.html')


@sm_bp.route('/import-csv', methods=['GET', 'POST'])
def sm_import_csv():
    """Resultat-Import: Quali-CSV (+ optional Final-CSV, SportyDog-Export) → eigenständiges
    SM-Event direkt aus den Resultaten (für Finalisten-Ableitung + Prozent-Kontrolle).

    Baut bewusst ein SEPARATES Event von der Teilnehmer-Import-Route (andere Event-ID,
    sm_import_participants) - die Resultat-CSV liefert nur eine schmale Entry-Struktur
    (kein SHSB/Verein/Chip/Zuchtname), würde die reicheren Teilnehmer-Stammdaten also
    überschreiben statt ergänzen. Gleiche ID überschreibt ein vorhandenes Event."""
    if request.method == 'POST':
        quali_file = request.files.get('quali_csv')
        final_file = request.files.get('final_csv')
        if not quali_file or not quali_file.filename:
            flash('Keine Quali-Datei gewählt.', 'warning')
            return redirect(url_for('sm_bp.sm_import_csv'))
        event_id = (request.form.get('event_id') or '').strip() or 'SM_2026_RESULTS'
        bezeichnung = (request.form.get('bezeichnung') or '').strip() or 'TKAMO-SM (Resultat-Import)'
        datum = (request.form.get('datum') or '').strip()
        try:
            final_data = final_file.read() if (final_file and final_file.filename) else None
            event = build_sm_event_from_csvs(
                quali_file.read(), final_data,
                event_id=event_id, bezeichnung=bezeichnung, datum=datum)
        except Exception as exc:  # pragma: no cover - defensiver Pfad
            flash(f'Import fehlgeschlagen: {exc}', 'danger')
            return redirect(url_for('sm_bp.sm_import_csv'))

        events = [e for e in _load_data(EVENTS_FILE) if e.get('id') != event_id]
        events.append(event)
        _save_data(EVENTS_FILE, events)

        parts = ", ".join(
            f"{r['kategorie']} {r['laufart']} ({'Final' if r['is_final'] else 'Quali'}): "
            f"{len(r['entries'])} Starter"
            for r in sorted(event['runs'], key=lambda r: (r['kategorie'], r['is_final'], r['laufart']))
        )
        flash(f"Import fertig — {parts}.", 'success')
        return redirect(url_for('sm_bp.sm_dashboard', event_id=event_id))

    default_event_id = request.args.get('event_id') or 'SM_2026_RESULTS'
    return render_template('sm_import_csv.html', default_event_id=default_event_id)


@sm_bp.route('/import-startnumbers/<event_id>', methods=['GET', 'POST'])
def sm_import_startnumbers(event_id):
    """Startnummern-Zuordnung: einfache CSV ``Lizenznummer;Startnummer`` hochladen,
    wirkt event-weit auf alle Läufe (Quali + Final) der jeweiligen Lizenz."""
    events, event = _get_event(event_id)
    if not event:
        abort(404)

    if request.method == 'POST':
        file = request.files.get('csv')
        if not file or not file.filename:
            flash('Keine Datei gewählt.', 'warning')
            return redirect(url_for('sm_bp.sm_import_startnumbers', event_id=event_id))
        try:
            stats = apply_sm_startnumbers(event, file.read())
        except Exception as exc:  # pragma: no cover - defensiver Pfad
            flash(f'Import fehlgeschlagen: {exc}', 'danger')
            return redirect(url_for('sm_bp.sm_import_startnumbers', event_id=event_id))

        _save_data(EVENTS_FILE, events)

        msg = f"{stats['matched']} Startnummern gesetzt."
        if stats['unmatched_licenses']:
            msg += f" {len(stats['unmatched_licenses'])} Lizenz(en) aus der Datei nicht im Event gefunden."
        if stats['unknown_rows']:
            msg += f" {stats['unknown_rows']} Zeile(n) ohne gültige Startnummer übersprungen."
        flash(msg, 'success' if not stats['unmatched_licenses'] else 'warning')
        return redirect(url_for('sm_bp.sm_dashboard', event_id=event_id))

    return render_template('sm_import_startnumbers.html', event=event)


@sm_bp.get('/dashboard/<event_id>')
def sm_dashboard(event_id):
    """SM-Übersicht: Qualifikationsergebnisse aller Kategorien."""
    events, event = _get_event(event_id)
    if not event:
        abort(404)

    # Ergebnisse neu berechnen (für Aktualität)
    settings = _load_settings()
    for run in event.get('runs', []):
        if run.get('sm_run_type'):
            recalc_and_store(run, settings)
    _save_data(EVENTS_FILE, events)

    sm_data = calculate_sm_qualification(event)
    sm_runs = get_sm_runs(event)

    return render_template(
        'sm_dashboard.html',
        event=event,
        sm_data=sm_data,
        sm_runs=sm_runs,
        categories=CATEGORIES,
        sm_run_types=SM_RUN_TYPES,
    )


@sm_bp.route('/config/<event_id>', methods=['GET', 'POST'])
def sm_config(event_id):
    """SM-Konfiguration: Titelverteidiger und Total-Starters pro Kategorie."""
    events, event = _get_event(event_id)
    if not event:
        abort(404)

    if request.method == 'POST':
        sm_config_data = event.get('sm_config', {})

        for cat in CATEGORIES:
            cat_key = cat.lower()
            cat_cfg = sm_config_data.get(cat, {})

            # Titelverteidiger-Daten
            def_license  = request.form.get(f'defending_license_{cat_key}', '').strip()
            def_dog      = request.form.get(f'defending_dog_{cat_key}', '').strip()
            def_handler  = request.form.get(f'defending_handler_{cat_key}', '').strip()

            if def_license:
                cat_cfg['defending_champion'] = {
                    'license':      def_license,
                    'dog_name':     def_dog,
                    'handler_name': def_handler,
                }
            else:
                cat_cfg.pop('defending_champion', None)

            sm_config_data[cat] = cat_cfg

        event['sm_config'] = sm_config_data
        _save_data(EVENTS_FILE, events)
        flash('SM-Konfiguration gespeichert.', 'success')
        return redirect(url_for('sm_bp.sm_dashboard', event_id=event_id))

    sm_config_data = event.get('sm_config', {})
    return render_template(
        'sm_config.html',
        event=event,
        sm_config=sm_config_data,
        categories=CATEGORIES,
    )


@sm_bp.get('/final-list/<event_id>/<category>')
def sm_final_list(event_id, category):
    """Druckbare Finalliste für eine Kategorie."""
    events, event = _get_event(event_id)
    if not event:
        abort(404)

    settings = _load_settings()
    for run in event.get('runs', []):
        if run.get('sm_run_type'):
            recalc_and_store(run, settings)

    sm_data = calculate_sm_qualification(event)
    cat_data = sm_data.get(category)
    if not cat_data:
        flash(f'Keine SM-Daten für Kategorie {category}.', 'warning')
        return redirect(url_for('sm_bp.sm_dashboard', event_id=event_id))

    return render_template(
        'sm_final_list.html',
        event=event,
        category=category,
        cat_data=cat_data,
    )


@sm_bp.get('/export-csv/<event_id>')
def sm_export_csv(event_id):
    """CSV-Export aller SM-Finallisten (alle Kategorien)."""
    events, event = _get_event(event_id)
    if not event:
        abort(404)

    settings = _load_settings()
    for run in event.get('runs', []):
        if run.get('sm_run_type'):
            recalc_and_store(run, settings)

    sm_data = calculate_sm_qualification(event)

    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')
    writer.writerow([
        'Kategorie', 'Final-Platz', 'Lizenznummer', 'Hundename',
        'Hundeführer/in', 'Kombi-Fehler', 'Kombi-Zeit (s)',
        'Quali A Fehler', 'Quali A Zeit', 'Quali J Fehler', 'Quali J Zeit',
        'Qualifikation via',
    ])

    for cat in CATEGORIES:
        cd = sm_data.get(cat)
        if not cd:
            continue
        for i, r in enumerate(cd['final_list'], 1):
            via = 'Titelverteidiger' if r.get('is_defending') else \
                  'Direkt (16%)' if r.get('is_direct') else 'Kombinationsrangliste'
            writer.writerow([
                cat,
                i,
                r.get('license', ''),
                r.get('dog_name', ''),
                r.get('handler_name', ''),
                round(r.get('kombi_fehler', 0), 2) if not r.get('kombi_dis') else 'DIS',
                round(r.get('kombi_zeit', 0), 2) if not r.get('kombi_dis') else 'DIS',
                round(r.get('qa_fehler', 0), 2) if not r.get('qa_dis') else 'DIS',
                round(r.get('qa_zeit', 0), 2) if not r.get('qa_dis') else 'DIS',
                round(r.get('qj_fehler', 0), 2) if not r.get('qj_dis') else 'DIS',
                round(r.get('qj_zeit', 0), 2) if not r.get('qj_dis') else 'DIS',
                via,
            ])

    filename = f"SM_Finalisten_{_safe_http_filename(event.get('Bezeichnung') or event_id)}.csv"
    return Response(
        output.getvalue().encode('utf-8-sig'),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'},
    )
