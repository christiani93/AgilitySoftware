# blueprints/routes_live.py
from flask import Blueprint, render_template, request, jsonify, abort, flash, redirect, url_for, session
from datetime import datetime
import json
import math
from app import socketio
from utils import (_load_data, _save_data, _get_active_event, 
                   _calculate_run_results, _load_settings, _get_active_event_id, 
                   _calculate_timelines)

live_bp = Blueprint('live_bp', __name__, template_folder='../templates')

def _get_live_data_for_ring(event, ring_name):
    active_run_for_ring = session.get('active_announcer_runs', {}).get(event['id'], {}).get(ring_name)
    if not active_run_for_ring: return None
    run_id = active_run_for_ring['run_id']
    run = next((r for r in event.get('runs', []) if r.get('id') == run_id), None)
    if not run: return None
    settings = _load_settings()
    all_results = _calculate_run_results(run, settings)
    last_results = sorted([res for res in all_results if res.get('platz')], key=lambda x: x.get('timestamp', 0), reverse=True)[:5]
    participants_in_order = sorted(run.get('entries', []), key=lambda x: int(x.get('Startnummer', 9999)))
    starters_without_result = [p for p in participants_in_order if not p.get('result')]
    current_starter = starters_without_result[0] if starters_without_result else None
    next_starter = starters_without_result[1] if len(starters_without_result) > 1 else None
    rankings = [r for r in all_results if r.get('platz')]
    return {"run_name": run.get('name'),"current_starter": current_starter, "next_starter": next_starter, "last_results": last_results, "top_rankings": rankings[:5]}

@live_bp.route('/live_dashboard')
def live_event_dashboard():
    event_id = _get_active_event_id()
    if not event_id:
        flash("Kein Event als 'Live' markiert.", "info")
        return redirect(url_for('events_bp.events_list'))
    event = _get_active_event()
    if not event:
        flash(f"Live-Event mit ID {event_id} wurde nicht gefunden.", "warning")
        _save_data('active_event.json', {})
        return redirect(url_for('events_bp.events_list'))
    runs_by_ring = {}
    if event.get('run_order'):
        all_rings = sorted(list(set(r['assigned_ring'] for r in event.get('runs', []) if r.get('assigned_ring'))))
        for ring_num in all_rings:
            runs_by_ring[f"Ring {ring_num}"] = [r for r in event.get('runs', []) if r.get('assigned_ring') == ring_num]
    judges = _load_data('judges.json')
    return render_template('live_event_dashboard.html', event=event, runs_by_ring=runs_by_ring, judges=judges)

@live_bp.route('/live/run_entry/<event_id>/<uuid:run_id>')
def live_run_entry(event_id, run_id):
    run_id = str(run_id)
    events = _load_data('events.json')
    event = next((e for e in events if e.get('id') == event_id), None)
    run = next((r for r in event.get('runs', []) if r.get('id') == run_id), None) if event else None
    if not event or not run: abort(404)
    all_entries_json = json.dumps(run.get('entries', []))
    return render_template('live_run_entry.html', event=event, run=run, all_entries_json=all_entries_json, run_id_from_url=run_id)

@live_bp.route('/live/save_result/<event_id>/<uuid:run_id>', methods=['POST'])
def save_result(event_id, run_id):
    run_id = str(run_id)
    data = request.json
    license_nr = data.get('license_number')
    events = _load_data('events.json')
    event = next((e for e in events if e.get('id') == event_id), None)
    run = next((r for r in event.get('runs', []) if r.get('id') == run_id), None) if event else None
    if not all([event, run, license_nr]):
        return jsonify({"success": False, "message": "Event, Lauf oder Lizenznummer nicht gefunden."}), 404
    entry = next((e for e in run.get('entries', []) if e.get('Lizenznummer') == license_nr), None)
    if not entry:
        return jsonify({"success": False, "message": "Teilnehmer nicht in diesem Lauf gefunden."}), 404
    entry['result'] = {'zeit': data.get('zeit'), 'fehler': data.get('fehler', 0), 'verweigerungen': data.get('verweigerungen', 0), 'disqualifikation': data.get('disqualifikation', None)}
    entry['timestamp'] = datetime.now().isoformat()
    _save_data('events.json', events)
    socketio.emit('result_update', {'run_id': run_id, 'license_nr': license_nr, 'result': entry['result']})
    if run.get('assigned_ring'):
        socketio.emit('announcer_update', {'event_id': event_id, 'ring_name': f"Ring {run.get('assigned_ring')}"})
    return jsonify({"success": True, "message": "Ergebnis erfolgreich gespeichert."})
    
@live_bp.route('/live/ranking/<event_id>/<uuid:run_id>')
def show_ranking(event_id, run_id):
    run_id = str(run_id)
    events = _load_data('events.json')
    event = next((e for e in events if e.get('id') == event_id), None)
    run = next((r for r in event.get('runs', []) if r.get('id') == run_id), None)
    if not event or not run: abort(404)
    settings = _load_settings()
    rankings = _calculate_run_results(run, settings)
    judges = _load_data('judges.json')
    calculated_sct = run.get('laufdaten', {}).get('standardzeit_sct_berechnet') or run.get('laufdaten', {}).get('standardzeit_sct')
    return render_template('ranking.html', event=event, run=run, rankings=rankings, judges=judges, calculated_sct=calculated_sct)

@live_bp.route('/announcer_dashboard/<event_id>')
def announcer_dashboard(event_id):
    event = next((e for e in _load_data('events.json') if e.get('id') == event_id), None)
    if not event: abort(404)
    return render_template('announcer_dashboard.html', event=event, kiosk_mode=True)

@live_bp.route('/live/set_active_announcer_run/<event_id>/<uuid:run_id>')
def set_active_announcer_run(event_id, run_id):
    run_id = str(run_id)
    event, run = _get_active_event(), next((r for r in _get_active_event().get('runs', []) if r.get('id') == run_id), None)
    if not event or not run or not run.get('assigned_ring'):
        flash("Lauf konnte nicht für Sprecher aktiviert werden.", "warning")
        return redirect(url_for('live_bp.live_event_dashboard'))
    ring_name = f"Ring {run['assigned_ring']}"
    active_runs = session.get('active_announcer_runs', {})
    if event_id not in active_runs: active_runs[event_id] = {}
    active_runs[event_id][ring_name] = {'run_id': run['id'], 'run_name': run['name']}
    session['active_announcer_runs'] = active_runs
    session.modified = True
    socketio.emit('announcer_update', {'event_id': event_id, 'ring_name': ring_name})
    flash(f"'{run['name']}' ist jetzt aktiv für die Anzeige auf {ring_name}.", "success")
    if 'from_ring_pc' in request.args:
        return redirect(url_for('live_bp.ring_pc_dashboard', ring_number=run['assigned_ring']))
    return redirect(url_for('live_bp.live_run_entry', event_id=event_id, run_id=run_id))

@live_bp.route('/ring_monitor/<int:ring_number>')
def display_ring_monitor(ring_number):
    event = _get_active_event()
    if not event: return "Kein aktives Event."
    return render_template('ring_monitor.html', event=event, ring_name=f"Ring {ring_number}", kiosk_mode=True)

@live_bp.route('/ring_pc_dashboard/<int:ring_number>')
def ring_pc_dashboard(ring_number):
    event = _get_active_event()
    if not event: return "Kein aktives Event."
    ring_name = f"Ring {ring_number}"
    runs_for_ring = [r for r in event.get('runs', []) if r.get('assigned_ring') == str(ring_number)]
    return render_template('ring_pc_dashboard.html', event=event, ring_name=ring_name, runs=runs_for_ring)

@live_bp.route('/api/render_speaker_panel_content/<event_id>/<ring_name>')
def render_speaker_panel_content(event_id, ring_name):
    event = next((e for e in _load_data('events.json') if e.get('id') == event_id), None)
    if not event: abort(404)
    ring_data = _get_live_data_for_ring(event, ring_name)
    return render_template('_speaker_panel_content.html', event_id=event_id, ring_name=ring_name, ring_data=ring_data)

@live_bp.route('/api/render_announcer_schedule/<event_id>')
def render_announcer_schedule(event_id):
    event = next((e for e in _load_data('events.json') if e.get('id') == event_id), None)
    if not event: abort(404)
    timelines_by_ring = _calculate_timelines(event)
    return render_template('_announcer_schedule.html', timelines_by_ring=timelines_by_ring)

@live_bp.route('/api/render_ring_monitor_content/<int:ring_number>')
def render_ring_monitor_content(ring_number):
    event, ring_name = _get_active_event(), f"Ring {ring_number}"
    if not event: return ""
    ring_data = _get_live_data_for_ring(event, ring_name)
    return render_template('_ring_monitor_content.html', ring_data=ring_data)
