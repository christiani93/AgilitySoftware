"""
SM Einzel – Blueprint für SM-Verwaltung und -Auswertung.
"""
import csv
import io

from flask import (Blueprint, render_template, request, redirect,
                   url_for, flash, abort, Response)

from utils import _load_data, _save_data, _load_settings, _calculate_run_results
from sm_qualification import (
    calculate_sm_qualification, get_sm_runs,
    CATEGORIES, SM_RUN_TYPES,
)

sm_bp = Blueprint('sm_bp', __name__, template_folder='../templates', url_prefix='/sm')

EVENTS_FILE = 'events.json'


# ── Helfer ────────────────────────────────────────────────────────────────────

def _get_event(event_id: str):
    events = _load_data(EVENTS_FILE)
    event  = next((e for e in events if e.get('id') == event_id), None)
    return events, event


# ── Routen ────────────────────────────────────────────────────────────────────

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
            _calculate_run_results(run, settings)
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
            _calculate_run_results(run, settings)

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
            _calculate_run_results(run, settings)

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

    filename = f"SM_Finalisten_{event.get('Bezeichnung', event_id).replace(' ', '_')}.csv"
    return Response(
        output.getvalue().encode('utf-8-sig'),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'},
    )
