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
from functools import partial

from flask import (Blueprint, render_template, request, redirect,
                   url_for, flash, abort, Response)

from utils import _load_data, _save_data, _load_settings, recalc_and_store, _safe_http_filename
from bccs_sm_qualification import (
    calculate_bccs_sm_qualification, rank_final_bccs, apply_final_start_order,
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
    """Ergebnisse neu berechnen und aufs Entry zurückschreiben (Reihenfolge bleibt) —
    sonst liest die BCCS-Berechnung keine platzierten Hunde → 0 Finalisten. Siehe recalc_and_store."""
    for run in event.get('runs', []):
        if _is_bccs_sm_run(run):
            recalc_and_store(run, settings)


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

    recalc_fn = partial(recalc_and_store, settings=settings)
    bccs_data = calculate_bccs_sm_qualification(event, recalc_fn=recalc_fn)
    final_ranking = rank_final_bccs(event, recalc_fn=recalc_fn)

    return render_template(
        'bccs_sm_dashboard.html',
        event=event,
        bccs_data=bccs_data,
        final_ranking=final_ranking,
        categories=CATEGORIES,
        divisions=DIVISIONS,
    )


@bccs_sm_bp.post('/final-startorder/<event_id>')
def bccs_sm_final_startorder(event_id):
    """Setzt die Startreihenfolge des 2. Finallaufs (Agility) je Kategorie/Klasse
    aus der Rangliste des 1. Finallaufs (Jumping): nicht klassierte (DIS) zuerst nach
    Startnummer, dann Schlechtester→Sieger. Schreibt `start_order` auf die Agility-Entries."""
    events, event = _get_event(event_id)
    if not event:
        abort(404)
    settings = _load_settings()
    applied = apply_final_start_order(event, lambda run: recalc_and_store(run, settings))
    _save_data(EVENTS_FILE, events)
    if applied:
        parts = ", ".join(f"{a['kategorie']} Kl.{a['klasse']} ({a['count']})" for a in applied)
        flash(f"Startreihenfolge 2. Finallauf gesetzt: {parts}.", "success")
    else:
        flash("Keine Final-Paarung (Jumping→Agility) mit is_final gefunden.", "warning")
    return redirect(url_for('bccs_sm_bp.bccs_sm_dashboard', event_id=event_id))


@bccs_sm_bp.post('/populate-finals/<event_id>')
def bccs_sm_populate_finals(event_id):
    """Überträgt die abgeleiteten Finalisten als Startplätze in die Finalläufe
    (is_final): jeder Finalist kommt in BEIDE Finalläufe (Jumping + Agility) seiner
    Kategorie + Division-Klasse. Idempotent (kein Doppel-Eintrag). Danach kann man
    die Final-Resultate erfassen und die Final-Rangierung rechnen."""
    events, event = _get_event(event_id)
    if not event:
        abort(404)
    settings = _load_settings()
    _recalc(event, settings)
    data = calculate_bccs_sm_qualification(
        event, recalc_fn=lambda r: recalc_and_store(r, settings))

    # Hundeführer je Lizenz aus den Quali-Läufen (Fallback, falls Finalist keinen trägt)
    handler_by_lic = {}
    for run in event.get('runs', []):
        if run.get('is_final'):
            continue
        for en in run.get('entries', []):
            lic = str(en.get('Lizenznummer') or '')
            if lic and lic not in handler_by_lic:
                handler_by_lic[lic] = en.get('Hundefuehrer') or ''

    # Index der Finalläufe: (Kategorie, Laufart, Klasse) → run
    final_runs = {}
    for run in event.get('runs', []):
        if run.get('is_final'):
            final_runs[(run.get('kategorie'), run.get('laufart'), str(run.get('klasse')))] = run

    added = 0
    for key, div in data['divisions'].items():
        category, div_key = key.split('/')
        classes = [str(c) for c in DIVISIONS[div_key]['classes']]
        for f in div.get('finalists', []):
            lic = str(f.get('license') or '')
            if not lic:
                continue
            tgt_cls = str(f.get('from_class') or classes[0])
            for la in QUALI_RUN_TYPES:   # Agility, Jumping
                run = final_runs.get((category, la, tgt_cls))
                if not run:              # Fallback: Final dieser Kat/Disziplin in Div-Klassen
                    for c in classes:
                        run = final_runs.get((category, la, c))
                        if run:
                            break
                if not run:
                    continue
                entries = run.setdefault('entries', [])
                if any(str(e.get('Lizenznummer') or '') == lic for e in entries):
                    continue
                entries.append({
                    'Lizenznummer': lic,
                    'Hundename':    f.get('dog_name') or '',
                    'Hundefuehrer': f.get('handler_name') or handler_by_lic.get(lic) or '',
                    'Kategorie':    category,
                    'Klasse':       tgt_cls,
                    'Startnummer':  0,
                    'bccs_sm':      True,
                })
                added += 1

    _save_data(EVENTS_FILE, events)
    flash(f'{added} Final-Startplätze aus den Finalisten übernommen.', 'success')
    return redirect(url_for('bccs_sm_bp.bccs_sm_dashboard', event_id=event_id))


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
    recalc_fn = partial(recalc_and_store, settings=settings)
    bccs_data = calculate_bccs_sm_qualification(event, recalc_fn=recalc_fn)
    final_ranking = rank_final_bccs(event, recalc_fn=recalc_fn)

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
