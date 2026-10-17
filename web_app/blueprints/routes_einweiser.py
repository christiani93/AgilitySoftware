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
from flask import Blueprint, render_template, request, Response

from utils import (_get_active_event, _load_data, resolve_judge_name,
                   sort_entries_for_startlist, format_ring_name_parts,
                   collect_ring_numbers, _starts_at_end)

einweiser_bp = Blueprint('einweiser_bp', __name__, template_folder='../templates')


def _is_ko_event(event: dict) -> bool:
    """KO-Cup-Event = es sind bereits Finals konfiguriert (lazy ko_cup-Dict)."""
    return bool((event or {}).get('ko_cup', {}).get('finals'))


def _hide_finished_arg(event: dict) -> bool:
    """`hide_finished`-Query auswerten. Default: im KO-Modus AN (Reglement-Wunsch:
    abgeschlossene Duelle ausblenden), im Normalmodus AUS (Einweiser will den
    ganzen Lauf sehen)."""
    raw = request.args.get('hide_finished')
    if raw is None:
        return _is_ko_event(event)
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
                'startnummer': e.get('Startnummer'),
                'handler': handler,
                'dog': dog,
                'status': status,
                'status_label': label,
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
    if _is_ko_event(event):
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
        'read_only': True,  # Phase 1 ist noch rein lesend
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
