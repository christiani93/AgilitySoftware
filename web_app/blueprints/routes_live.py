# --- FIXED HEADER: routes_live.py ---
from flask import Blueprint, render_template, request, jsonify, abort, flash, redirect, url_for, session, Response
from datetime import datetime
import json
import math
import re

from pathlib import Path

from extensions import socketio
from utils import (_load_data, _save_data, _get_active_event,
                   _calculate_run_results, _load_settings, _get_active_event_id,
                   _calculate_timelines)

live_bp = Blueprint('live_bp', __name__, template_folder='../templates')

# --- LIVE STATE + RING NORMALIZATION HELPERS (auto-insert) ---
# Persistenter Live-State: welches Event/Ring zeigt welchen aktiven Lauf?
# Speicherung in data/live_state.json via utils._load_data/_save_data
STATE_FILE = "live_state.json"

def _load_live_state():
    try:
        from utils import _load_data
        data = _load_data(STATE_FILE)
        return data if isinstance(data, dict) else {}
    except Exception:
        # Fallback ohne utils
        p = (Path(__file__).resolve().parent.parent / "data" / STATE_FILE)
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8")) or {}
            except Exception:
                return {}
        return {}

def _save_live_state(state: dict):
    try:
        from utils import _save_data
        _save_data(STATE_FILE, state or {})
    except Exception:
        # Fallback ohne utils
        p = (Path(__file__).resolve().parent.parent / "data" / STATE_FILE)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(state or {}, ensure_ascii=False, indent=2), encoding="utf-8")

def _norm_ring_strict(val, default_one=True):
    """
    Normalisiert Ring-Bezeichner robust auf Form "ring_<N>".
    Akzeptiert z.B.: 1, "1", "Ring 1", "ring_1", "Ring ring_1".
    """
    s = ("" if val is None else str(val)).strip()
    if not s:
        return "ring_1" if default_one else None
    low = s.lower().strip()
    # Entferne Variationen von "ring"
    low = (low
           .replace("ring ", " ")
           .replace("ring_", " ")
           .replace("ring", " ")
           .strip())
    # Extrahiere Ziffern
    digits = re.sub(r"[^0-9]", "", low)
    if digits:
        try:
            n = int(digits)
            return f"ring_{n}" if n >= 1 else ("ring_1" if default_one else None)
        except Exception:
            pass
    # Falls bereits korrekt
    if s.lower().startswith("ring_"):
        return s.lower()
    return "ring_1" if default_one else None
# --- END HELPERS ---


# --- END FIXED HEADER ---

@live_bp.route('/debug/live_state')
def debug_live_state():
    from flask import jsonify
    return jsonify(_load_live_state())
def _get_live_data_for_ring(event, ring_name):
    # aktiver Lauf aus persistentem State
    state = _load_live_state()
    evt_id = event.get('id') or event.get('event_id') or ''
    # Beide Schlüsselvarianten testen
    active = None
    for k in _ring_state_keys(ring_name):
        active = (state.get(evt_id, {}) or {}).get(k)
        if active:
            break
    if not active:
        return None

    run_id = active.get('run_id')
    run = next((r for r in event.get('runs', []) if r.get('id') == run_id), None)
    if not run:
        return None

    settings = _load_settings()
    all_results = _calculate_run_results(run, settings)
    last_results = sorted(
        [res for res in all_results if res.get('platz')],
        key=lambda x: x.get('timestamp', 0), reverse=True
    )[:5]



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

@live_bp.route('/live/save_result/<event_id>/<uuid:run_id>', methods=['POST','GET'])
def save_result(event_id, run_id):
    run_id = str(run_id)

    # Daten annehmen (JSON-POST bevorzugt, GET mit Query-Fallback)
    try:
        from flask import request
    except Exception:
        request = None

    data = {}
    if request is not None and getattr(request, 'method', '') == 'POST':
        try:
            data = request.get_json(force=True, silent=True) or {}
        except Exception:
            data = {}
    elif request is not None and getattr(request, 'method', '') == 'GET':
        # Fallback: /live/save_result/... ?license_number=...&zeit=...&fehler=...&verweigerungen=...&disqualifikation=...
        q = request.args or {}
        data = {
            'license_number': q.get('license_number'),
            'zeit': q.get('zeit'),
            'fehler': q.get('fehler', 0),
            'verweigerungen': q.get('verweigerungen', 0),
            'disqualifikation': q.get('disqualifikation')
        }

    license_nr = data.get('license_number')
    from utils import _load_data, _save_data, _load_settings, _calculate_run_results
    events = _load_data('events.json')
    event = next((e for e in events if e.get('id') == event_id), None)
    run = next((r for r in (event.get('runs', []) if event else []) if r.get('id') == run_id), None)

    if not all([event, run, license_nr]):
        return jsonify({"success": False, "message": "Event, Lauf oder Lizenznummer nicht gefunden."}), 404

    entry = next((e for e in run.get('entries', []) if e.get('Lizenznummer') == license_nr), None)
    if not entry:
        return jsonify({"success": False, "message": "Teilnehmer nicht in diesem Lauf gefunden."}), 404

    try:
        # Werte normalisieren
        zeit = data.get('zeit')
        fehler = int(data.get('fehler') or 0)
        verweigerungen = int(data.get('verweigerungen') or 0)
        disq = data.get('disqualifikation') or None

        entry['result'] = {
            'zeit': zeit,
            'fehler': fehler,
            'verweigerungen': verweigerungen,
            'disqualifikation': disq
        }
        entry['timestamp'] = datetime.now().isoformat()
        _save_data('events.json', events)

        # Realtime Updates
        try:
            socketio.emit('result_update', {'run_id': run_id, 'license_nr': license_nr, 'result': entry['result']})
            if run.get('assigned_ring'):
                ring_num = run.get('assigned_ring')
                socketio.emit('announcer_update', {'event_id': event_id, 'ring_name': f"Ring {ring_num}"})
        except Exception:
            pass

        return jsonify({"success": True, "message": "Ergebnis erfolgreich gespeichert.", "result": entry['result']})
    except Exception as ex:
        return jsonify({"success": False, "message": f"Fehler beim Speichern: {ex}"}), 500


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
    # Setzt den aktiven Lauf für Sprecher/Monitore.
    # Schreibt kanonisch NUR unter "Ring N" in live_state.json und entfernt Alt-Keys.
    run_id = str(run_id)

    event = _get_active_event()
    run = next((r for r in (event.get('runs', []) if event else []) if r.get('id') == run_id), None)

    if not event or not run or not run.get('assigned_ring'):
        flash('Lauf konnte nicht für Sprecher/Monitore aktiviert werden.', 'warning')
        return redirect(url_for('live_bp.live_event_dashboard'))

    # kanonisches Label "Ring N"
    try:
        n = int(re.sub(r"[^0-9]", "", str(run.get('assigned_ring'))))
    except Exception:
        n = 1
    ring_label = f"Ring {n}"

    # State laden
    state = _load_live_state()
    if not isinstance(state, dict):
        state = {}
    evt_id = event.get('id') or event.get('event_id') or ''
    by_event = state.get(evt_id, {})
    if not isinstance(by_event, dict):
        by_event = {}

    # Alle Nicht-Kanonischen Keys zur gleichen Ringnummer entfernen
    # z.B. "Ring ring_1", "ring_1", "Ring 01", etc.
    to_delete = []
    for k in list(by_event.keys()):
        if re.sub(r"[^0-9]", "", str(k) or "") == str(n) and k != ring_label:
            to_delete.append(k)
    for k in to_delete:
        by_event.pop(k, None)

    # Setzen
    by_event[ring_label] = {'run_id': run.get('id'), 'run_name': run.get('name')}
    state[evt_id] = by_event
    _save_live_state(state)

    # Echtzeit-Update
    try:
        from extensions import socketio
        socketio.emit('announcer_update', {'event_id': evt_id, 'ring_name': ring_label})
    except Exception:
        pass

    flash(f"'{run.get('name')}' ist jetzt aktiv für die Anzeige auf {ring_label}.", 'success')

    # Falls vom Ring-PC aufgerufen, zurück zum Ring-Dashboard
    if 'from_ring_pc' in request.args:
        return redirect(url_for('live_bp.ring_pc_dashboard', ring_number=n))
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
    target = _norm_ring_strict(ring_number)
    runs_for_ring = []
    for r in event.get('runs', []):
        assigned = r.get('assigned_ring') or r.get('ring') or r.get('ring_id') or r.get('ringName')
        if assigned and _norm_ring_strict(assigned) == target:
            runs_for_ring.append(r)
    return render_template('ring_pc_dashboard.html', event=event, ring_name=ring_name, runs=runs_for_ring)

@live_bp.route('/api/render_announcer_schedule/<event_id>')
def render_announcer_schedule(event_id):
    event = next((e for e in _load_data('events.json') if e.get('id') == event_id), None)
    if not event:
        abort(404)
    timelines_by_ring = _calculate_timelines(event)
    return render_template('_announcer_schedule.html', timelines_by_ring=timelines_by_ring)

@live_bp.route('/api/render_speaker_panel_content/<event_id>/<ring_name>')
def render_speaker_panel_content(event_id, ring_name):
# 1) Versuche aktiven Lauf per State
    try:
        norm_req = _norm_ring_strict(ring_name)
    except Exception:
        norm_req = 'ring_1'
    try:
        events = _load_data('events.json')
    except Exception:
        events = []
    event = next((e for e in events if isinstance(e, dict) and e.get('id') == event_id), None)

    # Wenn Event vorhanden und State aktiv -> zeige aktiven Lauf kurzformatig
    if event:
        # Suche aktive Daten per tolerantem Label
        ring_label_display = _ring_label_for_display(ring=norm_req)
        data = _get_live_data_for_ring(event, ring_label_display)
        if not data:
            # evtl. "Ring 1" vs "Ring ring_1"
            data = _get_live_data_for_ring(event, f"Ring {re.sub(r'[^0-9]','', ring_label_display)}") if re else None
        if data:
            parts = [f"<div class='speaker-panel'><h2>{ring_label_display} – {data.get('run_name','')}</h2>"]
            def _fmt(p):
                if not p: return '-'
                return f"{p.get('Startnummer','')} – {p.get('Hundeführer','')} mit {p.get('Hundename','')} ({p.get('Lizenznummer','')})"
            parts.append(f"<p><strong>Am Start:</strong> {_fmt(data.get('current_starter'))}</p>")
            parts.append(f"<p><strong>Bereit:</strong> {_fmt(data.get('next_starter'))}</p>")
            last = data.get('last_results') or []
            if last:
                parts.append('<h3>Letzte Resultate</h3><ul>')
                for r in last:
                    parts.append(f"<li>{r.get('Startnummer','')} – {r.get('hundename','')} : {r.get('zeit','?')}s, P={r.get('platz','-')}</li>")
                parts.append('</ul>')
            parts.append('</div>')
            return Response(''.join(parts), mimetype='text/html')

    # 2) Fallback: alter Zeitplan wie bisher
    try:
        from utils import _get_concrete_run_list
    except Exception:
        _get_concrete_run_list = None
    if not event:
        return Response(
            f"<div class='speaker-panel'><h2>{_ring_label_for_display(ring=norm_req)}</h2><p>Event nicht gefunden.</p></div>",
            mimetype='text/html'
        )
    ring_runs = []
    if _get_concrete_run_list:
        try:
            schedule_runs = _get_concrete_run_list(event)
            for r in schedule_runs:
                assigned = r.get('assigned_ring') or r.get('ring') or r.get('ring_id') or r.get('ringName')
                if assigned and _norm_ring_strict(assigned) == norm_req:
                    ring_runs.append(r)
        except Exception:
            pass
    if not ring_runs:
        for r in event.get('runs', []):
            assigned = r.get('assigned_ring') or r.get('ring') or r.get('ring_id') or r.get('ringName')
            if assigned and _norm_ring_strict(assigned) == norm_req:
                ring_runs.append(r)
    if not ring_runs and int(event.get('num_rings', 1)) == 1:
        ring_runs = event.get('runs', []) or []
    out = [f"<div class='speaker-panel'><h2>{_ring_label_for_display(ring=norm_req)}</h2>"]
    if not ring_runs:
        out.append('<p>Keine Läufe für diesen Ring.</p></div>')
        return Response(''.join(out), mimetype='text/html')
    out.append('<ol>')
    for r in ring_runs[:30]:
        title = r.get('name') or f"{r.get('laufart','?')} {r.get('kategorie','?')} {r.get('klasse','?')}"
        out.append(f"<li>{title}</li>")
    out.append('</ol></div>')
    return Response(''.join(out), mimetype='text/html')

    out.append("<ol>")
    for r in ring_runs[:30]:
        title = r.get('name') or f"{r.get('laufart','?')} {r.get('kategorie','?')} {r.get('klasse','?')}"
        out.append(f"<li>{title}</li>")
    out.append("</ol></div>")
    return Response(''.join(out), mimetype='text/html')


    ring_label = _ring_label_for_display(ring=ring_name)
    events = _load_data('events.json')
    event = next((e for e in events if isinstance(e, dict) and e.get('id') == event_id), None)
    if not event:
        return Response(f"<div class='speaker-panel'><h2>{ring_label}</h2><p>Event nicht gefunden.</p></div>", mimetype='text/html')

    state = _load_live_state()
    active = None
    evt_id = event.get('id') or event.get('event_id') or ''
    for _k in _ring_state_keys(ring_label):
        active = (state.get(evt_id, {}) or {}).get(_k)
        if active:
            break

    if active:
        # Live-Ansicht wie beim Ringmonitor, aber als Sprecher-Panel
        run_id = active.get('run_id')
        run = next((r for r in event.get('runs', []) if r.get('id') == run_id), None)
        if run:
            settings = _load_settings()
            all_results = _calculate_run_results(run, settings)

            last_results = sorted(
                [res for res in all_results if res.get('platz')],
                key=lambda x: x.get('timestamp', 0),
                reverse=True
            )[:5]

            def _num(v):
                try:
                    return int(v)
                except Exception:
                    return 999999

            participants = sorted(run.get('entries', []), key=lambda x: _num(x.get('Startnummer')))
            pending = [p for p in participants if not p.get('result')]
            current_starter = pending[0] if pending else None
            next_starter = pending[1] if len(pending) > 1 else None

            def _fmt(p):
                if not p:
                    return '-'
                return f"{p.get('Startnummer','')} – {p.get('Hundeführer','')} mit {p.get('Hundename','')} ({p.get('Lizenznummer','')})"

            parts = [f"<div class='speaker-panel'><h2>{ring_label} – {run.get('name','')}</h2>"]
            parts.append(f"<p><strong>Am Start:</strong> {_fmt(current_starter)}</p>")
            parts.append(f"<p><strong>Bereit:</strong> {_fmt(next_starter)}</p>")
            if last_results:
                parts.append("<h3>Letzte Resultate</h3><ul>")
                for r in last_results:
                    parts.append(f"<li>{r.get('Startnummer','')} – {r.get('hundename','')} : {r.get('zeit','?')}s, P={r.get('platz','-')}</li>")
                parts.append("</ul>")
            parts.append("</div>")
            return Response(''.join(parts), mimetype='text/html')

    # 2) Fallback: Plan-Liste für den Ring (wie bisher)
    norm_req = _norm_ring_strict(ring_name)
    try:
        from utils import _get_concrete_run_list
    except Exception:
        _get_concrete_run_list = None

    ring_runs = []
    if _get_concrete_run_list:
        try:
            schedule_runs = _get_concrete_run_list(event)
            for r in schedule_runs:
                assigned = r.get('assigned_ring') or r.get('ring') or r.get('ring_id') or r.get('ringName')
                if assigned and _norm_ring_strict(assigned) == norm_req:
                    ring_runs.append(r)
        except Exception:
            pass
    if not ring_runs:
        for r in event.get('runs', []):
            assigned = r.get('assigned_ring') or r.get('ring') or r.get('ring_id') or r.get('ringName')
            if assigned and _norm_ring_strict(assigned) == norm_req:
                ring_runs.append(r)
    if not ring_runs and int(event.get('num_rings', 1)) == 1:
        ring_runs = event.get('runs', []) or []

    out = [f"<div class='speaker-panel'><h2>{ring_label}</h2>"]
    if not ring_runs:
        out.append("<p>Keine Läufe für diesen Ring.</p></div>")
        return Response(''.join(out), mimetype='text/html')

    out.append("<ol>")
    for r in ring_runs[:30]:
        title = r.get('name') or f"{r.get('laufart','?')} {r.get('kategorie','?')} {r.get('klasse','?')}"
        out.append(f"<li>{title}</li>")
    out.append("</ol></div>")
    return Response(''.join(out), mimetype='text/html')


    try:
        from utils import _get_concrete_run_list
    except Exception:
        _get_concrete_run_list = None
    events = _load_data('events.json')
    event = next((e for e in events if isinstance(e, dict) and e.get('id') == event_id), None)
    if not event:
        return Response(
            f"<div class='speaker-panel'><h2>{_ring_label_for_display(ring=norm_req)}</h2><p>Event nicht gefunden.</p></div>",
            mimetype='text/html'
        )
    ring_runs = []
    if _get_concrete_run_list:
        try:
            schedule_runs = _get_concrete_run_list(event)
            for r in schedule_runs:
                assigned = r.get('assigned_ring') or r.get('ring') or r.get('ring_id') or r.get('ringName')
                if assigned and _norm_ring_strict(assigned) == norm_req:
                    ring_runs.append(r)
        except Exception:
            pass
    if not ring_runs:
        for r in event.get('runs', []):
            assigned = r.get('assigned_ring') or r.get('ring') or r.get('ring_id') or r.get('ringName')
            if assigned and _norm_ring_strict(assigned) == norm_req:
                ring_runs.append(r)
    if not ring_runs and int(event.get('num_rings', 1)) == 1:
        ring_runs = event.get('runs', []) or []
    out = [f"<div class='speaker-panel'><h2>{_ring_label_for_display(ring=norm_req)}</h2>"]
    if not ring_runs:
        out.append('<p>Keine Läufe für diesen Ring.</p></div>')
        return Response(''.join(out), mimetype='text/html')
    out.append('<ol>')
    for r in ring_runs[:30]:
        title = r.get('name') or f"{r.get('laufart','?')} {r.get('kategorie','?')} {r.get('klasse','?')}"
        out.append(f"<li>{title}</li>")
    out.append('</ol></div>')
    return Response(''.join(out), mimetype='text/html')
def _ring_label_for_display(ring=None, ring_number=None):
    """Gibt ein robustes Label 'Ring X' zurück und akzeptiert sowohl 'ring' als auch 'ring_number'.
    Normalisiert auch Werte wie 'ring_1', 'Ring 1', '1'."""
    s = None
    if ring is not None:
        s = str(ring).strip()
    elif ring_number is not None:
        s = str(ring_number).strip()
    else:
        return "Ring ?"
    digits = re.sub(r"[^0-9]", "", s)
    if digits:
        try:
            n = int(digits)
            return f"Ring {n}"
        except Exception:
            pass
    return f"Ring {s}"

def _ring_state_keys(ring_hint: str):
    # Liefert alle sinnvollen Schlüsselvarianten für den Live-State:
    # - "Ring 1" (Anzeige/neu)
    # - "Ring ring_1" (Altformat)
    disp = _ring_label_for_display(ring=ring_hint)   # z.B. "Ring 1"
    norm = _norm_ring_strict(ring_hint)              # z.B. "ring_1"
    return [disp, f"Ring {norm}"]

@live_bp.route('/api/render_ring_monitor_content/<int:ring_number>')
def render_ring_monitor_content(ring_number: int):
    ring_label = _ring_label_for_display(ring_number=ring_number)
    event = _get_active_event()
    if not event:
        return Response("<div class='ring-monitor'><p>Kein aktives Event.</p></div>", mimetype='text/html')
    data = _get_live_data_for_ring(event, ring_label)
    if not data:
        html = f"<div class='ring-monitor'><h2>{ring_label}</h2><p>Kein Lauf wurde für diesen Ring aktiviert.</p></div>"
        return Response(html, mimetype='text/html')
    parts = [f"<div class='ring-monitor'><h2>{ring_label} – {data.get('run_name','')}</h2>"]
    def _fmt(p):
        if not p:
            return '-'
        return f"{p.get('Startnummer','')} – {p.get('Hundeführer','')} mit {p.get('Hundename','')} ({p.get('Lizenznummer','')})"
    parts.append(f"<p><strong>Am Start:</strong> {_fmt(data.get('current_starter'))}</p>")
    parts.append(f"<p><strong>Bereit:</strong> {_fmt(data.get('next_starter'))}</p>")
    last = data.get('last_results') or []
    if last:
        parts.append('<h3>Letzte Resultate</h3><ul>')
        for r in last:
            parts.append(f"<li>{r.get('Startnummer','')} – {r.get('hundename','')} : {r.get('zeit','?')}s, P={r.get('platz','-')}</li>")
        parts.append('</ul>')
    parts.append('</div>')
    return Response(''.join(parts), mimetype='text/html')