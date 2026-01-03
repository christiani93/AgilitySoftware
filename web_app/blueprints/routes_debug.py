# blueprints/routes_debug.py
from flask import Blueprint, redirect, url_for, flash, abort
import random
import math
from utils import _load_data, _save_data, _load_settings, _to_float

debug_bp = Blueprint('debug_bp', __name__)

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
