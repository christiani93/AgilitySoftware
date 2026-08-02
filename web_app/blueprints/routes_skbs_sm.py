"""
SKBS-Schweizermeisterschaft – Blueprint für SKBS-SM-Verwaltung und -Auswertung.

Analog zu routes_sm.py (TKAMO-SM), aber für die SKBS-Variante:
  - Nur Kategorie Large
  - Iteration über Klassen 1, 2, 3 statt über Kategorien S/M/I/L
  - Gemeinsamer Finallauf für alle Klassen auf Niveau Klasse 3
  - Nachrück-Logik (max 10 FP, Klasse 3 → 2 → 1)
"""
import csv
import io

from flask import (Blueprint, render_template, request, redirect,
                   url_for, flash, abort, Response)

from utils import _load_data, _save_data, _load_settings, recalc_and_store, _safe_http_filename
from skbs_sm_qualification import (
    calculate_skbs_sm_qualification, rank_final,
    CLASS_LEVELS, CATEGORY,
)

skbs_sm_bp = Blueprint('skbs_sm_bp', __name__, template_folder='../templates',
                       url_prefix='/skbs-sm')

EVENTS_FILE = 'events.json'


# ── Helfer ────────────────────────────────────────────────────────────────────

def _get_event(event_id: str):
    events = _load_data(EVENTS_FILE)
    event  = next((e for e in events if e.get('id') == event_id), None)
    return events, event


def _is_skbs_sm_run(run: dict) -> bool:
    """SKBS-SM-relevante Läufe: Kategorie Large + entweder Quali oder is_final."""
    if run.get('kategorie') != CATEGORY:
        return False
    if run.get('is_final'):
        return True
    return str(run.get('klasse') or '') in CLASS_LEVELS and run.get('laufart') in ('Agility', 'Jumping')


# ── Routen ────────────────────────────────────────────────────────────────────

@skbs_sm_bp.get('/dashboard/<event_id>')
def skbs_sm_dashboard(event_id):
    """SKBS-SM-Übersicht: Quali-Standings pro Klasse + gemeinsame Finalisten-Liste."""
    events, event = _get_event(event_id)
    if not event:
        abort(404)

    # Ergebnisse neu berechnen (für Aktualität)
    settings = _load_settings()
    for run in event.get('runs', []):
        if _is_skbs_sm_run(run):
            recalc_and_store(run, settings)
    _save_data(EVENTS_FILE, events)

    skbs_data = calculate_skbs_sm_qualification(event)
    final_ranking = rank_final(event)

    return render_template(
        'skbs_sm_dashboard.html',
        event=event,
        skbs_data=skbs_data,
        final_ranking=final_ranking,
        class_levels=CLASS_LEVELS,
    )


@skbs_sm_bp.route('/config/<event_id>', methods=['GET', 'POST'])
def skbs_sm_config(event_id):
    """SKBS-SM-Konfiguration: Titelverteidiger (eine Person, da nur Large)."""
    events, event = _get_event(event_id)
    if not event:
        abort(404)

    if request.method == 'POST':
        cfg = event.get('skbs_sm_config', {})

        def_license = request.form.get('defending_license', '').strip()
        def_dog     = request.form.get('defending_dog', '').strip()
        def_handler = request.form.get('defending_handler', '').strip()

        if def_license:
            cfg['defending_champion'] = {
                'license':      def_license,
                'dog_name':     def_dog,
                'handler_name': def_handler,
            }
        else:
            cfg.pop('defending_champion', None)

        event['skbs_sm_config'] = cfg
        _save_data(EVENTS_FILE, events)
        flash('SKBS-SM-Konfiguration gespeichert.', 'success')
        return redirect(url_for('skbs_sm_bp.skbs_sm_dashboard', event_id=event_id))

    cfg = event.get('skbs_sm_config', {})
    return render_template(
        'skbs_sm_config.html',
        event=event,
        skbs_config=cfg,
    )


@skbs_sm_bp.get('/final-list/<event_id>')
def skbs_sm_final_list(event_id):
    """Druckbare gemeinsame Finalliste."""
    events, event = _get_event(event_id)
    if not event:
        abort(404)

    settings = _load_settings()
    for run in event.get('runs', []):
        if _is_skbs_sm_run(run):
            recalc_and_store(run, settings)

    skbs_data = calculate_skbs_sm_qualification(event)

    return render_template(
        'skbs_sm_final_list.html',
        event=event,
        skbs_data=skbs_data,
    )


@skbs_sm_bp.get('/export-csv/<event_id>')
def skbs_sm_export_csv(event_id):
    """CSV-Export der Finalisten-Liste + Final-Rangierung (falls vorhanden)."""
    events, event = _get_event(event_id)
    if not event:
        abort(404)

    settings = _load_settings()
    for run in event.get('runs', []):
        if _is_skbs_sm_run(run):
            recalc_and_store(run, settings)

    skbs_data = calculate_skbs_sm_qualification(event)
    final_ranking = rank_final(event)

    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')

    # Finalisten-Block
    writer.writerow(['# FINALISTEN'])
    writer.writerow([
        '#', 'Lizenznummer', 'Hundename', 'Hundeführer/in',
        'Qualifiziert via', 'Aus Klasse', 'Quali-Rang',
    ])
    for i, f in enumerate(skbs_data.get('finalists', []), 1):
        writer.writerow([
            i,
            f.get('license', ''),
            f.get('dog_name', ''),
            f.get('handler_name', ''),
            f.get('source', ''),
            f.get('from_class') if f.get('from_class') is not None else '',
            f.get('quali_rank') if f.get('quali_rank') is not None else '',
        ])

    if skbs_data.get('open_spots'):
        writer.writerow([])
        writer.writerow([f'# Offene Plätze: {skbs_data["open_spots"]}'])

    # Final-Rangierung (falls Final gelaufen)
    if final_ranking:
        writer.writerow([])
        writer.writerow(['# FINAL-RANGIERUNG'])
        writer.writerow([
            'Final-Rang', 'Lizenznummer', 'Hundename', 'Hundeführer/in',
            'Gesamt-Fehler', 'Parcoursfehler', 'Zeit (s)', 'Status',
        ])
        for r in final_ranking:
            writer.writerow([
                r.get('final_rang') if r.get('final_rang') is not None else 'DIS',
                r.get('license', ''),
                r.get('dog_name', ''),
                r.get('handler_name', ''),
                round(r.get('fehler_total', 0), 2) if not r.get('dis') else 'DIS',
                r.get('fehler_parcours', 0),
                round(r.get('zeit', 0), 2) if not r.get('dis') else 'DIS',
                'DIS' if r.get('dis') else 'OK',
            ])

    filename = f"SKBS-SM_{_safe_http_filename(event.get('Bezeichnung') or event_id)}.csv"
    return Response(
        output.getvalue().encode('utf-8-sig'),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'},
    )
