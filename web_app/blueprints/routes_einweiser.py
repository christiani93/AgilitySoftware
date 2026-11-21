"""Elektronischer Einweiser (Ring-Steward-Tablet).

Phase 1: Touch-optimierte, read-only Ganztags-Ansicht PRO RING. Vom Hauptserver
ausgeliefert, im Chrome eines Tablets ueber das (geschuetzte) Turnier-WLAN
geoeffnet: ``http://<server-ip>:5000/einweiser/1`` bzw. ``/einweiser/2``.

Bewusst UNABHAENGIG vom Ring-PC (der Einweiser arbeitet an kommenden
Kategorien vor) — die Laufliste des Rings kommt aus derselben Quelle wie das
"Lauf auswaehlen"-Dropdown (``_resolve_runs_for_ring``), nicht aus dem aktiven
Lauf des Ring-PCs.

Modi:
- ``normal``: zeigt je Lauf des Rings die (startlisten-sortierten) Teilnehmer.
  Spaetere Phasen machen daraus einen Schreiber (Anwesenheit/Umreihen/
  "bereit"-Markierung). Heute REIN LESEND.
- ``ko``: KO-Cup-Event (Halloween Cup). Der Einweiser ist hier DAUERHAFT nur
  Anzeige; abgeschlossene (entschiedene) Duelle werden ausgeblendet.

Live-Aktualisierung ueber dieselben SocketIO-Raeume/Events wie der Ring-Monitor
(``event:<id>:ring:<n>`` + announcer_update/ring_result_saved/...), die Seite
laedt bei einem Event das Content-Partial neu.
"""
from flask import Blueprint, render_template, request, Response, jsonify

from extensions import socketio
from utils import (_get_active_event, _load_data, _save_data, resolve_judge_name,
                   sort_entries_for_startlist, format_ring_name_parts,
                   collect_ring_numbers, _starts_at_end, find_run_ring_number,
                   _DATA_LOCK)

einweiser_bp = Blueprint('einweiser_bp', __name__, template_folder='../templates')

# Nicht-autoritative Einweiser-Markierungen pro Teilnehmer (Phase 2/3). Bewusst
# OHNE Resultat-/DNS-/current_starter-Wirkung — der Einweiser MARKIERT nur
# (present/absent = Anwesenheit, ready = "bereit/am Gate", later = "kommt
# spaeter"), der Ring-PC behaelt die Hoheit ueber Wertung und aktiven Starter.
# 'none' loescht die Markierung.
#
# 'later' (Wunsch Chris 2026-11-21): Teilnehmer ist kurzfristig nicht am Gate
# (z.B. anderer Ring gerade dran). Statt ihn durch die ganze Liste nach hinten
# zu schieben (start_order-Umreihung), wird er per Markierung nur aus der
# Ring-PC-Auto-Auswahl UND -Anzeige ausgeblendet (routes_live._pick_auto_starter,
# ring_pc_dashboard.html fetchRunDetails) — der Einweiser sieht ihn weiterhin
# auf seinem Tablet. Entfernt der Einweiser die Markierung wieder (erneuter
# Tap = 'none'), taucht der Eintrag ohne jede Umsortierung automatisch wieder
# an seiner urspruenglichen Position auf.
_VALID_MARKS = {'present', 'absent', 'ready', 'later'}


def _is_ko_event(event: dict) -> bool:
    """KO-Cup-Event = es sind bereits Finals konfiguriert (lazy ko_cup-Dict)."""
    return bool((event or {}).get('ko_cup', {}).get('finals'))


# Globaler Einweiser-Anzeigemodus (alle Tablets), am KO-Ring-PC umschaltbar.
_VALID_MODES = {'auto', 'ko', 'normal'}


def _effective_ko_mode(event: dict) -> bool:
    """Effektiver Anzeigemodus der Einweiser-Tablets. `event['einweiser_mode']`:
    - 'ko'     → erzwingt KO-Anzeige (read-only Duelle)
    - 'normal' → erzwingt Normal-Läufe (auch wenn Finals konfiguriert sind)
    - 'auto'/fehlt → KO genau dann, wenn Finals konfiguriert sind (_is_ko_event).
    Der Button am KO-Ring-PC schaltet diesen globalen Override um (Wunsch HCS:
    während des KO einen normalen Quali-Ring am Einweiser vorbereiten können)."""
    mode = ((event or {}).get('einweiser_mode') or 'auto').strip().lower()
    if mode == 'ko':
        return True
    if mode == 'normal':
        return False
    return _is_ko_event(event)


def _hide_finished_arg(event: dict) -> bool:
    """`hide_finished`-Query auswerten. Default: im KO-Modus AN (Reglement-Wunsch:
    abgeschlossene Duelle ausblenden), im Normalmodus AUS (Einweiser will den
    ganzen Lauf sehen)."""
    raw = request.args.get('hide_finished')
    if raw is None:
        return _effective_ko_mode(event)
    return str(raw).strip().lower() in ('1', 'true', 'yes', 'on')


def _entry_status(entry: dict):
    """(status, label) eines Teilnehmers: 'disq' (DNS/DIS/ABR...), 'done'
    (Zeit erfasst) oder 'pending' (noch offen)."""
    res = entry.get('result') or {}
    disq = res.get('disqualifikation')
    if disq:
        return 'disq', str(disq)
    if res.get('zeit') not in (None, ''):
        return 'done', 'Beendet'
    return 'pending', ''


def _build_normal_ring(event: dict, ring_number: int, hide_finished: bool):
    """Ganztags-Laufliste eines Rings fuer ein normales Event (read-only)."""
    # Lazy-Import: vermeidet jede Import-Reihenfolge-Kopplung mit routes_live.
    from blueprints.routes_live import _resolve_runs_for_ring, _find_run_block_for_run

    runs_for_ring, _debug = _resolve_runs_for_ring(event, ring_number)
    judges = _load_data('judges.json')
    current_runs = event.get('current_runs_by_ring') or event.get('current_run_per_ring') or {}
    active_run_id = current_runs.get(str(ring_number)) or current_runs.get(ring_number)

    runs_model = []
    for run in runs_for_ring:
        block, _rk = _find_run_block_for_run(event, run, str(ring_number))
        judge = resolve_judge_name(event, run, judges, block)
        entries_sorted = sort_entries_for_startlist(run.get('entries', []) or [])
        is_active = run.get('id') == active_run_id
        cur_lic = (run.get('current_starter') or {}).get('Lizenznummer')
        next_lic = (run.get('next_starter') or {}).get('Lizenznummer')

        # Fallback wie Ring-Monitor: zu Laufbeginn ist current_starter noch leer
        # (wird erst beim ersten save_result/Ring-PC-Socket gesetzt). Dann gilt der
        # erste noch nicht gelaufene (pending) Eintrag als "am Start", damit der
        # Einweiser nicht mit leerem Starter dasteht.
        if is_active and not cur_lic:
            pending = [e for e in entries_sorted if _entry_status(e)[0] == 'pending']
            if pending:
                cur_lic = pending[0].get('Lizenznummer')
                if not next_lic and len(pending) > 1:
                    next_lic = pending[1].get('Lizenznummer')

        entries_model = []
        finished = 0
        for e in entries_sorted:
            status, label = _entry_status(e)
            if status != 'pending':
                finished += 1
            if hide_finished and status != 'pending':
                continue
            lic = e.get('Lizenznummer')
            handler, dog = format_ring_name_parts(e)
            entries_model.append({
                'license': lic,
                'startnummer': e.get('Startnummer'),
                'handler': handler,
                'dog': dog,
                'status': status,
                'status_label': label,
                'mark': e.get('einweiser_mark') or '',
                'starts_at_end': _starts_at_end(e),
                'is_current': bool(is_active and lic and lic == cur_lic),
                'is_next': bool(is_active and lic and lic == next_lic),
            })

        total = len(entries_sorted)
        runs_model.append({
            'id': run.get('id'),
            'title': run.get('name') or '',
            'kategorie': run.get('kategorie'),
            'klasse': run.get('klasse'),
            'laufart': run.get('laufart'),
            'judge': judge,
            'is_active': is_active,
            'counts': {'total': total, 'finished': finished, 'pending': total - finished},
            'entries': entries_model,
        })
    return runs_model, active_run_id


def _build_ko_ring(event: dict, ring_number: int, hide_finished: bool):
    """Read-only KO-Duell-Liste fuer EINEN Ring. Spiegelt die Sortierung von
    ``routes_ko_cup._event_ring_startlists`` (frueheste Runden zuerst, Finals
    zuletzt in Kategorie-Reihenfolge), ergaenzt aber pro Zeile ``decided``
    (``winner_id`` gesetzt) — damit abgeschlossene Duelle ausgeblendet werden
    koennen. KO nutzt laut Reglement fix 2 Ringe."""
    import ko_cup

    ko = event.get('ko_cup') or {}
    cat_rank = {c: i for i, c in enumerate(ko_cup.CATEGORY_ORDER)}
    type_rank = {'third_place': 0, 'winner': 1}
    rows = []
    for final in ko.get('finals', []):
        rounds = ko_cup.matchups_by_round(final)
        if not rounds:
            continue
        rounds_total = max(rnd for rnd, _label, _ms in rounds)
        c_rank = cat_rank.get(final.get('category_code'), 99)
        for round_no, label, matchups in rounds:
            phase = rounds_total - round_no  # 0 = letzte Runde
            for m in matchups:
                pa = ko_cup.get_participant(final, m.get('a_id'))
                pb = ko_cup.get_participant(final, m.get('b_id'))
                if not (pa and pb):
                    continue
                decided = bool(m.get('winner_id'))
                if hide_finished and decided:
                    continue
                rings = ko_cup.ring_assignment(final, m)
                t_rank = type_rank.get(m.get('matchup_type'), 1)
                for side, part in (('a', pa), ('b', pb)):
                    try:
                        side_ring = int(rings[side]['run1'])
                    except (KeyError, TypeError, ValueError):
                        continue
                    if side_ring != int(ring_number):
                        continue
                    rows.append({
                        'sort_key': (-phase, c_rank, t_rank, m['matchup_no']),
                        'category': final.get('group_label') or final.get('category_code'),
                        'round_label': label,
                        'matchup_no': m['matchup_no'],
                        'handler': part.get('handler_name'),
                        'dog': part.get('dog_name'),
                        'startnummer': part.get('start_number'),
                        'decided': decided,
                    })
    rows.sort(key=lambda r: r['sort_key'])
    return rows


def build_einweiser_model(event: dict, ring_number: int, hide_finished: bool):
    """Baut das Anzeige-Modell fuer einen Ring (normal ODER ko)."""
    base = {
        'ring_number': ring_number,
        'ring_label': f"Ring {ring_number}",
        'event_id': event.get('id'),
        'event_name': event.get('Bezeichnung') or event.get('name') or '',
        'hide_finished': hide_finished,
    }
    if _effective_ko_mode(event):
        base.update({
            'mode': 'ko',
            'read_only': True,
            'ko_rows': _build_ko_ring(event, ring_number, hide_finished),
            'runs': [],
            'active_run_id': None,
        })
        return base
    runs_model, active_run_id = _build_normal_ring(event, ring_number, hide_finished)
    base.update({
        'mode': 'normal',
        'read_only': False,  # P2+: Anwesenheit/bereit markieren + umreihen erlaubt
        'runs': runs_model,
        'active_run_id': active_run_id,
        'ko_rows': [],
    })
    return base


@einweiser_bp.get('/einweiser')
def einweiser_pick():
    """Ring-Auswahl (erste Seite auf dem Tablet)."""
    event = _get_active_event()
    rings = collect_ring_numbers(event) if event else []
    return render_template('einweiser_pick.html', event=event, rings=rings)


@einweiser_bp.get('/einweiser/<int:ring_number>')
def einweiser_ring(ring_number):
    event = _get_active_event()
    if not event:
        return render_template('einweiser.html', event=None, model=None, ring_number=ring_number)
    model = build_einweiser_model(event, ring_number, _hide_finished_arg(event))
    return render_template('einweiser.html', event=event, model=model, ring_number=ring_number)


@einweiser_bp.get('/api/render_einweiser_content/<int:ring_number>')
def render_einweiser_content(ring_number):
    """Content-Partial fuer die Live-Aktualisierung (SocketIO-Refresh)."""
    event = _get_active_event()
    if not event:
        return Response("<div class='ew-empty'>Kein aktives Event.</div>", mimetype='text/html')
    model = build_einweiser_model(event, ring_number, _hide_finished_arg(event))
    return render_template('_einweiser_content.html', model=model)


@einweiser_bp.post('/einweiser/api/set_mode')
def api_set_einweiser_mode():
    """Schaltet den GLOBALEN Einweiser-Anzeigemodus aller Tablets um (am KO-Ring-PC).
    Body: {"mode": "auto"|"ko"|"normal"}. Speichert `event['einweiser_mode']` am
    aktiven Event ('auto' löscht den Override) und broadcastet `einweiser_mode_changed`
    → die Tablets laden ihr Content-Partial neu (neuer Modus)."""
    data = request.get_json(silent=True) or {}
    mode = (data.get('mode') or '').strip().lower()
    if mode not in _VALID_MODES:
        return jsonify({'success': False, 'message': f'Unbekannter Modus: {mode}'}), 400
    active = _get_active_event()
    if not active:
        return jsonify({'success': False, 'message': 'Kein aktives Event.'}), 404
    event_id = active.get('id')
    with _DATA_LOCK:
        events = _load_data('events.json')
        event = next((e for e in events if e.get('id') == event_id), None)
        if not event:
            return jsonify({'success': False, 'message': 'Event nicht gefunden.'}), 404
        if mode == 'auto':
            event.pop('einweiser_mode', None)
        else:
            event['einweiser_mode'] = mode
        effective_ko = _effective_ko_mode(event)
        _save_data('events.json', events)

    try:
        socketio.emit('einweiser_mode_changed', {'event_id': event_id, 'mode': mode})
    except Exception:
        pass
    return jsonify({'success': True, 'mode': mode, 'effective_ko': effective_ko})


@einweiser_bp.post('/einweiser/api/mark/<event_id>/<run_id>')
def api_set_mark(event_id, run_id):
    """Setzt/loescht eine nicht-autoritative Einweiser-Markierung (present/absent/
    ready) fuer einen Teilnehmer. Schreibt KEIN Resultat und veraendert NICHT
    current_starter — nur ein Hinweis-Flag. Im KO-Modus gesperrt (read-only)."""
    data = request.get_json(silent=True) or {}
    lic = data.get('license_number')
    mark = (data.get('mark') or '').strip().lower()
    if mark not in _VALID_MARKS and mark != 'none':
        return jsonify({'success': False, 'message': f'Unbekannte Markierung: {mark}'}), 400

    # Laden+Aendern+Speichern unter EINEM Lock -> der Einweiser-Write kann einen
    # zwischenzeitlichen Ring-PC-Write (z.B. ein Resultat) nicht ueberschreiben:
    # der Ring-PC-save kann nicht zwischen unserem load und save liegen. Verloren
    # gehen kann hoechstens die Markierung selbst (harmlos, self-healing).
    with _DATA_LOCK:
        events = _load_data('events.json')
        event = next((e for e in events if e.get('id') == event_id), None)
        if not event:
            return jsonify({'success': False, 'message': 'Event nicht gefunden.'}), 404
        if _effective_ko_mode(event):
            return jsonify({'success': False, 'message': 'KO-Modus ist nur Anzeige.'}), 403
        run = next((r for r in event.get('runs', []) or [] if r.get('id') == run_id), None)
        if not run:
            return jsonify({'success': False, 'message': 'Lauf nicht gefunden.'}), 404
        entry = next((e for e in run.get('entries', []) or [] if e.get('Lizenznummer') == lic), None)
        if not entry:
            return jsonify({'success': False, 'message': 'Teilnehmer nicht gefunden.'}), 404

        if mark == 'none':
            entry.pop('einweiser_mark', None)
        else:
            if mark == 'ready':
                # Es darf immer nur EIN Teilnehmer "bereit / am Gate" sein: ein
                # zuvor als "bereit" markierter Hund im selben Lauf wird gelöscht
                # (present/absent bleiben unberührt, da einweiser_mark nur EINEN
                # Wert je Eintrag trägt). Der Client lädt bei einweiser_mark_changed
                # die ganze Liste neu → der alte "bereit"-Badge verschwindet sofort.
                for other in run.get('entries', []) or []:
                    if other is not entry and other.get('einweiser_mark') == 'ready':
                        other.pop('einweiser_mark', None)
            entry['einweiser_mark'] = mark
        _save_data('events.json', events)

    # Global broadcasten (ohne Raum) — erreicht Tablet UND Ring-PC-Dashboard
    # (letzteres tritt keinem Raum bei, hoert nur globale Events wie result_update).
    try:
        socketio.emit('einweiser_mark_changed',
                      {'event_id': event_id, 'run_id': run_id, 'license_nr': lic, 'mark': mark})
    except Exception:
        pass
    return jsonify({'success': True, 'mark': '' if mark == 'none' else mark})


@einweiser_bp.post('/einweiser/api/reorder/<event_id>/<run_id>')
def api_reorder(event_id, run_id):
    """Umreihen: schiebt einen Teilnehmer in der Startreihenfolge eines Laufs um
    eine Position (up/down). Vergibt danach ``start_order`` an ALLE Einträge des
    Laufs (0..n), sodass die Reihenfolge vollständig explizit ist. Veraendert
    bewusst NICHT current_starter (der Ring-PC behaelt die Starter-Hoheit). Im
    KO-Modus gesperrt."""
    data = request.get_json(silent=True) or {}
    lic = data.get('license_number')
    direction = (data.get('direction') or '').strip().lower()
    if direction not in ('up', 'down'):
        return jsonify({'success': False, 'message': f'Unbekannte Richtung: {direction}'}), 400

    with _DATA_LOCK:
        events = _load_data('events.json')
        event = next((e for e in events if e.get('id') == event_id), None)
        if not event:
            return jsonify({'success': False, 'message': 'Event nicht gefunden.'}), 404
        if _effective_ko_mode(event):
            return jsonify({'success': False, 'message': 'KO-Modus ist nur Anzeige.'}), 403
        run = next((r for r in event.get('runs', []) or [] if r.get('id') == run_id), None)
        if not run:
            return jsonify({'success': False, 'message': 'Lauf nicht gefunden.'}), 404

        entries = run.get('entries', []) or []
        ordered = sort_entries_for_startlist(entries)  # gleiche Objektreferenzen
        idx = next((i for i, e in enumerate(ordered) if e.get('Lizenznummer') == lic), None)
        if idx is None:
            return jsonify({'success': False, 'message': 'Teilnehmer nicht gefunden.'}), 404

        swap = idx - 1 if direction == 'up' else idx + 1
        if swap < 0 or swap >= len(ordered):
            return jsonify({'success': True, 'noop': True})  # schon am Rand
        ordered[idx], ordered[swap] = ordered[swap], ordered[idx]
        for pos, e in enumerate(ordered):
            e['start_order'] = pos
        ring_no = find_run_ring_number(event, run) or '1'
        _save_data('events.json', events)

    try:
        payload = {'event_id': event_id, 'run_id': run_id, 'ring_name': f"Ring {ring_no}"}
        socketio.emit('einweiser_order_changed', payload)  # global: Tablet + Ring-PC
        for room in (f"event:{event_id}:ring:{ring_no}", f"event:{event_id}"):
            socketio.emit('announcer_update', payload, room=room)  # Ring-Monitor zieht nach
    except Exception:
        pass
    return jsonify({'success': True})
