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
                   _calculate_timelines, resolve_judge_name, resolve_judge_id, _to_int,
                   build_ring_view_model, collect_ring_numbers, format_ring_name,
                   _format_time, _format_total_errors, get_ring_state)
import planner.schedule_planner as schedule_planner

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


def _schedule_runs_for_ring(event, ring_key):
    schedule = event.get("schedule") or {}
    rings = schedule.get("rings") or {}
    ring_data = rings.get(str(ring_key)) or {}
    blocks = ring_data.get("blocks") or []
    debug = []
    runs_for_ring = []
    seen_ids = set()
    for block in blocks:
        block_type = (block.get("type") or block.get("block_type") or "").lower()
        if block_type != "run":
            debug.append(f"skip:{block_type or 'unknown'}")
            continue
        matched = [
            run for run in event.get("runs", []) or []
            if isinstance(run, dict) and schedule_planner._match_run_to_block(run, block)
        ]
        if not matched:
            debug.append(f"no_match:{block.get('title') or block.get('label') or block.get('laufart') or 'run'}")
            continue
        for run in matched:
            run_id = run.get("id")
            if run_id and run_id in seen_ids:
                continue
            if run_id:
                seen_ids.add(run_id)
            runs_for_ring.append(run)
    return runs_for_ring, debug


def _find_run_block_for_run(event, run, ring_key: str | None = None):
    schedule = event.get("schedule") or {}
    rings = schedule.get("rings") or {}
    ring_keys = [ring_key] if ring_key is not None else list(rings.keys())
    for key in ring_keys:
        ring_data = rings.get(str(key)) or {}
        for block in ring_data.get("blocks") or []:
            block_type = (block.get("type") or block.get("block_type") or "").lower()
            if block_type != "run":
                continue
            if schedule_planner._match_run_to_block(run, block):
                return block, str(key)
    return None, None


def _persist_current_run(events, event_id, ring_key, run_block_id):
    updated = False
    for event in events:
        if event.get("id") != event_id:
            continue
        current = event.get("current_run_blocks") or {}
        current[str(ring_key)] = {
            "run_block_id": run_block_id,
            "updated_at": datetime.utcnow().isoformat(),
        }
        event["current_run_blocks"] = current
        updated = True
        break
    return updated


def _infer_ring_number(event, run, fallback=1):
    run_block, ring_key = _find_run_block_for_run(event, run)
    if ring_key:
        try:
            return int(re.sub(r"[^0-9]", "", str(ring_key)))
        except Exception:
            pass
    assigned_ring = run.get('assigned_ring') or run.get('ring') or run.get('ring_id') or run.get('ringName')
    digits = re.sub(r"[^0-9]", "", str(assigned_ring or ""))
    if digits:
        try:
            return int(digits)
        except Exception:
            pass
    return fallback


def _build_ring_payload(event, ring_number):
    view = build_ring_view_model(event, ring_number)
    current_run = view.get("current_run") or {}
    payload = {
        "ring_no": ring_number,
        "run_id": current_run.get("id"),
        "run_meta": current_run,
        "current_starter": view.get("current_starter") or {},
        "startlist_next": view.get("startlist") or [],
        "ranking_top": view.get("ranking") or [],
        "last_results": view.get("last_results") or [],
    }
    return payload


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
    run_block_id = active.get('run_block_id')
    run = next((r for r in event.get('runs', []) if r.get('id') == run_id), None)
    if not run:
        return None

    settings = _load_settings()
    all_results = _calculate_run_results(run, settings)
    last_results = sorted(
        [res for res in all_results if res.get('platz')],
        key=lambda x: x.get('timestamp', 0), reverse=True
    )[:5]
    judges = _load_data('judges.json')
    run_block = None
    if run_block_id:
        schedule = event.get("schedule") or {}
        for ring_key, ring_data in (schedule.get("rings") or {}).items():
            for block in ring_data.get("blocks") or []:
                if block.get("id") == run_block_id:
                    run_block = block
                    break
            if run_block:
                break
    if not run_block:
        run_block, _ = _find_run_block_for_run(event, run)
    judge_name = resolve_judge_name(event, run, judges, run_block)

    return {
        "run": run,
        "run_name": run.get("name"),
        "run_block_id": run_block_id,
        "judge_name": judge_name,
        "current_starter": run.get("current_starter"),
        "next_starter": run.get("next_starter"),
        "last_results": last_results,
    }
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
    ring_numbers = collect_ring_numbers(event)
    ring_cards = [get_ring_state(event, ring_number) for ring_number in ring_numbers]
    return render_template(
        'live_event_dashboard.html',
        event=event,
        ring_numbers=ring_numbers,
        ring_cards=ring_cards,
    )

@live_bp.route('/live/run_entry/<event_id>/<uuid:run_id>')
def live_run_entry(event_id, run_id):
    run_id = str(run_id)
    events = _load_data('events.json')
    event = next((e for e in events if e.get('id') == event_id), None)
    run = next((r for r in event.get('runs', []) if r.get('id') == run_id), None) if event else None
    if not event or not run: abort(404)
    settings = _load_settings()
    _calculate_run_results(run, settings)
    laufdaten = run.get('laufdaten', {})
    sct_display = laufdaten.get('standardzeit_sct_gerundet') or laufdaten.get('standardzeit_sct_berechnet') or laufdaten.get('standardzeit_sct') or 'N/A'
    mct_display = laufdaten.get('maximalzeit_mct_gerundet') or laufdaten.get('maximalzeit_mct_berechnet') or laufdaten.get('maximalzeit_mct') or 'N/A'
    all_entries_json = json.dumps(run.get('entries', []))
    return render_template('live_run_entry.html', event=event, run=run, all_entries_json=all_entries_json, run_id_from_url=run_id, sct_display=sct_display, mct_display=mct_display)

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
            ring_no = _infer_ring_number(event, run)
            payload = _build_ring_payload(event, ring_no)
            payload.update({
                "event_id": event_id,
                "entry_id": license_nr,
            })
            ring_room = f"event:{event_id}:ring:{ring_no}"
            socketio.emit('ring_result_saved', payload, room=ring_room)
            socketio.emit('ring_result_saved', payload, room=f"event:{event_id}")
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
    judge_display = resolve_judge_name(event, run, judges)

    laufdaten = run.get('laufdaten', {})
    sct_display = laufdaten.get('standardzeit_sct_gerundet') or laufdaten.get('standardzeit_sct_berechnet') or laufdaten.get('standardzeit_sct') or 'N/A'
    mct_display = laufdaten.get('maximalzeit_mct_gerundet') or laufdaten.get('maximalzeit_mct_berechnet') or laufdaten.get('maximalzeit_mct') or 'N/A'

    return render_template(
        'ranking.html',
        event=event,
        run=run,
        rankings=rankings,
        judges=judges,
        judge_display=judge_display,
        sct_display=sct_display,
        mct_display=mct_display,
    )

@live_bp.route('/announcer_dashboard/<event_id>')
def announcer_dashboard(event_id):
    event = next((e for e in _load_data('events.json') if e.get('id') == event_id), None)
    if not event: abort(404)
    ring_numbers = collect_ring_numbers(event)
    return render_template('announcer_dashboard.html', event=event, ring_numbers=ring_numbers, kiosk_mode=True)
@live_bp.route('/live/set_active_announcer_run/<event_id>/<uuid:run_id>')
def set_active_announcer_run(event_id, run_id):
    # Setzt den aktiven Lauf für Sprecher/Monitore.
    # Schreibt kanonisch NUR unter "Ring N" in live_state.json und entfernt Alt-Keys.
    run_id = str(run_id)

    event = _get_active_event()
    run = next((r for r in (event.get('runs', []) if event else []) if r.get('id') == run_id), None)
    ring_hint = request.args.get('ring')

    if not event or not run:
        flash('Lauf konnte nicht für Sprecher/Monitore aktiviert werden.', 'warning')
        return redirect(url_for('live_bp.live_event_dashboard'))

    run_block = None
    ring_key = None
    if ring_hint:
        run_block, ring_key = _find_run_block_for_run(event, run, str(ring_hint))
    if not run_block:
        run_block, ring_key = _find_run_block_for_run(event, run)
    if not ring_key:
        assigned_ring = run.get('assigned_ring') or run.get('ring') or run.get('ring_id') or run.get('ringName')
        ring_key = re.sub(r"[^0-9]", "", str(assigned_ring or "1")) or "1"
    ring_label = f"Ring {ring_key}"

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
        if re.sub(r"[^0-9]", "", str(k) or "") == str(ring_key) and k != ring_label:
            to_delete.append(k)
    for k in to_delete:
        by_event.pop(k, None)

    judges = _load_data('judges.json')
    judge_name = resolve_judge_name(event, run, judges, run_block)
    # Setzen
    by_event[ring_label] = {
        'run_id': run.get('id'),
        'run_name': run.get('name'),
        'run_block_id': run_block.get('id') if run_block else None,
        'judge_name': judge_name,
    }
    state[evt_id] = by_event
    _save_live_state(state)
    events = _load_data('events.json')
    if _persist_current_run(events, evt_id, ring_key, run_block.get('id') if run_block else None):
        _save_data('events.json', events)

    # Echtzeit-Update
    try:
        from extensions import socketio
        ring_room = f"event:{evt_id}:ring:{ring_key}"
        socketio.emit('announcer_update', {'event_id': evt_id, 'ring_name': ring_label}, room=ring_room)
        socketio.emit('current_run_changed', {'event_id': evt_id, 'ring_id': ring_key, 'run_block_id': run_block.get('id') if run_block else None}, room=ring_room)
        socketio.emit('current_run_changed', {'event_id': evt_id, 'ring_id': ring_key, 'run_block_id': run_block.get('id') if run_block else None}, room=f"event:{evt_id}")
        payload = _build_ring_payload(event, int(ring_key))
        payload.update({"event_id": evt_id})
        socketio.emit('ring_run_changed', payload, room=ring_room)
        socketio.emit('ring_run_changed', payload, room=f"event:{evt_id}")
    except Exception:
        pass

    flash(f"'{run.get('name')}' ist jetzt aktiv für die Anzeige auf {ring_label}.", 'success')

    # Falls vom Ring-PC aufgerufen, zurück zum Ring-Dashboard
    if 'from_ring_pc' in request.args:
        return redirect(url_for('live_bp.ring_pc_dashboard', ring_number=int(ring_key)))
    return redirect(url_for('live_bp.live_run_entry', event_id=event_id, run_id=run_id))


@live_bp.route('/live/api/ring_starter_changed', methods=['POST'])
def ring_starter_changed():
    data = request.get_json(silent=True) or {}
    event_id = data.get("event_id")
    ring_no = data.get("ring_no")
    if not event_id or not ring_no:
        return jsonify({"success": False, "message": "event_id oder ring_no fehlt"}), 400
    events = _load_data('events.json')
    event = next((e for e in events if e.get('id') == event_id), None)
    if not event:
        return jsonify({"success": False, "message": "Event nicht gefunden"}), 404
    try:
        ring_no = int(ring_no)
    except Exception:
        ring_no = 1
    payload = _build_ring_payload(event, ring_no)
    payload.update({"event_id": event_id})
    try:
        ring_room = f"event:{event_id}:ring:{ring_no}"
        socketio.emit('ring_starter_changed', payload, room=ring_room)
        socketio.emit('ring_starter_changed', payload, room=f"event:{event_id}")
    except Exception:
        pass
    return jsonify({"success": True})

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
    schedule = event.get("schedule") or {}
    schedule_rings = schedule.get("rings") or {}
    if schedule_rings:
        ring_key = str(ring_number)
        runs_for_ring, debug = _schedule_runs_for_ring(event, ring_key)
        judges = _load_data('judges.json')
        for run in runs_for_ring:
            run_block, _ = _find_run_block_for_run(event, run, ring_key)
            run["judge_display"] = resolve_judge_name(event, run, judges, run_block)
        if not runs_for_ring and debug:
            flash(
                f"Zeitplan gefunden, aber keine Lauf-Blöcke für {ring_name}: {', '.join(debug)}",
                "warning",
            )
    else:
        for r in event.get('runs', []):
            assigned = r.get('assigned_ring') or r.get('ring') or r.get('ring_id') or r.get('ringName')
            if assigned and _norm_ring_strict(assigned) == target:
                runs_for_ring.append(r)
    selected_run_id = request.args.get("run_id")
    if not selected_run_id:
        state = _load_live_state()
        evt_id = event.get('id') or event.get('event_id') or ''
        ring_label = f"Ring {ring_number}"
        active = (state.get(evt_id, {}) or {}).get(ring_label)
        if active:
            selected_run_id = active.get("run_id")
    if not selected_run_id:
        ring_key = str(ring_number)
        ring_data = (schedule.get("rings") or {}).get(ring_key) or {}
        for block in ring_data.get("blocks") or []:
            block_type = (block.get("type") or block.get("block_type") or "").lower()
            if block_type != "run":
                continue
            matched = [
                run for run in event.get("runs", []) or []
                if isinstance(run, dict) and schedule_planner._match_run_to_block(run, block)
            ]
            if matched:
                selected_run_id = matched[0].get("id")
                break
    if not selected_run_id and runs_for_ring:
        selected_run_id = runs_for_ring[0].get("id")
    return render_template(
        'ring_pc_dashboard.html',
        event=event,
        ring_name=ring_name,
        runs=runs_for_ring,
        selected_run_id=selected_run_id,
    )

@live_bp.route('/api/render_announcer_schedule/<event_id>')
def render_announcer_schedule(event_id):
    event = next((e for e in _load_data('events.json') if e.get('id') == event_id), None)
    if not event:
        abort(404)
    timelines_by_ring = _calculate_timelines(event)
    return render_template('_announcer_schedule.html', timelines_by_ring=timelines_by_ring)

@live_bp.route('/api/render_speaker_panel_content/<event_id>/<ring_name>')
def render_speaker_panel_content(event_id, ring_name):
    events = _load_data('events.json')
    event = next((e for e in events if isinstance(e, dict) and e.get('id') == event_id), None)
    digits = re.sub(r"[^0-9]", "", str(ring_name))
    ring_number = int(digits) if digits else 1
    ring_label = _ring_label_for_display(ring_number=ring_number)
    if not event:
        return Response(f"<div class='speaker-panel'><h2>{ring_label}</h2><p>Event nicht gefunden.</p></div>", mimetype='text/html')

    view = build_ring_view_model(event, ring_number, max_last_results=3)
    current_run = view.get("current_run")
    if not current_run:
        html = (
            "<div class='card shadow-sm'>"
            "<div class='card-body text-center'>"
            f"<h5 class='mb-1'>{ring_label}</h5>"
            "<div class='text-muted'>Kein Lauf aktiv.</div>"
            "</div></div>"
        )
        return Response(html, mimetype='text/html')

    meta_bits = []
    if current_run.get("klasse"):
        meta_bits.append(f"Klasse: {current_run.get('klasse')}")
    if current_run.get("kategorie"):
        meta_bits.append(f"Kategorie: {current_run.get('kategorie')}")
    if current_run.get("laufart"):
        meta_bits.append(f"Laufart: {current_run.get('laufart')}")
    meta_line = " | ".join(meta_bits) if meta_bits else "—"

    current_starter = view.get("current_starter") or {}
    next_starter = view.get("next_starter") or {}

    parts = [
        "<div class='card shadow-sm h-100'>",
        "<div class='card-body'>",
        f"<h5 class='mb-1'>{ring_label} – {current_run.get('title','')}</h5>",
        f"<div class='text-muted small mb-2'><strong>Richter:</strong> {current_run.get('judge_name','—')}</div>",
        "<div class='small text-muted mb-2'>",
        f"SCT {current_run.get('sct','—')} s · MCT {current_run.get('mct','—')} s · {current_run.get('parcours_laenge','—')} m · {current_run.get('hindernisse','—')} Geräte",
        "</div>",
        f"<div class='small text-muted mb-3'>{meta_line}</div>",
        "<div class='text-uppercase small text-muted'>Aktueller Starter</div>",
        f"<div class='h4 fw-semibold mb-1'>{format_ring_name(current_starter)}</div>",
        "<div class='small text-muted mb-3'>",
        f"Am Start: {format_ring_name(current_starter)}",
        "<br>",
        f"Bereit: {format_ring_name(next_starter)}",
        "</div>",
        "<div class='fw-semibold mb-2'>Letzte 3 Ergebnisse</div>",
    ]

    last_results = view.get("last_results") or []
    if last_results:
        parts.append("<div class='d-flex flex-column gap-1'>")
        for res in last_results:
            platz = res.get("platz") or "—"
            parts.append(
                "<div class='d-flex justify-content-between align-items-center'>"
                f"<span>{platz} – {format_ring_name(res)}</span>"
                f"<span class='text-muted small'>Fehler {_format_total_errors(res)} · Zeit {_format_time(res.get('zeit_total') or res.get('zeit'))} s</span>"
                "</div>"
            )
        parts.append("</div>")
    else:
        parts.append("<div class='text-muted'>Noch keine Ergebnisse.</div>")

    parts.extend(["</div>", "</div>"])
    return Response(''.join(parts), mimetype='text/html')
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
    view = build_ring_view_model(event, ring_number)
    current_run = view.get("current_run")
    if not current_run:
        html = f"<div class='ring-monitor'><h2>{ring_label}</h2><p>Kein Lauf wurde für diesen Ring aktiviert.</p></div>"
        return Response(html, mimetype='text/html')
    meta_bits = []
    if current_run.get("klasse"):
        meta_bits.append(f"Klasse: {current_run.get('klasse')}")
    if current_run.get("kategorie"):
        meta_bits.append(f"Kategorie: {current_run.get('kategorie')}")
    if current_run.get("laufart"):
        meta_bits.append(f"Laufart: {current_run.get('laufart')}")
    meta_line = " | ".join(meta_bits) if meta_bits else "—"

    current_starter = view.get("current_starter") or {}
    current_label = format_ring_name(current_starter)
    current_startno = current_starter.get("Startnummer")
    current_startno_display = f"#{current_startno}" if current_startno else ""

    parts = [
        "<div class='ring-monitor'>",
        "<div class='mb-3'>",
        f"<h2 class='h3 mb-1'>{ring_label} – {current_run.get('title','')}</h2>",
        f"<div class='text-muted mb-2'><strong>Richter:</strong> {current_run.get('judge_name','—')}</div>",
        "<div class='card shadow-sm mb-3'>",
        "<div class='card-body py-2'>",
        "<div class='row text-center'>",
        f"<div class='col-6 col-md'><div class='small text-muted'>Parcourslänge</div><div class='fw-semibold'>{current_run.get('parcours_laenge','—')} m</div></div>",
        f"<div class='col-6 col-md'><div class='small text-muted'>Geräte</div><div class='fw-semibold'>{current_run.get('hindernisse','—')}</div></div>",
        f"<div class='col-6 col-md'><div class='small text-muted'>SCT</div><div class='fw-semibold'>{current_run.get('sct','—')} s</div></div>",
        f"<div class='col-6 col-md'><div class='small text-muted'>MCT</div><div class='fw-semibold'>{current_run.get('mct','—')} s</div></div>",
        "</div>",
        f"<div class='mt-2 small text-muted'>{meta_line}</div>",
        "</div></div>",
        "</div>",
        "<div class='row g-3'>",
        "<div class='col-12 col-lg-6'>",
        "<div class='card shadow-sm h-100'>",
        "<div class='card-header bg-light fw-semibold'>Aktuelle Startliste</div>",
        "<ul class='list-group list-group-flush'>",
    ]

    start_entries = view.get("startlist") or []
    if start_entries:
        for entry in start_entries:
            startno = entry.get("Startnummer")
            startno_display = f"#{startno}" if startno else ""
            parts.append(
                "<li class='list-group-item d-flex justify-content-between align-items-center'>"
                f"<span class='fw-semibold'>{format_ring_name(entry)}</span>"
                f"<span class='small text-muted'>{startno_display}</span>"
                "</li>"
            )
    else:
        parts.append("<li class='list-group-item text-muted'>Keine Startliste verfügbar.</li>")

    parts.extend([
        "</ul>",
        "</div>",
        "</div>",
        "<div class='col-12 col-lg-6'>",
        "<div class='card shadow-sm h-100'>",
        "<div class='card-header bg-light fw-semibold'>Aktuelle Rangliste</div>",
        "<div class='table-responsive'>",
        "<table class='table table-sm mb-0'>",
        "<thead><tr><th>Platz</th><th>Name</th><th>Gesamtfehler</th><th>Zeit</th></tr></thead>",
        "<tbody>",
    ])

    ranked_results = view.get("ranking") or []
    if ranked_results:
        for res in ranked_results:
            parts.append(
                "<tr>"
                f"<td>{res.get('platz')}</td>"
                f"<td>{format_ring_name(res)}</td>"
                f"<td>{_format_total_errors(res)}</td>"
                f"<td>{_format_time(res.get('zeit_total'))}</td>"
                "</tr>"
            )
    else:
        parts.append("<tr><td colspan='4' class='text-muted'>Noch keine Rangliste verfügbar.</td></tr>")

    parts.extend([
        "</tbody>",
        "</table>",
        "</div>",
        "</div>",
        "</div>",
        "</div>",
        "<div class='card shadow-sm mt-3'>",
        "<div class='card-header bg-light fw-semibold'>Letzte 3 Ergebnisse</div>",
        "<div class='card-body py-2'>",
    ])

    last_results = view.get("last_results") or []
    if last_results:
        parts.append("<div class='d-flex flex-column gap-2'>")
        for res in last_results:
            platz = res.get("platz") or "—"
            parts.append(
                "<div class='d-flex justify-content-between align-items-center'>"
                f"<span class='fw-semibold'>{platz} – {format_ring_name(res)}</span>"
                f"<span class='text-muted small'>Fehler {_format_total_errors(res)} · Zeit {_format_time(res.get('zeit_total') or res.get('zeit'))} s</span>"
                "</div>"
            )
        parts.append("</div>")
    else:
        parts.append("<div class='text-muted'>Noch keine Ergebnisse.</div>")

    parts.extend([
        "</div>",
        "</div>",
        "<div class='card bg-dark text-white mt-3'>",
        "<div class='card-body text-center'>",
        "<div class='text-uppercase small text-muted'>Aktueller Starter</div>",
        f"<div class='display-6 fw-semibold'>{current_label}</div>",
        f"<div class='text-muted'>{current_startno_display}</div>",
        "</div>",
        "</div>",
        "</div>",
    ])

    return Response(''.join(parts), mimetype='text/html')
