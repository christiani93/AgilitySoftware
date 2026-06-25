"""
FMBB-Quali – Blueprint für FMBB-Tag-Auswertung.

Analog zu routes_skbs_sm.py. Unterschied: FMBB ist ein **Overlay** über
bestehende Events, kein eigener Veranstaltungstyp. Aktivierung über
`event["fmbb_quali_active"] = True`. Teilnehmer-Markierung manuell pro
Anmeldung (`is_fmbb`-Flag), Bulk-Setzen via Lizenz-Liste.
"""
import csv
import io
import re

from flask import (Blueprint, render_template, request, redirect,
                   url_for, flash, abort, Response)

from utils import _load_data, _save_data, _load_settings, _calculate_run_results, _safe_http_filename
from fmbb_quali import (
    calculate_fmbb_quali,
    mark_fmbb_by_licenses,
    is_fmbb_active,
    FMBB_ELIGIBLE_CLASSES,
    FMBB_RUN_TYPES,
)

fmbb_bp = Blueprint('fmbb_bp', __name__, template_folder='../templates',
                    url_prefix='/fmbb')

EVENTS_FILE = 'events.json'


# ── Helfer ────────────────────────────────────────────────────────────────────

def _get_event(event_id: str):
    events = _load_data(EVENTS_FILE)
    event  = next((e for e in events if e.get('id') == event_id), None)
    return events, event


def _is_fmbb_run(run: dict) -> bool:
    """Lauf gehört zur FMBB-Tag-Auswertung wenn Klasse 2/3 + Agi/Jump."""
    klasse  = str(run.get('klasse') or '')
    laufart = run.get('laufart') or ''
    return klasse in FMBB_ELIGIBLE_CLASSES and laufart in FMBB_RUN_TYPES


def _parse_license_list(text: str) -> list[str]:
    """
    Parst eine Lizenz-Liste aus einem Textarea oder CSV-Upload.
    Akzeptiert beliebige Trennzeichen (Whitespace, Komma, Semikolon, Newline).
    """
    if not text:
        return []
    parts = re.split(r"[\s,;]+", text.strip())
    return [p.strip() for p in parts if p.strip()]


# ── Routen ────────────────────────────────────────────────────────────────────

@fmbb_bp.get('/dashboard/<event_id>')
def fmbb_dashboard(event_id):
    """FMBB-Übersicht: Tag-Auswertung pro Lauf (gefiltert auf FMBB-Teilnehmer)."""
    events, event = _get_event(event_id)
    if not event:
        abort(404)

    # Ergebnisse neu berechnen für aktuelle FMBB-Läufe
    settings = _load_settings()
    for run in event.get('runs', []):
        if _is_fmbb_run(run):
            _calculate_run_results(run, settings)
    _save_data(EVENTS_FILE, events)

    fmbb_data = calculate_fmbb_quali(event)

    return render_template(
        'fmbb_dashboard.html',
        event=event,
        fmbb_data=fmbb_data,
        is_active=is_fmbb_active(event),
    )


@fmbb_bp.route('/config/<event_id>', methods=['GET', 'POST'])
def fmbb_config(event_id):
    """
    FMBB-Konfiguration: Aktivierung + Bulk-Marker via Lizenz-Liste.
    POST mit 'action' = 'activate' / 'deactivate' / 'mark_licenses' / 'clear_marks'.
    """
    events, event = _get_event(event_id)
    if not event:
        abort(404)

    if request.method == 'POST':
        action = (request.form.get('action') or '').strip()

        if action == 'activate':
            event['fmbb_quali_active'] = True
            _save_data(EVENTS_FILE, events)
            flash('FMBB-Quali für diesen Event aktiviert.', 'success')

        elif action == 'deactivate':
            event['fmbb_quali_active'] = False
            _save_data(EVENTS_FILE, events)
            flash('FMBB-Quali für diesen Event deaktiviert.', 'info')

        elif action == 'mark_licenses':
            licenses = _parse_license_list(request.form.get('licenses', ''))
            reset = request.form.get('reset', '1') == '1'
            if not licenses:
                flash('Keine Lizenznummern gefunden.', 'warning')
            else:
                stats = mark_fmbb_by_licenses(event, licenses, reset=reset)
                _save_data(EVENTS_FILE, events)
                msg = (
                    f"{stats['matched']} Teams als FMBB markiert "
                    f"(von {len(licenses)} Lizenzen, {stats['total_entries']} Anmeldungen)."
                )
                if stats['unmatched']:
                    sample = ', '.join(stats['unmatched'][:5])
                    extra = '' if len(stats['unmatched']) <= 5 else f' (+{len(stats["unmatched"]) - 5} weitere)'
                    msg += f" Nicht gefunden: {sample}{extra}."
                flash(msg, 'success')

        elif action == 'clear_marks':
            # Alle is_fmbb-Flags zurücksetzen
            cleared = 0
            for run in event.get('runs', []):
                for entry in run.get('entries', []):
                    if entry.get('is_fmbb'):
                        entry['is_fmbb'] = False
                        cleared += 1
            _save_data(EVENTS_FILE, events)
            flash(f'{cleared} FMBB-Markierungen zurückgesetzt.', 'info')

        return redirect(url_for('fmbb_bp.fmbb_config', event_id=event_id))

    # GET: Anzeige
    fmbb_data = calculate_fmbb_quali(event)

    # Aktuelle FMBB-Lizenzen sammeln (für Anzeige + Pre-Fill der Textarea)
    current_licenses: list[str] = []
    for run in event.get('runs', []):
        for entry in run.get('entries', []):
            if entry.get('is_fmbb'):
                lic = (entry.get('Lizenznummer') or '').strip()
                if lic and lic not in current_licenses:
                    current_licenses.append(lic)

    return render_template(
        'fmbb_config.html',
        event=event,
        is_active=is_fmbb_active(event),
        current_licenses=current_licenses,
        total_fmbb_teams=fmbb_data['total_fmbb_teams'],
    )


@fmbb_bp.get('/export-csv/<event_id>')
def fmbb_export_csv(event_id):
    """CSV-Export der FMBB-Tag-Auswertung für SKBS-Übermittlung."""
    events, event = _get_event(event_id)
    if not event:
        abort(404)

    settings = _load_settings()
    for run in event.get('runs', []):
        if _is_fmbb_run(run):
            _calculate_run_results(run, settings)

    fmbb_data = calculate_fmbb_quali(event)

    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')
    writer.writerow([
        'Kategorie', 'Klasse', 'Laufart',
        'Rang', 'Lizenznummer', 'Hund', 'Hundeführer/in',
        'Gesamt-Fehler', 'Parcoursfehler', 'Zeit (s)', 'Status',
    ])

    for run_data in fmbb_data['runs']:
        for r in run_data['rankings']:
            writer.writerow([
                run_data['kategorie'],
                f"Klasse {run_data['klasse']}",
                run_data['laufart'],
                r['rang'] if r['rang'] is not None else 'DIS',
                r['license'],
                r['dog_name'],
                r['handler_name'],
                round(r['fehler_total'], 2) if not r['dis'] else 'DIS',
                r['fehler_parcours'],
                round(r['zeit'], 2) if not r['dis'] else 'DIS',
                'DIS' if r['dis'] else 'OK',
            ])

    filename = f"FMBB-Quali_{_safe_http_filename(event.get('Bezeichnung') or event_id)}.csv"
    return Response(
        output.getvalue().encode('utf-8-sig'),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'},
    )
