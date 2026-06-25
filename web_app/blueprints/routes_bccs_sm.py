"""
BCCS-Schweizermeisterschaft – Blueprint für BCCS-SM-Verwaltung und -Auswertung.

Analog zu routes_skbs_sm.py, aber für die BCCS-Variante (Border Collie Club Schweiz):
  - Kategorien Intermediate + Large
  - Zwei Divisionen: SM (Klasse 3) + Nachwuchs (Klassen 1+2)
  - 15 %-Quote pro Quali-Lauf, alternierendes Nachrücken (kein FP-Deckel)
  - Final = 2 Läufe (Jumping + Agility) summiert
Siehe bccs_sm_qualification.py und Reglement BCCS 2023.
"""
import csv
import io

from flask import (Blueprint, render_template, request, redirect,
                   url_for, flash, abort, Response)

from utils import _load_data, _save_data, _load_settings, _calculate_run_results, _safe_http_filename
from bccs_sm_qualification import (
    calculate_bccs_sm_qualification, rank_final_bccs,
    CATEGORIES, DIVISIONS, QUALI_RUN_TYPES,
)

bccs_sm_bp = Blueprint('bccs_sm_bp', __name__, template_folder='../templates',
                       url_prefix='/bccs-sm')

EVENTS_FILE = 'events.json'

# Alle Klassen, die in irgendeiner Division vorkommen (für die Lauf-Erkennung)
_BCCS_CLASSES = {c for d in DIVISIONS.values() for c in d["classes"]}


def _get_event(event_id: str):
    events = _load_data(EVENTS_FILE)
    event = next((e for e in events if e.get('id') == event_id), None)
    return events, event


def _is_bccs_sm_run(run: dict) -> bool:
    """BCCS-SM-relevant: Kategorie Intermediate/Large + Quali (Kl.1-3, Agi/Jump) oder is_final."""
    if run.get('kategorie') not in CATEGORIES:
        return False
    if run.get('is_final'):
        return True
    return (str(run.get('klasse') or '') in _BCCS_CLASSES
            and run.get('laufart') in QUALI_RUN_TYPES)


def _recalc(event, settings):
    for run in event.get('runs', []):
        if _is_bccs_sm_run(run):
            _calculate_run_results(run, settings)


# ── Routen ────────────────────────────────────────────────────────────────────

@bccs_sm_bp.get('/dashboard/<event_id>')
def bccs_sm_dashboard(event_id):
    """BCCS-SM-Übersicht: pro Division (I/L × SM/Nachwuchs) Quoten, Finalisten, Final."""
    events, event = _get_event(event_id)
    if not event:
        abort(404)

    settings = _load_settings()
    _recalc(event, settings)
    _save_data(EVENTS_FILE, events)

    bccs_data = calculate_bccs_sm_qualification(event)
    final_ranking = rank_final_bccs(event)

    return render_template(
        'bccs_sm_dashboard.html',
        event=event,
        bccs_data=bccs_data,
        final_ranking=final_ranking,
        categories=CATEGORIES,
        divisions=DIVISIONS,
    )


@bccs_sm_bp.route('/config/<event_id>', methods=['GET', 'POST'])
def bccs_sm_config(event_id):
    """BCCS-SM-Konfiguration: bis zu 4 Titelverteidiger (Kategorie × Division)."""
    events, event = _get_event(event_id)
    if not event:
        abort(404)

    if request.method == 'POST':
        defenders = []
        for cat in CATEGORIES:
            for div_key in DIVISIONS:
                lic = request.form.get(f'def_{cat}_{div_key}_license', '').strip()
                if not lic:
                    continue
                defenders.append({
                    'license':      lic,
                    'dog_name':     request.form.get(f'def_{cat}_{div_key}_dog', '').strip(),
                    'handler_name': request.form.get(f'def_{cat}_{div_key}_handler', '').strip(),
                    'category':     cat,
                    'division':     div_key,
                })
        cfg = event.get('bccs_sm_config', {})
        cfg['defending_champions'] = defenders
        # Quali-Lauf-Reihenfolge (für Nachrück-Alternierung), optional
        order = request.form.get('quali_run_order', '').strip()
        if order in ('Agility,Jumping', 'Jumping,Agility'):
            cfg['quali_run_order'] = order.split(',')
        event['bccs_sm_config'] = cfg
        _save_data(EVENTS_FILE, events)
        flash('BCCS-SM-Konfiguration gespeichert.', 'success')
        return redirect(url_for('bccs_sm_bp.bccs_sm_dashboard', event_id=event_id))

    cfg = event.get('bccs_sm_config', {})
    defenders = {(d.get('category'), d.get('division')): d
                 for d in cfg.get('defending_champions', [])}
    return render_template(
        'bccs_sm_config.html',
        event=event, bccs_config=cfg, defenders=defenders,
        categories=CATEGORIES, divisions=DIVISIONS,
    )


@bccs_sm_bp.get('/export-csv/<event_id>')
def bccs_sm_export_csv(event_id):
    """CSV-Export: Finalisten + Final-Rangierung je Division."""
    events, event = _get_event(event_id)
    if not event:
        abort(404)

    settings = _load_settings()
    _recalc(event, settings)
    bccs_data = calculate_bccs_sm_qualification(event)
    final_ranking = rank_final_bccs(event)

    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')

    for key, div in bccs_data.get('divisions', {}).items():
        writer.writerow([f'# FINALISTEN — {key}  (Quote {div.get("quota")}, '
                         f'offen {div.get("open_spots")})'])
        writer.writerow(['#', 'Lizenz', 'Hund', 'Hundeführer/in', 'Quelle',
                         'Aus Klasse', 'Quali-Rang'])
        for i, f in enumerate(div.get('finalists', []), 1):
            writer.writerow([i, f.get('license', ''), f.get('dog_name', ''),
                             f.get('handler_name', ''), f.get('source', ''),
                             f.get('from_class') if f.get('from_class') is not None else '',
                             f.get('quali_rank') if f.get('quali_rank') is not None else ''])
        ranking = final_ranking.get(key, [])
        if ranking:
            writer.writerow([])
            writer.writerow([f'# FINAL-RANGIERUNG — {key}'])
            writer.writerow(['Rang', 'Lizenz', 'Hund', 'Hundeführer/in',
                             'Summe Fehler', 'Summe Parcours', 'Summe Zeit (s)'])
            for r in ranking:
                writer.writerow([
                    r.get('final_rang') if r.get('final_rang') is not None else 'DIS',
                    r.get('license', ''), r.get('dog_name', ''), r.get('handler_name', ''),
                    r.get('sum_fehler') if r.get('sum_fehler') is not None else 'DIS',
                    r.get('sum_parcours') if r.get('sum_parcours') is not None else '',
                    r.get('sum_zeit') if r.get('sum_zeit') is not None else '',
                ])
        writer.writerow([])

    filename = f"BCCS-SM_{_safe_http_filename(event.get('Bezeichnung') or event_id)}.csv"
    return Response(
        output.getvalue().encode('utf-8-sig'),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'},
    )
