# --- FIXED HEADER: routes_live.py ---
from flask import Blueprint, render_template, request, jsonify, abort, flash, redirect, url_for, session, Response
from flask_babel import gettext as _
from datetime import datetime
from functools import partial
import json
import math
import re

from pathlib import Path

from extensions import socketio
from utils import (_load_data, _save_data, _get_active_event,
                   _calculate_run_results, _load_settings, _get_active_event_id,
                   _calculate_timelines, resolve_judge_name, resolve_judge_id, _to_int,
                   build_ring_view_model, collect_ring_numbers, format_ring_name,
                   format_ring_name_html, format_ring_name_parts,
                   _format_time, _format_total_errors, get_ring_state,
                   sort_entries_for_startlist, recalc_and_store)
from bccs_sm_qualification import (rank_final_bccs, quali_ranking_for_run,
                                   CATEGORIES as _BCCS_CATEGORIES, DIVISIONS as _BCCS_DIVISIONS)
import planner.schedule_planner as schedule_planner
from web_app.live.ring_state import apply_start_impulse, apply_result_saved, apply_manual_reassign, init_ring_entry_state

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


def _persist_current_run(events, event_id, ring_key, run_block_id, run_id=None):
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
        if run_id:
            current_runs = event.get("current_runs_by_ring") or {}
            current_runs[str(ring_key)] = run_id
            event["current_runs_by_ring"] = current_runs
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


def _format_last_result_detail(res):
    """Rechter Teil einer „Letzte Ergebnisse"-Zeile am Ring-Monitor.

    Platzierte Läufe: ``Fehler X · Zeit Y s``. DIS/ABR (Hund war im Parcours,
    hat aber keinen Platz): stattdessen der Disqualifikations-Code, sonst
    stünde dort sinnloses ``Fehler 999.00 · Zeit 999.99 s``."""
    res = res or {}
    disq = res.get("disqualifikation")
    if disq in ("DIS", "ABR") and not res.get("platz"):
        return disq
    return (f"{_('Fehler')} {_format_total_errors(res)} · "
            f"{_('Zeit')} {_format_time(res.get('zeit_total') or res.get('zeit'))} s")


def _build_ring_payload(event, ring_number):
    view = build_ring_view_model(event, ring_number)
    current_run = view.get("current_run") or {}
    payload = {
        "ring_no": ring_number,
        "run_id": current_run.get("id"),
        "run_meta": view.get("run_meta") or current_run,
        "current": view.get("current") or {},
        "ready": view.get("ready") or {},
        "startlist_next": view.get("startlist_next") or view.get("startlist") or [],
        "ranking_top": view.get("ranking_top") or view.get("ranking") or [],
        "last_results": view.get("last_results") or [],
    }
    return payload


# --- END FIXED HEADER ---

@live_bp.route('/debug/live_state')
def debug_live_state():
    from flask import jsonify, abort
    from utils import debug_tools_enabled
    if not debug_tools_enabled():
        abort(404)
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
        flash(_("Kein Event als 'Live' markiert."), "info")
        return redirect(url_for('events_bp.events_list'))
    event = _get_active_event()
    if not event:
        flash(_("Live-Event mit ID %(id)s wurde nicht gefunden.", id=event_id), "warning")
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

@live_bp.route('/live/run_entry/<event_id>/<run_id>')
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

@live_bp.route('/live/save_result/<event_id>/<run_id>', methods=['POST','GET'])
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
            'disqualifikation': q.get('disqualifikation'),
            'start_time_tod': q.get('start_time_tod')
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
        # Scheduling-Grundlage (Zeitplan-Optimierung): echte TIMY-Startzeit
        # (Tageszeit laut C0-Impuls, vom Ring-Server durchgereicht) statt nur
        # der Speicher-Zeit in 'timestamp'. Optional – fehlt z.B. bei manueller
        # Eingabe ohne TIMY, dann einfach None.
        start_time_tod = data.get('start_time_tod') or None

        entry['result'] = {
            'zeit': zeit,
            'fehler': fehler,
            'verweigerungen': verweigerungen,
            'disqualifikation': disq,
            'start_time_tod': start_time_tod
        }
        entry['timestamp'] = datetime.now().isoformat()

        # Bug 3 Fix: current_starter / next_starter beim Speichern weiterrücken.
        # sort_entries_for_startlist sortiert läufige Hündinnen ans Ende (wie
        # Startliste/Monitor), damit der aktive Läufer der gleichen Reihenfolge
        # folgt wie die Ring-PC-Liste.
        entries_sorted = sort_entries_for_startlist(run.get('entries', []))
        unfinished = [
            e for e in entries_sorted
            if not (e.get('result') and (e['result'].get('zeit') or e['result'].get('disqualifikation')))
        ]
        run['current_starter'], run['next_starter'] = _pick_auto_starter(unfinished)

        # ring_entry_state (current_entry_id) ebenfalls weiterruecken - sonst
        # bleibt der Ring-Monitor/Sprecher-Display (die ueber build_ring_view_model
        # aus ring_entry_state lesen, nicht aus run['current_starter']) auf dem
        # ersten Starter des Laufs haengen.
        ring_num_for_state = re.sub(r"[^0-9]", "", str(run.get('assigned_ring') or "")) or "1"
        ring_state_all = event.setdefault("ring_entry_state", {})
        ring_state_all[ring_num_for_state] = apply_result_saved(
            ring_state_all.get(ring_num_for_state) or {}, entries_sorted, license_nr
        )

        _save_data('events.json', events)

        # Realtime Updates
        try:
            ring_num = find_run_ring_number(event, run)
            ring_label = f"Ring {ring_num}"
            announcer_payload = {'event_id': event_id, 'ring_name': ring_label}
            socketio.emit('result_update', {'run_id': run_id, 'license_nr': license_nr, 'result': entry['result']})
            # Bug 1+2 Fix: in Ring-Room UND Event-Room emittieren (statt globalem Broadcast ohne Room)
            socketio.emit('announcer_update', announcer_payload, room=f"event:{event_id}:ring:{ring_num}")
            socketio.emit('announcer_update', announcer_payload, room=f"event:{event_id}")
            socketio.emit('current_run_changed', {
                'event_id': event_id, 'ring_id': ring_num, 'run_block_id': None
            }, room=f"event:{event_id}:ring:{ring_num}")
            socketio.emit('current_run_changed', {
                'event_id': event_id, 'ring_id': ring_num, 'run_block_id': None
            }, room=f"event:{event_id}")
        except Exception:
            pass

        # Portal-Sync: Live-Update + Result-Export im Hintergrund
        try:
            from portal_sync import push_live_update, send_result_export
            from threading import Thread
            settings_for_sync = _load_settings()
            if settings_for_sync.get("portal_url"):
                # 1) Live-Update (Einzel-Ergebnis, asynchron)
                if settings_for_sync.get("portal_live_api_key"):
                    all_results_for_sync = _calculate_run_results(run, settings_for_sync)
                    enriched_entry = next(
                        (r for r in all_results_for_sync if r.get("Lizenznummer") == license_nr),
                        entry
                    )
                    push_live_update(settings_for_sync, event, run, enriched_entry,
                                     ring_label=f"Ring {find_run_ring_number(event, run)}")
                # 2) Result-Export (aktuelle Rangliste, asynchron)
                if settings_for_sync.get("portal_results_api_key"):
                    _event_snap = dict(event)  # shallow copy für Thread-Sicherheit
                    _settings_snap = dict(settings_for_sync)
                    def _bg_export():
                        try:
                            send_result_export(_settings_snap, _event_snap, final=False)
                        except Exception:
                            pass
                    Thread(target=_bg_export, daemon=True).start()
        except Exception:
            pass  # Portal-Sync darf nie den Hauptprozess unterbrechen

        return jsonify({"success": True, "message": "Ergebnis erfolgreich gespeichert.", "result": entry['result']})
    except Exception as ex:
        return jsonify({"success": False, "message": f"Fehler beim Speichern: {ex}"}), 500


@live_bp.route('/live/ranking/<event_id>/<run_id>')
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
    # Pro Ring gleich den Ring-Monitor-Inhalt vorrendern, damit das Sprecherdashboard
    # designtechnisch identisch zum Ringmonitor aussieht (gleicher Builder).
    ring_content = {ring_no: build_ring_monitor_content_html(event, ring_no, max_ranking=4) for ring_no in ring_numbers}
    return render_template('announcer_dashboard.html', event=event, ring_numbers=ring_numbers, ring_content=ring_content, kiosk_mode=True)
@live_bp.route('/live/set_active_announcer_run/<event_id>/<run_id>')
def set_active_announcer_run(event_id, run_id):
    # Setzt den aktiven Lauf für Sprecher/Monitore.
    # Schreibt kanonisch NUR unter "Ring N" in live_state.json und entfernt Alt-Keys.
    run_id = str(run_id)

    event = _get_active_event()
    run = next((r for r in (event.get('runs', []) if event else []) if r.get('id') == run_id), None)
    ring_hint = request.args.get('ring')

    if not event or not run:
        flash(_('Lauf konnte nicht für Sprecher/Monitore aktiviert werden.'), 'warning')
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
    if _persist_current_run(events, evt_id, ring_key, run_block.get('id') if run_block else None, run.get('id')):
        for evt in events:
            if evt.get("id") != evt_id:
                continue
            evt.setdefault("current_runs_by_ring", {})[str(ring_key)] = run.get("id")
            from utils import sort_entries_for_startlist
            evt.setdefault("ring_entry_state", {})[str(ring_key)] = init_ring_entry_state(
                sort_entries_for_startlist(run.get("entries", []))
            )
            break
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

    flash(_("'%(run)s' ist jetzt aktiv für die Anzeige auf %(ring)s.", run=run.get('name'), ring=ring_label), 'success')

    # Portal-Sync: Lauf-Wechsel pushen
    try:
        from portal_sync import push_run_changed
        settings_sync = _load_settings()
        if settings_sync.get("portal_url") and settings_sync.get("portal_live_api_key"):
            push_run_changed(settings_sync, event, run)
    except Exception:
        pass

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
    run_id = data.get("run_id")
    if not run_id:
        current_runs = event.get("current_runs_by_ring") or {}
        run_id = current_runs.get(str(ring_no))
    run = next((r for r in event.get("runs", []) or [] if r.get("id") == run_id), None)
    if run:
        ring_state = event.get("ring_entry_state") or {}
        ring_state[str(ring_no)] = apply_start_impulse(ring_state.get(str(ring_no)) or {}, run.get("entries", []))
        event["ring_entry_state"] = ring_state
        _save_data("events.json", events)
    payload = _build_ring_payload(event, ring_no)
    payload.update({"event_id": event_id})
    try:
        ring_room = f"event:{event_id}:ring:{ring_no}"
        socketio.emit('ring_ready_changed', payload, room=ring_room)
        socketio.emit('ring_ready_changed', payload, room=f"event:{event_id}")
    except Exception:
        pass
    return jsonify({"success": True})


@live_bp.route('/live/api/reassign_current_starter', methods=['POST'])
def reassign_current_starter():
    """Setzt den aktuellen Starter manuell (Button 'Zeit diesem Teilnehmer
    zuweisen' im Ring-PC-Dashboard, z.B. bei Fehlzuordnung am Alge-Board) -
    ohne Timer-Reset. Aktualisiert beide State-Mechanismen (run['current_starter']
    fuers Ring-PC-Dashboard selbst, ring_entry_state fuer Ring-Monitor/Sprecher-
    Display) und benachrichtigt die Monitore per Socket."""
    data = request.get_json(silent=True) or {}
    event_id = data.get("event_id")
    run_id = data.get("run_id")
    license_nr = data.get("license_number")
    if not event_id or not run_id or not license_nr:
        return jsonify({"success": False, "message": "event_id, run_id oder license_number fehlt"}), 400

    events = _load_data('events.json')
    event = next((e for e in events if e.get('id') == event_id), None)
    if not event:
        return jsonify({"success": False, "message": "Event nicht gefunden"}), 404
    run = next((r for r in event.get('runs', []) or [] if r.get('id') == run_id), None)
    if not run:
        return jsonify({"success": False, "message": "Lauf nicht gefunden"}), 404
    entry = next((e for e in run.get('entries', []) if e.get('Lizenznummer') == license_nr), None)
    if not entry:
        return jsonify({"success": False, "message": "Teilnehmer nicht in diesem Lauf gefunden"}), 404

    entries_sorted = sort_entries_for_startlist(run.get('entries', []))
    unfinished = [
        e for e in entries_sorted
        if not (e.get('result') and (e['result'].get('zeit') or e['result'].get('disqualifikation')))
    ]
    run['current_starter'] = entry
    remaining = [e for e in unfinished if e.get('Lizenznummer') != license_nr]
    run['next_starter'] = remaining[0] if remaining else {}

    ring_no = re.sub(r"[^0-9]", "", str(run.get('assigned_ring') or "")) or "1"
    ring_state_all = event.setdefault("ring_entry_state", {})
    ring_state_all[ring_no] = apply_manual_reassign(
        ring_state_all.get(ring_no) or {}, entries_sorted, license_nr
    )

    _save_data('events.json', events)

    try:
        ring_room = f"event:{event_id}:ring:{ring_no}"
        payload = {'event_id': event_id, 'ring_name': f"Ring {ring_no}"}
        socketio.emit('announcer_update', payload, room=ring_room)
        socketio.emit('announcer_update', payload, room=f"event:{event_id}")
        socketio.emit('ring_ready_changed', payload, room=ring_room)
        socketio.emit('ring_ready_changed', payload, room=f"event:{event_id}")
    except Exception:
        pass

    return jsonify({"success": True})


@live_bp.route('/ring_monitor/<int:ring_number>')
def display_ring_monitor(ring_number):
    event = _get_active_event()
    if not event: return "Kein aktives Event."
    view_model = build_ring_view_model(event, ring_number)
    return render_template('ring_monitor.html', event=event, ring_name=f"Ring {ring_number}", view_model=view_model, kiosk_mode=True)

def _resolve_runs_for_ring(event, ring_number):
    """Liefert die Läufe eines Rings in Anzeige-Reihenfolge (gleiche Quelle wie
    das "Lauf auswählen"-Dropdown im Ring-PC-Dashboard) + Debug-Infos.

    Bewusst unabhängig von der (aktuell fehlerhaften) Zeitplan-Zeitberechnung:
    nutzt nur die Block-/Reihenfolge-Zuordnung, keine berechneten Uhrzeiten.
    Wird auch für die "Laufvorgaben gültig bis Lauf X"-Reichweitenauswahl
    verwendet, damit diese unabhängig vom Zeitplan-Fix funktioniert.
    """
    target = _norm_ring_strict(ring_number)
    runs_for_ring = []
    debug = []
    schedule = event.get("schedule") or {}
    schedule_rings = schedule.get("rings") or {}
    if schedule_rings:
        ring_key = str(ring_number)
        runs_for_ring, debug = _schedule_runs_for_ring(event, ring_key)
    else:
        for r in event.get('runs', []):
            assigned = r.get('assigned_ring') or r.get('ring') or r.get('ring_id') or r.get('ringName')
            if assigned and _norm_ring_strict(assigned) == target:
                runs_for_ring.append(r)
    return runs_for_ring, debug


def find_run_ring_number(event, run):
    """Ermittelt die Ring-NUMMER (als str "1"/"2"/...) eines Laufs.

    Primär aus der Zeitplan-Ring-Zuordnung (``event['schedule']['rings']`` →
    Blöcke), denn bei genutztem Zeitplan-Modul trägt der Lauf selbst KEIN
    ``assigned_ring`` → sonst landete bisher alles auf „Ring 1" (u.a. im
    Portal-Live-Upload). Fallback: direktes Feld am Lauf, sonst "1".
    """
    direct = run.get('assigned_ring') or run.get('ring') or run.get('ring_id') or run.get('ringName')
    if direct:
        return re.sub(r"[^0-9]", "", _norm_ring_strict(direct)) or "1"
    schedule = event.get('schedule') or {}
    rings = schedule.get('rings') or {}
    run_id = run.get('id')
    for key in rings.keys():
        runs_for_ring, _dbg = _schedule_runs_for_ring(event, key)
        if any(r.get('id') == run_id for r in runs_for_ring):
            return re.sub(r"[^0-9]", "", _norm_ring_strict(key)) or "1"
    return "1"


def _pick_auto_starter(unfinished):
    """Waehlt current/next aus den noch offenen (unfinished) Eintraegen.

    Ein vom Einweiser als 'ready' (bereit/am Gate) markierter Eintrag hat Vorrang
    vor der reinen Startlisten-Reihenfolge: die Auto-Reihenfolge springt auf den,
    den der Einweiser bereitgestellt hat, statt stur auf die naechste offene
    Startnummer (Wunsch #6). 'next' = naechster offener in Startlisten-Reihenfolge.
    """
    if not unfinished:
        return {}, {}
    ready = [e for e in unfinished if str(e.get('einweiser_mark') or '').lower() == 'ready']
    current = ready[0] if ready else unfinished[0]
    rest = [e for e in unfinished if e is not current]
    return current, (rest[0] if rest else {})


# ---------------------------------------------------------------------------
# Ring-PC-Auto-Registrierung
#
# Jeder Ring-Server meldet sich im Heartbeat beim Hauptserver
# (GET /api/ring_register?ring=N&port=P). Der Hauptserver merkt sich die
# Quell-IP (request.remote_addr) pro Ring, damit das Ring-PC-Dashboard den
# Ring-Server direkt unter seiner echten IP erreicht – ohne netsh-portproxy.
# Faellt die Registrierung aus, nutzt das Dashboard den bisherigen Fallback
# (127.0.0.1 / window.location.hostname), ist also nie schlechter als vorher.
# ---------------------------------------------------------------------------
_RING_REGISTRY = {}  # {"1": {"ip": "...", "port": 5001, "last_seen": "..."}}


def _register_ring(ring_number, ip, port):
    key = str(ring_number)
    entry = {"ip": ip, "port": port, "last_seen": datetime.utcnow().isoformat()}
    prev = _RING_REGISTRY.get(key)
    _RING_REGISTRY[key] = entry
    # Nur bei IP-/Port-Wechsel persistieren (kein Disk-Thrash im 3s-Heartbeat).
    if not prev or prev.get("ip") != ip or prev.get("port") != port:
        try:
            reg = _load_data('ring_registry.json')
            if not isinstance(reg, dict):
                reg = {}
            reg[key] = entry
            _save_data('ring_registry.json', reg)
        except Exception:
            pass


def _get_registered_ring_host(ring_number):
    key = str(ring_number)
    entry = _RING_REGISTRY.get(key)
    if not entry:
        try:
            reg = _load_data('ring_registry.json')
            if isinstance(reg, dict) and isinstance(reg.get(key), dict):
                entry = reg[key]
                _RING_REGISTRY[key] = entry
        except Exception:
            entry = None
    if isinstance(entry, dict) and entry.get("ip"):
        return entry.get("ip")
    return None


@live_bp.route('/api/ring_register', methods=['GET', 'POST'])
def api_ring_register():
    try:
        ring_number = int(request.values.get('ring'))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "ring required"}), 400
    try:
        port = int(request.values.get('port'))
    except (TypeError, ValueError):
        port = 5000 + ring_number
    ip = request.remote_addr or ''
    if ip == '::1':  # IPv6-localhost auf IPv4 normalisieren
        ip = '127.0.0.1'
    _register_ring(ring_number, ip, port)
    return jsonify({"ok": True, "ring": ring_number, "ip": ip, "port": port}), 200


@live_bp.route('/ring_pc_dashboard/<int:ring_number>')
def ring_pc_dashboard(ring_number):
    event = _get_active_event()
    if not event: return "Kein aktives Event."
    ring_name = f"Ring {ring_number}"
    schedule = event.get("schedule") or {}
    runs_for_ring, debug = _resolve_runs_for_ring(event, ring_number)
    if schedule.get("rings"):
        ring_key = str(ring_number)
        judges = _load_data('judges.json')
        for run in runs_for_ring:
            run_block, _ = _find_run_block_for_run(event, run, ring_key)
            run["judge_display"] = resolve_judge_name(event, run, judges, run_block)
        if not runs_for_ring and debug:
            flash(
                _("Zeitplan gefunden, aber keine Lauf-Blöcke für %(ring)s: %(debug)s", ring=ring_name, debug=', '.join(debug)),
                "warning",
            )
    selected_run_id = request.args.get("run_id")
    if not selected_run_id:
        current_runs = event.get("current_runs_by_ring") or event.get("current_run_per_ring") or {}
        selected_run_id = current_runs.get(str(ring_number))
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

    # Portal-Sync: aktuellen Lauf ans Portal melden (VAR + Live-Seite aktuell halten)
    if selected_run_id:
        try:
            from portal_sync import push_run_changed as _prc
            _settings_rc = _load_settings()
            if _settings_rc.get("portal_url") and _settings_rc.get("portal_live_api_key"):
                _run_rc = next((r for r in event.get("runs", []) if r.get("id") == selected_run_id), None)
                if _run_rc:
                    _prc(_settings_rc, event, _run_rc)
        except Exception:
            pass

    return render_template(
        'ring_pc_dashboard.html',
        event=event,
        ring_name=ring_name,
        runs=runs_for_ring,
        selected_run_id=selected_run_id,
        judges=_load_data('judges.json'),
        ring_host=_get_registered_ring_host(ring_number) or '',
    )

@live_bp.route('/ring_pc_ko/<int:ring_number>')
def ring_pc_ko(ring_number):
    # Der Ring-Server kennt die Event-ID nicht; hier das aktive Event auflösen
    # und auf die KO-Cup-Bedienseite dieses Rings weiterleiten.
    event = _get_active_event()
    if not event:
        return "Kein aktives Event.", 404
    return redirect(url_for('ko_cup_bp.ko_ring', event_id=event.get('id'),
                            ring=ring_number))

@live_bp.route('/api/render_announcer_schedule/<event_id>')
def render_announcer_schedule(event_id):
    event = next((e for e in _load_data('events.json') if e.get('id') == event_id), None)
    if not event:
        abort(404)
    timelines_by_ring = _calculate_timelines(event)
    return render_template('_announcer_schedule.html', timelines_by_ring=timelines_by_ring)

@live_bp.route('/api/render_speaker_panel_content/<event_id>/<ring_name>')
def render_speaker_panel_content(event_id, ring_name):
    """Inhalt einer Ring-Karte im Sprecherdashboard. Nutzt denselben Builder wie der
    Ring-Monitor (`build_ring_monitor_content_html`), damit Sprecherdisplay und
    Ringmonitor designtechnisch identisch aussehen."""
    events = _load_data('events.json')
    event = next((e for e in events if isinstance(e, dict) and e.get('id') == event_id), None)
    digits = re.sub(r"[^0-9]", "", str(ring_name))
    ring_number = int(digits) if digits else 1
    if not event:
        ring_label = _ring_label_for_display(ring_number=ring_number)
        return Response(f"<div class='ring-monitor'><h2>{ring_label}</h2><p>Event nicht gefunden.</p></div>", mimetype='text/html')
    return Response(build_ring_monitor_content_html(event, ring_number, max_ranking=4), mimetype='text/html')
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


def _bccs_division_for_run(current_run):
    """(category, div_key, div_label) für den Finallauf, oder None wenn Kat/Klasse
    nicht zu einer BCCS-Division passt."""
    category = current_run.get("kategorie")
    if category not in _BCCS_CATEGORIES:
        return None
    klasse = str(current_run.get("klasse") or "")
    for div_key, div_def in _BCCS_DIVISIONS.items():
        if klasse in div_def["classes"]:
            return category, div_key, div_def["label"]
    return None


def _format_sum_errors(val):
    """Summe Gesamtfehler fürs Monitor-Display: ganze Zahl ohne Nachkomma, sonst gekürzt."""
    if val is None:
        return "—"
    return f"{val:g}"


def _name_html_from_row(d, show_startnummer=False, muted_cls="text-muted"):
    """Einzeiliger Name aus einer Kombi-Ranglisten-Zeile (handler_name/dog_name),
    optional mit Startnummer-Badge (z.B. fuer die "Fuehrend"-Zeile der Platz-1-
    Projektion, wo die Startnummer am Ring direkt zuordenbar sein soll). `muted_cls`
    auf 'text-white-50' setzen, wenn auf dunklem Hintergrund eingebettet."""
    handler = d.get("handler_name") or ""
    dog = d.get("dog_name") or ""
    name_html = ""
    if show_startnummer and d.get("startnummer") is not None:
        name_html += f"<span class='small {muted_cls} fw-normal'>#{d.get('startnummer')}</span> "
    name_html += f"<strong>{handler}</strong>" if handler else ""
    if dog:
        name_html += f" <span class='small {muted_cls} fw-normal'>{dog}</span>"
    return name_html


_BCCS_MONITOR_TOP_N = 4


def _render_bccs_combined_table(rows, cat_label, div_label):
    """A2: kombinierte Final-Rangliste (Summe beider Finalläufe) als Karte.

    Zeigt nur die ersten `_BCCS_MONITOR_TOP_N` KLASSIERTEN Plätze (Monitor-Platzgrund:
    gleiche Grössenordnung wie die anderen Listen/Karten des Ring-Monitors) — nicht
    klassierte (DIS/noch nicht gelaufen) Teams werden hier ausgeblendet, nicht nur
    ans Ende sortiert."""
    top_rows = [d for d in rows if not d.get("dis")][:_BCCS_MONITOR_TOP_N]
    if not top_rows:
        # Noch kein einziges Team in beiden Finalläufen klassiert (typisch waehrend
        # des 1. Finallaufs/Jumping, solange niemand den 2. Lauf/Agility beendet hat)
        # — dann lieber gar keine (leere) Tabelle zeigen statt eines nutzlosen Rahmens.
        return ""
    title = f"{_('Kombinierte Rangliste')} – {cat_label} {div_label}"
    parts = [
        "<div class='card shadow-sm mt-3'>",
        f"<div class='card-header bg-light fw-semibold'>🏆 {title}</div>",
        "<div class='table-responsive'>",
        "<table class='table table-sm mb-0'>",
        f"<thead><tr><th>{_('Platz')}</th><th>{_('Name')}</th>"
        f"<th>{_('Gesamtfehler')}</th><th>{_('Zeit')}</th></tr></thead>",
        "<tbody>",
    ]
    for d in top_rows:
        platz = d.get("final_rang")
        parts.append(
            "<tr>"
            f"<td>{platz}</td>"
            f"<td>{_name_html_from_row(d)}</td>"
            f"<td>{_format_sum_errors(d.get('sum_fehler'))}</td>"
            f"<td>{_format_time(d.get('sum_zeit'))}</td>"
            "</tr>"
        )
    parts.extend(["</tbody>", "</table>", "</div>", "</div>"])
    return ''.join(parts)


def _render_bccs_platz1_projection(rows, view, embedded=False):
    """A3: „Was darf sich der Läufer erlauben, um Platz 1 zu erreichen" — Live-Projektion
    für den aktuellen Starter im 2. Finallauf (Agility).

    Semantik (User-Entscheid 2026-11-02, final): „Platz 1 erreichen" heisst **alleiniger**
    Platz 1 (überholen), nicht Teilen mit dem Führenden. Die Strenge greift dabei nur auf
    der Zeit-Ebene — bei Fehler-Gleichstand übernimmt der Starter die Führung trotzdem, wenn
    er schneller ist (Reglement 3.2: Gesamtfehler → Parcoursfehler → Zeit; bei Fehlergleichstand
    entscheidet die Zeit). Budget gegenüber dem besten bereits in BEIDEN Läufen klassierten Team:
      - Fehlerpunkte-Budget im Agility = Führender.Summe_Fehler − Jumping-Fehler des Starters
        (höchstens so viele Punkte → Gesamtfehler ≤ Führender, Gleichstand zulässig).
      - Zeit-Budget im Agility (für den Fehler-Gleichstand-Fall) = Führender.Summe_Zeit −
        Jumping-Zeit des Starters (Zeit muss ECHT UNTER diesem Wert liegen, nicht nur gleich).
    ⚠️ Vereinfachung: ignoriert die Parcoursfehler-Zwischenstufe (Reglement-Tiebreak #2) —
    bei exaktem Gesamtfehler-Gleichstand entscheidet offiziell zuerst die Parcoursfehler-Summe,
    erst dann die Zeit. Für die Live-Anzeige bewusst auf Fehler→Zeit vereinfacht.
    Liefert leeren String, wenn nicht anwendbar (kein Agility-Final, kein aktueller Starter,
    Starter im Jumping disqualifiziert → keine Kombination mehr möglich).

    `embedded=True`: liefert nur den Inhalt OHNE eigene Card-Huelle, OHNE Titel/Trennlinie
    und OHNE „Führend"-Zeile (zum nahtlosen Einbetten in die dunkle „Aktueller Starter"-
    Karte direkt unter Name/Hund — die Führend-Info steht ohnehin in der Kombi-Rangliste-
    Karte darunter, Platz 1). Text läuft in hellen Farben (text-white-50) statt text-muted
    auf dem dunklen Hintergrund."""
    current_run = view.get("current_run") or {}
    # Nur im 2. Finallauf (Agility) sinnvoll — im 1. Finallauf (Jumping) gibt es noch keine Kombi.
    if current_run.get("laufart") != "Agility":
        return ""
    starter = view.get("current_starter") or {}
    lic = (starter.get("Lizenznummer") or "").strip()
    if not lic:
        return ""

    starter_row = next((d for d in rows if str(d.get("license") or "").strip() == lic), None)
    jump = (starter_row or {}).get("runs", {}).get("Jumping") if starter_row else None

    muted_cls = "text-white-50" if embedded else "text-muted"
    if embedded:
        def _box(body_html):
            # Steht jetzt als eigene Spalte neben Name/Hund (statt darunter gestapelt)
            # -> keine Extra-Margin noetig, row align-items-center uebernimmt das.
            return body_html
    else:
        header = f"<div class='card-header bg-dark text-white fw-semibold'>🎯 {_('Für Platz 1')}</div>"

        def _box(body_html):
            return ("<div class='card shadow-sm mt-3 border-dark'>"
                    f"{header}<div class='card-body py-2'>{body_html}</div></div>")

    if jump is None:
        # Starter hat (noch) kein Jumping-Final-Ergebnis in der Wertung.
        return ""
    if jump.get("dis"):
        return _box(f"<div class='{muted_cls}'>{_('Keine Kombination möglich (Jumping disqualifiziert).')}</div>")

    # Bester bereits klassierter Gegner (beide Läufe sauber), nicht der Starter selbst.
    classified = [d for d in rows
                  if not d.get("dis") and str(d.get("license") or "").strip() != lic]
    if not classified:
        return _box(f"<div>{_('Noch keine Kombi-Führung – ein fehlerfreier Lauf führt.')}</div>")
    leader = classified[0]  # rows sind bereits nach Summe Fehler→Parcours→Zeit sortiert

    j_f = jump.get("fehler_total") or 0
    j_t = jump.get("zeit") or 0
    fehler_budget = round((leader.get("sum_fehler") or 0) - j_f, 3)
    zeit_budget = round((leader.get("sum_zeit") or 0) - j_t, 3)

    # "Führend"-Zeile nur in der eigenstaendigen (nicht eingebetteten) Variante — im
    # eingebetteten Monitor-Layout steht der Führende ohnehin auf Platz 1 der Kombi-
    # Rangliste-Karte direkt darunter.
    leader_line = ""
    if not embedded:
        leader_name = _name_html_from_row(leader, show_startnummer=True, muted_cls=muted_cls)
        leader_line = (f"<div class='small {muted_cls}'>{_('Führend')}: {leader_name} "
                        f"({_format_sum_errors(leader.get('sum_fehler'))} {_('Fehler')}, "
                        f"{_format_time(leader.get('sum_zeit'))} s)</div>")

    if fehler_budget < 0:
        body = f"<div class='{muted_cls}'>{_('Platz 1 nicht mehr erreichbar.')}</div>" + leader_line
        return _box(body)

    body = (
        f"<div class='fs-5'>{_('Höchstens')} <strong>{_format_sum_errors(fehler_budget)}</strong> "
        f"{_('Fehlerpunkte im Agility')}</div>"
        f"<div>{_('Bei Null Fehlern: Agility-Zeit unter')} <strong>{_format_time(zeit_budget)} s</strong></div>"
        + leader_line
    )
    return _box(body)


def _bccs_monitor_rows(event, view):
    """Gemeinsame Datenbeschaffung fuer A2 (Kombi-Rangliste) + A3 (Platz-1-Projektion):
    liefert (rows, cat_label, div_label) oder None, wenn ausserhalb BCCS-SM/Final oder
    ohne Finalisten. Read-only: `rank_final_bccs` arbeitet auf Kopien (kein Save)."""
    current_run = view.get("current_run") or {}
    if (event.get("Veranstaltungsart") != "BCCS-SM") or not current_run.get("is_final"):
        return None
    div = _bccs_division_for_run(current_run)
    if not div:
        return None
    category, div_key, div_label = div
    try:
        settings = _load_settings()
        ranking = rank_final_bccs(event, recalc_fn=partial(recalc_and_store, settings=settings))
    except Exception:
        return None
    rows = ranking.get(f"{category}/{div_key}") or []
    if not rows:
        return None
    cat_label = _('Intermediate') if category == 'Intermediate' else _('Large')
    return rows, cat_label, div_label


def _render_bccs_previous_run_line(event, view):
    """Zeigt Platz + Resultat des aktuellen Starters aus dem VORANGEHENDEN Finallauf
    (Jumping, vor dem 2. Finallauf Agility) — Einordnung für Sprecher/Publikum, bevor
    der Agility-Lauf dieses Teams beginnt. Leerer String, wenn nicht anwendbar (kein
    Agility-Final, kein aktueller Starter, noch kein Jumping-Ergebnis vorhanden)."""
    current_run = view.get("current_run") or {}
    if current_run.get("laufart") != "Agility":
        return ""
    data = _bccs_monitor_rows(event, view)
    if not data:
        return ""
    rows, _cat_label, _div_label = data
    starter = view.get("current_starter") or {}
    lic = (starter.get("Lizenznummer") or "").strip()
    if not lic:
        return ""
    starter_row = next((d for d in rows if str(d.get("license") or "").strip() == lic), None)
    jump = (starter_row or {}).get("runs", {}).get("Jumping") if starter_row else None
    if jump is None:
        return ""

    if jump.get("dis"):
        result_text = _("nicht klassiert")
    else:
        platz = jump.get("rang")
        platz_text = f"{_('Platz')} {platz} · " if platz else ""
        result_text = (f"{platz_text}{_format_total_errors(jump)} {_('Fehler')} · "
                        f"{_format_time(jump.get('zeit'))} s")
    return f"<div class='small text-white-50'>{_('Jumping')}: {result_text}</div>"


def _render_bccs_platz1_inner(event, view):
    """A3-Inhalt OHNE eigene Card-Huelle, zum Einbetten in die „Aktueller Starter"-Karte."""
    data = _bccs_monitor_rows(event, view)
    if not data:
        return ""
    rows, _cat_label, _div_label = data
    return _render_bccs_platz1_projection(rows, view, embedded=True)


def _render_bccs_combined_section(event, view):
    """A2-Kombi-Ranglisten-Karte (eigenstaendig, Top-4 Plätze)."""
    data = _bccs_monitor_rows(event, view)
    if not data:
        return ""
    rows, cat_label, div_label = data
    return _render_bccs_combined_table(rows, cat_label, div_label)


def _bccs_quali_rows(event, view):
    """Datenbeschaffung für die Quali-Rangliste im Ring-Monitor (Analogon zu
    `_bccs_monitor_rows` für den Final): liefert `data` (s. `quali_ranking_for_run`)
    oder None, wenn ausserhalb BCCS-SM, im Final oder ohne SM-Starter im Lauf.
    Read-only: `quali_ranking_for_run` arbeitet auf Kopien (kein Save)."""
    current_run = view.get("current_run") or {}
    if event.get("Veranstaltungsart") != "BCCS-SM" or current_run.get("is_final"):
        return None
    try:
        settings = _load_settings()
        data = quali_ranking_for_run(event, current_run,
                                      recalc_fn=partial(recalc_and_store, settings=settings))
    except Exception:
        return None
    if not data or not data["ranking"]:
        return None
    return data


def _render_bccs_quali_ranking_table(data):
    """Volle BCCS-SM-Quali-Rangliste EINES Laufs (Top-`_BCCS_MONITOR_TOP_N` + Quote-
    Zeile) als Karte — Analogon zu `_render_bccs_combined_table` für den Final.
    Qualifizierte Teams (direkt oder Nachrücker) grün hervorgehoben."""
    rows = [r for r in data["ranking"] if not r.get("dis")][:_BCCS_MONITOR_TOP_N]
    if not rows:
        return ""
    title = (f"{_('Quali-Rangliste')} – {data['category']} {data['division_label']} "
             f"Kl.{data['klasse']} {_(data['laufart'])}")
    parts = [
        "<div class='card shadow-sm mt-3'>",
        f"<div class='card-header bg-light fw-semibold'>📋 {title}</div>",
        "<div class='table-responsive'>",
        "<table class='table table-sm mb-0'>",
        f"<thead><tr><th>{_('Platz')}</th><th>{_('Name')}</th>"
        f"<th>{_('Fehler')}</th><th>{_('Zeit')}</th></tr></thead>",
        "<tbody>",
    ]
    for d in rows:
        row_cls = " class='table-success'" if d.get("qualified_source") else ""
        parts.append(
            f"<tr{row_cls}>"
            f"<td>{d.get('rang')}</td>"
            f"<td>{_name_html_from_row(d)}</td>"
            f"<td>{_format_sum_errors(d.get('fehler_total'))}</td>"
            f"<td>{_format_time(d.get('zeit'))}</td>"
            "</tr>"
        )
    parts.extend([
        "</tbody>", "</table>",
        f"<div class='px-2 py-1 small text-muted'>{_('Quote')}: {data['quota']}</div>",
        "</div>", "</div>",
    ])
    return ''.join(parts)


def _render_bccs_quali_ranking_section(event, view):
    """BCCS-SM: volle Quali-Rangliste des aktuellen Laufs als eigene Monitor-Karte
    unter „Aktueller Starter" — Analogon zur Final-Kombirangliste
    (`_render_bccs_combined_section`), aber während der Qualifikation (Kl. 1–3,
    Agility/Jumping, kein Final)."""
    data = _bccs_quali_rows(event, view)
    if not data:
        return ""
    return _render_bccs_quali_ranking_table(data)


def _render_bccs_monitor_extras(event, view):
    """Zuschauer-Monitor-Zusätze bei BCCS-SM-Finalläufen: A3-Platz-1-Projektion (nur
    Agility-Final, eigene Card) + A2-Kombi-Rangliste. Leerer String ausserhalb BCCS-SM/
    Final. Nur noch für Tests/Altcode mit eigener A3-Card — die Live-Route bettet A3
    stattdessen in die „Aktueller Starter"-Karte ein (siehe `_render_bccs_platz1_inner`)."""
    data = _bccs_monitor_rows(event, view)
    if not data:
        return ""
    rows, cat_label, div_label = data
    return (_render_bccs_platz1_projection(rows, view)
            + _render_bccs_combined_table(rows, cat_label, div_label))


def build_ring_monitor_content_html(event, ring_number: int, max_ranking: int = 10):
    """Baut das Ring-Monitor-Inhalts-HTML (ohne Response-Wrapper), damit es sowohl
    der Ring-Monitor (`/api/render_ring_monitor_content`) als AUCH das
    Sprecherdashboard (`/api/render_speaker_panel_content`) identisch nutzen –
    so sehen Sprecherdisplay und Ringmonitor designtechnisch gleich aus.
    `max_ranking` begrenzt die „Aktuelle Rangliste" (Sprecherdashboard: Top 4)."""
    ring_label = _ring_label_for_display(ring_number=ring_number)
    if not event:
        return f"<div class='ring-monitor'><p>{_('Kein aktives Event.')}</p></div>"
    view = build_ring_view_model(event, ring_number, max_ranking=max_ranking)
    current_run = view.get("current_run")
    if not current_run:
        html = (
            f"<div class='ring-monitor'><h2>{ring_label}</h2>"
            f"<p>{_('Kein Lauf wurde für diesen Ring aktiviert.')}</p>"
            f"<a href='/print/schedule/{event.get('id')}' target='_blank' "
            f"class='btn btn-outline-primary'>📅 {_('Zeitplan anzeigen')}</a></div>"
        )
        return html
    meta_bits = []
    if current_run.get("klasse"):
        meta_bits.append(f"{_('Klasse')}: {current_run.get('klasse')}")
    if current_run.get("kategorie"):
        meta_bits.append(f"{_('Kategorie')}: {current_run.get('kategorie')}")
    if current_run.get("laufart"):
        meta_bits.append(f"{_('Laufart')}: {current_run.get('laufart')}")
    meta_line = " | ".join(meta_bits) if meta_bits else "—"

    current_starter = view.get("current_starter") or {}
    current_handler, current_dog = format_ring_name_parts(current_starter)

    parts = [
        "<div class='ring-monitor'>",
        "<div class='mb-2'>",
        f"<h2 class='h3 mb-1'>{ring_label} – {current_run.get('title','')}</h2>",
        f"<div class='text-muted mb-2'><strong>{_('Richter')}:</strong> {current_run.get('judge_name','—')}</div>",
        "</div>",
        # Laufvorgaben – gleiche Hoehe wie Letzte Ergebnisse + Aktueller Starter (.ring-band)
        "<div class='card shadow-sm mb-3 ring-band'>",
        "<div class='card-body py-2 d-flex flex-column justify-content-center'>",
        "<div class='row text-center g-2'>",
        f"<div class='col-6 col-md'><div class='small text-muted'>{_('Parcourslänge')}</div><div class='fw-semibold'>{current_run.get('parcours_laenge','—')} m</div></div>",
        f"<div class='col-6 col-md'><div class='small text-muted'>{_('Geräte')}</div><div class='fw-semibold'>{current_run.get('hindernisse','—')}</div></div>",
        f"<div class='col-6 col-md'><div class='small text-muted'>SCT</div><div class='fw-semibold'>{current_run.get('sct','—')} s</div></div>",
        f"<div class='col-6 col-md'><div class='small text-muted'>MCT</div><div class='fw-semibold'>{current_run.get('mct','—')} s</div></div>",
        "</div>",
        f"<div class='mt-2 small text-muted text-center'>{meta_line}</div>",
        "</div>",
        "</div>",
        "<div class='row g-3'>",
        "<div class='col-12 col-lg-6'>",
        "<div class='card shadow-sm h-100'>",
        f"<div class='card-header bg-light fw-semibold'>{_('Aktuelle Startliste')}</div>",
        "<ul class='list-group list-group-flush ring-startlist'>",
    ]

    start_entries = view.get("startlist") or []
    if start_entries:
        for entry in start_entries:
            startno = entry.get("Startnummer")
            startno_display = f"#{startno}" if startno is not None else ""
            parts.append(
                "<li class='list-group-item d-flex justify-content-between align-items-center'>"
                f"<span>{format_ring_name_html(entry)}</span>"
                f"<span class='small text-muted'>{startno_display}</span>"
                "</li>"
            )
    else:
        parts.append(f"<li class='list-group-item text-muted'>{_('Keine Startliste verfügbar.')}</li>")

    parts.extend([
        "</ul>",
        "</div>",
        "</div>",
        "<div class='col-12 col-lg-6'>",
        "<div class='card shadow-sm h-100'>",
        f"<div class='card-header bg-light fw-semibold'>{_('Aktuelle Rangliste')}</div>",
        "<div class='table-responsive'>",
        "<table class='table table-sm mb-0'>",
        f"<thead><tr><th>{_('Platz')}</th><th>{_('Name')}</th><th>{_('Gesamtfehler')}</th><th>{_('Zeit')}</th></tr></thead>",
        "<tbody>",
    ])

    ranked_results = view.get("ranking") or []
    if ranked_results:
        for res in ranked_results:
            parts.append(
                "<tr>"
                f"<td>{res.get('platz')}</td>"
                f"<td>{format_ring_name_html(res)}</td>"
                f"<td>{_format_total_errors(res)}</td>"
                f"<td>{_format_time(res.get('zeit_total'))}</td>"
                "</tr>"
            )
    else:
        parts.append(f"<tr><td colspan='4' class='text-muted'>{_('Noch keine Rangliste verfügbar.')}</td></tr>")

    parts.extend([
        "</tbody>",
        "</table>",
        "</div>",
        "</div>",
        "</div>",
        "</div>",
        # Letzte Ergebnisse (ohne Titel) – gleiche Hoehe wie Laufvorgaben +
        # Aktueller Starter (.ring-band).
        "<div class='card shadow-sm mt-3 ring-band'>",
        "<div class='card-body py-2 d-flex flex-column justify-content-center'>",
        f"<div class='fw-semibold mb-2'>{_('Letzte 3 Ergebnisse')}</div>",
    ])

    last_results = view.get("last_results") or []
    if last_results:
        parts.append("<div class='d-flex flex-column gap-2'>")
        for res in last_results:
            platz = res.get("platz") or "—"
            handler, dog = format_ring_name_parts(res)
            name_html = f"<strong>{platz} – {handler}</strong>" if handler else f"<strong>{platz}</strong>"
            name_html += f" <span class='small text-muted fw-normal'>{dog}</span>" if dog else ""
            parts.append(
                "<div class='d-flex justify-content-between align-items-start'>"
                f"<span>{name_html}</span>"
                f"<span class='text-muted small'>{_format_last_result_detail(res)}</span>"
                "</div>"
            )
        parts.append("</div>")
    else:
        parts.append(f"<div class='text-muted'>{_('Noch keine Ergebnisse.')}</div>")

    # BCCS-SM: Platz/Resultat aus dem vorangehenden Finallauf (Jumping) + Platz-1-
    # Projektion (Agility-Final) werden in die Aktueller-Starter-Karte eingebettet
    # statt eigene Karten zu belegen (spart Monitor-Platz). Wenn vorhanden, links/
    # rechts neben Name+Hund gesetzt (3-Spalten) statt darunter gestapelt — haelt die
    # Karte flach, egal wie viel BCCS-Zusatzinfo dazukommt.
    bccs_previous_run_html = _render_bccs_previous_run_line(event, view)
    bccs_platz1_html = _render_bccs_platz1_inner(event, view)

    core_info = f"<div class='h3 fw-semibold mb-0'>{current_handler or '—'}</div>"
    if current_dog:
        core_info += f"<div class='text-white-50'>{current_dog}</div>"

    if bccs_previous_run_html or bccs_platz1_html:
        starter_body = (
            "<div class='row align-items-center text-center g-2'>"
            f"<div class='col-4'>{bccs_previous_run_html}</div>"
            f"<div class='col-4'>{core_info}</div>"
            f"<div class='col-4'>{bccs_platz1_html}</div>"
            "</div>"
        )
    else:
        starter_body = core_info

    parts.extend([
        "</div>",   # card-body
        "</div>",   # card
        # Aktueller Starter – gleiche Hoehe via .ring-band (min-height)
        "<div class='card bg-dark text-white mt-3 ring-band'>",
        "<div class='card-body text-center py-2 d-flex flex-column justify-content-center'>",
        f"<div class='text-uppercase small text-white-50'>{_('Aktueller Starter')}</div>",
        starter_body,
        "</div>",   # card-body
        "</div>",   # card
    ])

    # BCCS-SM: kombinierte Final-Rangliste (A2, Top 4) als eigene Karte
    parts.append(_render_bccs_combined_section(event, view))
    # BCCS-SM: volle Quali-Rangliste während der Qualifikation (Top 4 + Quote)
    parts.append(_render_bccs_quali_ranking_section(event, view))

    parts.append("</div>")   # .ring-monitor

    return ''.join(parts)


@live_bp.route('/api/render_ring_monitor_content/<int:ring_number>')
def render_ring_monitor_content(ring_number: int):
    event = _get_active_event()
    return Response(build_ring_monitor_content_html(event, ring_number), mimetype='text/html')


def _apply_laufdaten_to_run(run, data, settings):
    """Übernimmt Richter/Parcours/SCT-Formulardaten in einen einzelnen Lauf."""
    laufdaten = run.get('laufdaten', {})

    raw_laenge = data.get('parcours_laenge')
    if raw_laenge not in (None, ''):
        laufdaten['parcours_laenge'] = raw_laenge

    raw_hind = data.get('anzahl_hindernisse')
    if raw_hind not in (None, ''):
        laufdaten['anzahl_hindernisse'] = raw_hind

    if run.get('klasse') in ['1', 'Oldie']:
        laufdaten['sct_direkt'] = bool(data.get('sct_direkt', False))
        if laufdaten['sct_direkt']:
            laufdaten['standardzeit_sct'] = data.get('standardzeit_sct', '')
            laufdaten['geschwindigkeit'] = ''
        else:
            laufdaten['geschwindigkeit'] = data.get('geschwindigkeit', '')
            laufdaten['standardzeit_sct'] = ''

    judge_id = data.get('judge_id') or ''
    run['judge_id'] = judge_id
    run['richter_id'] = judge_id
    run['laufdaten'] = laufdaten

    # SCT/MCT neu berechnen
    _calculate_run_results(run, settings)


@live_bp.route('/live/api/update_run_laufdaten/<event_id>/<run_id>', methods=['POST'])
def api_update_run_laufdaten(event_id, run_id):
    """Aktualisiert Laufdaten (Parcours, Richter, SCT) direkt vom Ring-PC-Dashboard.

    Optionales `until_run_id`: wendet dieselben Laufdaten auf alle Läufe dieses
    Rings zwischen run_id und until_run_id an (inklusive, in Dashboard-
    Reihenfolge) — z.B. wenn eine Hindernis-Konfiguration für mehrere Klassen
    bis zum nächsten Umbau/Briefing unverändert bleibt. Die Reichweite nutzt
    bewusst dieselbe Lauf-Reihenfolge wie das "Lauf auswählen"-Dropdown, nicht
    die (aktuell fehlerhafte) Zeitplan-Zeitberechnung.
    """
    run_id = str(run_id)
    data = request.get_json(force=True, silent=True) or {}
    events = _load_data('events.json')
    event = next((e for e in events if e.get('id') == event_id), None)
    run = next((r for r in (event.get('runs', []) if event else []) if r.get('id') == run_id), None)
    if not event or not run:
        return jsonify({'success': False, 'message': 'Event oder Lauf nicht gefunden.'}), 404

    target_runs = [run]
    until_run_id = data.get('until_run_id') or None
    if until_run_id and str(until_run_id) != run_id:
        ring_number = re.sub(r"[^0-9]", "", str(run.get('assigned_ring') or "")) or "1"
        runs_for_ring, _debug = _resolve_runs_for_ring(event, ring_number)
        ids_in_order = [r.get('id') for r in runs_for_ring]
        try:
            start_idx = ids_in_order.index(run_id)
            end_idx = ids_in_order.index(str(until_run_id))
        except ValueError:
            start_idx = end_idx = None
        if start_idx is not None and end_idx is not None and end_idx >= start_idx:
            target_runs = runs_for_ring[start_idx:end_idx + 1]

    settings = _load_settings()
    for target_run in target_runs:
        _apply_laufdaten_to_run(target_run, data, settings)

    _save_data('events.json', events)

    # Monitore aktualisieren
    try:
        ring_num = re.sub(r"[^0-9]", "", str(run.get('assigned_ring') or "")) or "1"
        ring_label = f"Ring {ring_num}"
        payload = {'event_id': event_id, 'ring_name': ring_label}
        socketio.emit('announcer_update', payload, room=f"event:{event_id}:ring:{ring_num}")
        socketio.emit('announcer_update', payload, room=f"event:{event_id}")
    except Exception:
        pass

    updated_laufdaten = run.get('laufdaten', {})
    return jsonify({
        'success': True,
        'applied_to_runs': len(target_runs),
        'sct': updated_laufdaten.get('standardzeit_sct_gerundet') or updated_laufdaten.get('standardzeit_sct_berechnet'),
        'mct': updated_laufdaten.get('maximalzeit_mct_gerundet') or updated_laufdaten.get('maximalzeit_mct_berechnet'),
    })


@live_bp.route('/live/api/set_participant_status/<event_id>/<run_id>', methods=['POST'])
def api_set_participant_status(event_id, run_id):
    """Setzt den Status eines Teilnehmers (DNS = nicht gestartet, DIS = disqualifiziert)."""
    run_id = str(run_id)
    data = request.get_json(force=True, silent=True) or {}
    license_nr = data.get('license_number')
    status = data.get('status', '')

    events = _load_data('events.json')
    event = next((e for e in events if e.get('id') == event_id), None)
    run = next((r for r in (event.get('runs', []) if event else []) if r.get('id') == run_id), None)
    if not event or not run or not license_nr:
        return jsonify({'success': False, 'message': 'Event, Lauf oder Lizenznummer fehlt.'}), 404

    entry = next((e for e in run.get('entries', []) if e.get('Lizenznummer') == license_nr), None)
    if not entry:
        return jsonify({'success': False, 'message': 'Teilnehmer nicht gefunden.'}), 404

    if status == 'DNS':
        # Nicht gestartet: als Ergebnis speichern (wird in Rangliste als DNS gewertet)
        entry['result'] = {'zeit': None, 'fehler': 0, 'verweigerungen': 0, 'disqualifikation': 'DNS'}
        entry['timestamp'] = datetime.now().isoformat()
    elif status == 'DIS':
        # Disqualifiziert: als Ergebnis speichern (wird in Rangliste als DIS gewertet).
        entry['result'] = {'zeit': None, 'fehler': 0, 'verweigerungen': 0, 'disqualifikation': 'DIS'}
        entry['timestamp'] = datetime.now().isoformat()
    else:
        return jsonify({'success': False, 'message': f'Unbekannter Status: {status}'}), 400

    # DNS wie DIS beenden den Eintrag: current_starter/next_starter weiterrücken
    # (analog save_result), damit der aktive Läufer nicht auf dem gesetzten
    # Teilnehmer hängen bleibt. unfinished filtert Einträge mit Zeit ODER
    # disqualifikation (DNS/DIS) heraus, ist also für beide Status korrekt.
    # sort_entries_for_startlist hält läufige Hündinnen am Ende (wie Startliste).
    entries_sorted = sort_entries_for_startlist(run.get('entries', []))
    unfinished = [
        e for e in entries_sorted
        if not (e.get('result') and (e['result'].get('zeit') or e['result'].get('disqualifikation')))
    ]
    run['current_starter'], run['next_starter'] = _pick_auto_starter(unfinished)

    # ring_entry_state ebenfalls weiterruecken, analog save_result (sonst
    # haengt der Ring-Monitor nach DNS/DIS auf dem alten Starter fest).
    ring_num_for_state = find_run_ring_number(event, run)
    ring_state_all = event.setdefault("ring_entry_state", {})
    ring_state_all[ring_num_for_state] = apply_result_saved(
        ring_state_all.get(ring_num_for_state) or {}, entries_sorted, license_nr
    )

    _save_data('events.json', events)

    try:
        ring_num = find_run_ring_number(event, run)
        socketio.emit('result_update', {'run_id': run_id, 'license_nr': license_nr, 'status': status})
        socketio.emit('announcer_update', {'event_id': event_id, 'ring_name': f"Ring {ring_num}"},
                      room=f"event:{event_id}:ring:{ring_num}")
        socketio.emit('announcer_update', {'event_id': event_id, 'ring_name': f"Ring {ring_num}"},
                      room=f"event:{event_id}")
    except Exception:
        pass

    # Portal-Sync: Live-Update + Result-Export im Hintergrund (analog save_result).
    # Ohne diesen Block blieb das Portal nach einem DIS/DNS ohne nächsten Starter
    # stehen, weil nur save_result pushte.
    try:
        from portal_sync import push_live_update, send_result_export
        from threading import Thread
        settings_for_sync = _load_settings()
        if settings_for_sync.get("portal_url"):
            if settings_for_sync.get("portal_live_api_key"):
                all_results_for_sync = _calculate_run_results(run, settings_for_sync)
                enriched_entry = next(
                    (r for r in all_results_for_sync if r.get("Lizenznummer") == license_nr),
                    entry
                )
                push_live_update(settings_for_sync, event, run, enriched_entry,
                                 ring_label=f"Ring {ring_num}")
            if settings_for_sync.get("portal_results_api_key"):
                _event_snap = dict(event)
                _settings_snap = dict(settings_for_sync)
                def _bg_export():
                    try:
                        send_result_export(_settings_snap, _event_snap, final=False)
                    except Exception:
                        pass
                Thread(target=_bg_export, daemon=True).start()
    except Exception:
        pass  # Portal-Sync darf nie den Hauptprozess unterbrechen

    return jsonify({'success': True})


# ---------------------------------------------------------------------------
# Portal-Ergebnis-Export
# ---------------------------------------------------------------------------

@live_bp.route('/live/export_results/<event_id>', methods=['GET', 'POST'])
def export_results_to_portal(event_id):
    """
    GET  → ZIP herunterladen (lokal speichern / manuell hochladen)
    POST → ZIP erzeugen und direkt ans Portal senden (benötigt konfigurierte URL+Key)

    Query-Parameter:
      ?final=1  → Export als Abschluss-Export markieren (setzt event.is_completed im Portal)
    """
    from utils import _load_data, _load_settings
    from portal_sync import build_result_export_zip, send_result_export
    from flask import send_file

    events   = _load_data('events.json')
    event    = next((e for e in events if e.get('id') == event_id), None)
    if not event:
        abort(404)

    final    = request.args.get('final', '0') == '1'
    settings = _load_settings()

    if request.method == 'GET':
        # ZIP zum Download anbieten
        zip_bytes = build_result_export_zip(event, final=final)
        filename  = f"results_{event_id}.zip"
        return Response(
            zip_bytes,
            mimetype='application/zip',
            headers={'Content-Disposition': f'attachment; filename="{filename}"'},
        )

    # POST → ans Portal senden
    result = send_result_export(settings, event, final=final)
    if result.get('error'):
        flash(_('Portal-Export fehlgeschlagen: %(error)s', error=result["error"]), 'danger')
    else:
        status_detail = f'(final={result.get("final")}, event={result.get("event_external_id")})'
        flash(_('Ergebnisse erfolgreich ans Portal übertragen %(detail)s', detail=status_detail), 'success')
    return redirect(url_for('live_bp.live_event_dashboard'))


# ---------------------------------------------------------------------------
# Ranglisten-PDF generieren und ans Portal hochladen
# ---------------------------------------------------------------------------

def _render_ranking_pdf_html(event, run, event_id, is_final):
    """Baut das Rangliste-HTML (Grundlage für PDF-Upload und Vorschau)."""
    from blueprints.routes_print import _enrich_entries_rasse_verein
    _enrich_entries_rasse_verein([run])

    settings = _load_settings()
    results       = _calculate_run_results(run, settings)
    judges        = _load_data('judges.json')
    judge_display = resolve_judge_name(event, run, judges)

    import os as _os, base64 as _b64
    # Logo-Kopfbox: xhtml2pdf (pisa) ignoriert CSS max-width/max-height auf <img>
    # und rendert sonst in nativer Pixelgrösse -> Logo sprengt die Seite. Darum
    # hier das Seitenverhältnis bestimmen und EXPLIZITE width/height in cm setzen.
    # Zielgrösse = gemessene Höhe des 3-zeiligen Titelblocks (Titel/Richter/
    # Subtitle) im gerenderten PDF = 1.8cm, damit Logo und Text optisch gleich
    # hoch wirken (per pymupdf-Textbbox verifiziert, nicht nur geschätzt).
    _LOGO_MAX_W_CM = float(_os.environ.get("AGILITY_LOGO_MAX_W_CM", "2.5"))
    _LOGO_MAX_H_CM = float(_os.environ.get("AGILITY_LOGO_MAX_H_CM", "1.8"))

    def _logo_b64(logo_key):
        fname = event.get(logo_key)
        if not fname:
            return None, ""
        from paths import data_path
        path = data_path("logos", event_id, fname)
        if not _os.path.exists(path):
            return None, ""
        ext = _os.path.splitext(fname)[1].lower().lstrip(".")
        mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                "gif": "image/gif", "svg": "image/svg+xml", "webp": "image/webp"}.get(ext, "image/png")
        with open(path, "rb") as _f:
            raw = _f.read()
        data = _b64.b64encode(raw).decode()
        data_uri = f"data:{mime};base64,{data}"

        # Explizite Zielgrösse aus dem Seitenverhältnis des Bildes berechnen.
        style = f"height:{_LOGO_MAX_H_CM}cm"  # Fallback (proportional) falls Masse unbekannt
        try:
            from PIL import Image as _Image
            import io as _pil_io
            with _Image.open(_pil_io.BytesIO(raw)) as _im:
                w_px, h_px = _im.size
            if w_px > 0 and h_px > 0:
                nat_w_cm = w_px / 96.0 * 2.54
                nat_h_cm = h_px / 96.0 * 2.54
                scale = min(_LOGO_MAX_W_CM / nat_w_cm, _LOGO_MAX_H_CM / nat_h_cm)
                style = (f"width:{nat_w_cm * scale:.2f}cm;"
                         f"height:{nat_h_cm * scale:.2f}cm")
        except Exception:
            pass  # SVG oder PIL-Fehler -> Fallback-Style (height only)
        return data_uri, style

    event_logo_data, event_logo_style = _logo_b64("event_logo_filename")
    club_logo_data,  club_logo_style  = _logo_b64("club_logo_filename")

    from flask import render_template as _rt
    return _rt(
        'print_ranking_pdf.html',
        event=event,
        run=run,
        results=results,
        judges=judges,
        judge_display=judge_display,
        is_final=is_final,
        event_logo_data=event_logo_data,
        event_logo_style=event_logo_style,
        club_logo_data=club_logo_data,
        club_logo_style=club_logo_style,
    )


@live_bp.route('/live/preview_ranking_pdf/<event_id>/<run_id>')
def preview_ranking_pdf(event_id, run_id):
    """Zeigt die Rangliste-PDF im Browser an (kein Upload) — zum Layout-Check."""
    try:
        from xhtml2pdf import pisa
        import io as _io
    except Exception as _e:
        return f"xhtml2pdf nicht verfügbar: {type(_e).__name__}: {_e}", 500

    events = _load_data('events.json')
    event  = next((e for e in events if e.get('id') == event_id), None)
    if not event:
        return "Event nicht gefunden", 404
    run = next((r for r in event.get('runs', []) if r.get('id') == run_id), None)
    if not run:
        return "Lauf nicht gefunden", 404

    is_final = request.args.get('final', '0') == '1'
    html_str = _render_ranking_pdf_html(event, run, event_id, is_final)

    buf = _io.BytesIO()
    pisa_status = pisa.CreatePDF(_io.StringIO(html_str), dest=buf)
    if pisa_status.err:
        return f"PDF-Generierung fehlgeschlagen (pisa errors: {pisa_status.err})", 500

    from flask import Response
    return Response(buf.getvalue(), mimetype='application/pdf',
                    headers={"Content-Disposition": "inline; filename=rangliste_vorschau.pdf"})


def _save_ranking_pdf_to_downloads(run, pdf_bytes, is_final, settings):
    """Speichert die Rangliste-PDF zusätzlich lokal, in einem Unterordner pro
    Tag (Datum der Erzeugung). Nutzt den in den Einstellungen konfigurierten
    `download_dir` (Zielordner für Exporte), sonst den System-Downloads-Ordner."""
    import os
    from datetime import date
    from werkzeug.utils import secure_filename

    base = (settings.get("download_dir") or "").strip()
    if not base or not os.path.isdir(base):
        base = os.path.join(os.path.expanduser("~"), "Downloads")

    day_folder = date.today().isoformat()
    base_dir = os.path.join(base, "AgilitySoftware_Ranglisten", day_folder)
    os.makedirs(base_dir, exist_ok=True)

    run_name = run.get("name") or run.get("id")
    suffix = "offiziell" if is_final else "zwischenstand"
    filename = secure_filename(f"Rangliste_{run_name}_{suffix}.pdf")
    full_path = os.path.join(base_dir, filename)
    with open(full_path, "wb") as f:
        f.write(pdf_bytes)
    return full_path


@live_bp.route('/live/upload_ranking_pdf/<event_id>/<run_id>', methods=['POST'])
def upload_ranking_pdf(event_id, run_id):
    """
    Rendert die Rangliste eines Laufs als PDF und liefert sie an Portal
    und/oder lokalen Download-Ordner aus (je nach Checkbox-Auswahl im UI).
    Form-Parameter: is_final (true/false), to_portal (true/false), to_download (true/false)
    """
    try:
        from xhtml2pdf import pisa
        import io as _io
    except Exception as _e:
        return jsonify({"error": f"xhtml2pdf nicht verfügbar: {type(_e).__name__}: {_e}"}), 500

    settings = _load_settings()
    events   = _load_data('events.json')
    event    = next((e for e in events if e.get('id') == event_id), None)
    if not event:
        return jsonify({"error": "Event nicht gefunden"}), 404

    run = next((r for r in event.get('runs', []) if r.get('id') == run_id), None)
    if not run:
        return jsonify({"error": "Lauf nicht gefunden"}), 404

    is_final    = request.form.get('is_final', 'false').lower() == 'true'
    to_portal   = request.form.get('to_portal', 'true').lower() == 'true'
    to_download = request.form.get('to_download', 'false').lower() == 'true'

    if not to_portal and not to_download:
        return jsonify({"error": "Weder Portal noch Download ausgewählt"}), 400

    html_str = _render_ranking_pdf_html(event, run, event_id, is_final)

    # HTML → PDF via xhtml2pdf
    try:
        buf = _io.BytesIO()
        pisa_status = pisa.CreatePDF(_io.StringIO(html_str), dest=buf)
        if pisa_status.err:
            return jsonify({"error": f"PDF-Generierung fehlgeschlagen (pisa errors: {pisa_status.err})"}), 500
        pdf_bytes = buf.getvalue()
    except Exception as exc:
        return jsonify({"error": f"PDF-Generierung fehlgeschlagen: {exc}"}), 500

    result = {"is_final": is_final}
    ok = True

    if to_download:
        try:
            saved_path = _save_ranking_pdf_to_downloads(run, pdf_bytes, is_final, settings)
            result["download"] = "ok"
            result["download_path"] = saved_path
        except Exception as exc:
            result["download"] = f"error: {exc}"
            ok = False

    if to_portal:
        import requests as _req

        portal_url     = (settings.get("portal_url") or "").rstrip("/")
        api_key        = settings.get("portal_results_api_key") or ""
        external_id    = event.get("external_id") or ""

        if not portal_url or not api_key:
            result["portal"] = "error: Portal nicht konfiguriert (URL oder API-Key fehlt)"
            ok = False
        elif not external_id:
            result["portal"] = "error: Event hat keine external_id – bitte Turnier neu vom Portal importieren"
            ok = False
        else:
            # Metadaten aus dem Lauf auslesen — Ring auf "Ring N"-Format normalisieren
            _raw_ring = run.get("assigned_ring") or ""
            _ring_num = re.search(r'\d+', str(_raw_ring))
            ring          = f"Ring {_ring_num.group()}" if _ring_num else (_raw_ring or "Ring 1")
            discipline    = (run.get("laufart") or "").lower()
            category_code = run.get("kategorie") or ""
            class_level   = str(run.get("klasse") or 0)

            try:
                resp = _req.post(
                    f"{portal_url}/api/resultpdf",
                    headers={"X-Api-Key": api_key},
                    files={"file": (f"rangliste_{run_id}.pdf", pdf_bytes, "application/pdf")},
                    data={
                        "event_external_id": external_id,
                        "run_name":          run.get("name") or "",
                        "ring":              ring,
                        "discipline":        discipline,
                        "category_code":     category_code,
                        "class_level":       class_level,
                        "is_final":          "true" if is_final else "false",
                    },
                    timeout=30,
                )
                if resp.ok:
                    result["portal"] = "ok"
                else:
                    result["portal"] = f"error: {resp.text}"
                    ok = False
            except Exception as exc:
                result["portal"] = f"error: Netzwerkfehler: {exc}"
                ok = False

    result["status"] = "ok" if ok else "error"
    return jsonify(result), (200 if ok else 502)


# ──────────────────────────────────────────────────────────────────────
# Stream-Deck-Plugin API: Bare-Endpoints fuer schnelle Live-Eingabe
# am Ring-PC via Hardware-Tasten. Alle Aktionen wirken auf den
# "aktuellen Starter" des aktiven Laufs am gewaehlten Ring.
# ──────────────────────────────────────────────────────────────────────

def _resolve_active_starter(ring_no):
    """
    Returns (events, event, run, entry) oder None wenn etwas fehlt.
    """
    event_id = _get_active_event_id()
    if not event_id:
        return None
    events = _load_data('events.json')
    event = next((e for e in events if e.get('id') == event_id), None)
    if not event:
        return None
    current_runs = event.get('current_runs_by_ring') or {}
    run_id = current_runs.get(str(ring_no))
    if not run_id:
        return None
    run = next((r for r in event.get('runs', []) if r.get('id') == run_id), None)
    if not run:
        return None
    current = run.get('current_starter') or {}
    if not current.get('Lizenznummer'):
        # Fallback: erster Eintrag ohne Resultat
        for e in run.get('entries', []):
            r = e.get('result') or {}
            if not r.get('zeit') and not r.get('disqualifikation'):
                current = e
                break
    if not current.get('Lizenznummer'):
        return None
    entry = next((e for e in run.get('entries', []) if e.get('Lizenznummer') == current.get('Lizenznummer')), None)
    if not entry:
        return None
    return events, event, run, entry


@live_bp.route('/api/sd/fault', methods=['POST'])
def sd_inc_fault():
    """Stream-Deck: +1 Parcoursfehler auf den aktuellen Starter."""
    data = request.get_json(silent=True) or {}
    ring_no = int(data.get('ring') or request.args.get('ring') or 1)
    resolved = _resolve_active_starter(ring_no)
    if not resolved:
        return jsonify({'success': False, 'message': 'Kein aktueller Starter'}), 404
    events, event, run, entry = resolved
    result = entry.setdefault('result', {})
    result['fehler'] = int(result.get('fehler') or 0) + 1
    _save_data('events.json', events)
    return jsonify({
        'success': True, 'action': 'fault', 'lic': entry.get('Lizenznummer'),
        'fehler': result['fehler'], 'verweigerungen': int(result.get('verweigerungen') or 0),
    })


@live_bp.route('/api/sd/refusal', methods=['POST'])
def sd_inc_refusal():
    """Stream-Deck: +1 Verweigerung auf den aktuellen Starter."""
    data = request.get_json(silent=True) or {}
    ring_no = int(data.get('ring') or request.args.get('ring') or 1)
    resolved = _resolve_active_starter(ring_no)
    if not resolved:
        return jsonify({'success': False, 'message': 'Kein aktueller Starter'}), 404
    events, event, run, entry = resolved
    result = entry.setdefault('result', {})
    result['verweigerungen'] = int(result.get('verweigerungen') or 0) + 1
    _save_data('events.json', events)
    return jsonify({
        'success': True, 'action': 'refusal', 'lic': entry.get('Lizenznummer'),
        'fehler': int(result.get('fehler') or 0), 'verweigerungen': result['verweigerungen'],
    })


@live_bp.route('/api/sd/start_release', methods=['POST'])
def sd_start_release():
    """
    Stream-Deck: Startfreigabe / Startimpuls fuer den naechsten Starter
    am gewaehlten Ring. Verwendet die bestehende ring_starter_changed-Logik.
    """
    data = request.get_json(silent=True) or {}
    ring_no = int(data.get('ring') or request.args.get('ring') or 1)
    event_id = _get_active_event_id()
    if not event_id:
        return jsonify({'success': False, 'message': 'Kein aktives Event'}), 404
    events = _load_data('events.json')
    event = next((e for e in events if e.get('id') == event_id), None)
    if not event:
        return jsonify({'success': False, 'message': 'Event nicht gefunden'}), 404
    current_runs = event.get('current_runs_by_ring') or {}
    run_id = current_runs.get(str(ring_no))
    run = next((r for r in event.get('runs', []) if r.get('id') == run_id), None) if run_id else None
    if not run:
        return jsonify({'success': False, 'message': f'Kein aktiver Lauf an Ring {ring_no}'}), 404
    ring_state = event.get('ring_entry_state') or {}
    ring_state[str(ring_no)] = apply_start_impulse(ring_state.get(str(ring_no)) or {}, run.get('entries', []))
    event['ring_entry_state'] = ring_state
    _save_data('events.json', events)
    payload = _build_ring_payload(event, ring_no)
    payload.update({'event_id': event_id})
    try:
        socketio.emit('ring_ready_changed', payload, room=f'event:{event_id}:ring:{ring_no}')
        socketio.emit('ring_ready_changed', payload, room=f'event:{event_id}')
    except Exception:
        pass
    starter = (ring_state[str(ring_no)] or {}).get('current_starter') or {}
    return jsonify({
        'success': True, 'action': 'start_release',
        'ring': ring_no, 'current_starter_lic': starter.get('Lizenznummer'),
    })

