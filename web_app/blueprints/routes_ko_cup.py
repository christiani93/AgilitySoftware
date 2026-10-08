"""
KO-Cup ("American") – Blueprint für Finale-Verwaltung und Bracket-Durchführung.

Erst-Ausgabe: Halloween Cup (HCS), Final am Samstag. Die KO-Logik liegt in
`ko_cup.py` (reine Funktionen); hier nur Laden/Speichern des Event-Dicts,
Formular-Handling und Anzeige-Viewmodels.

Das KO-System ist ein **Add-on auf einem beliebigen Event** (ein HCS-Samstag ist
ein normales Turnier mit Quali-Läufen PLUS dem Final). Es wird nicht über die
`Veranstaltungsart` erzwungen, sondern lazy unter `event["ko_cup"]` angelegt.

Finalisten kommen später via eventexport vom Portal (inkl. Startnummer); bis
dahin können sie hier manuell erfasst werden.
"""
from __future__ import annotations

import random

from flask import (Blueprint, render_template, request, redirect,
                   url_for, flash, abort, jsonify)

from utils import _load_data, _save_data, get_event_logo_data_uris
import ko_cup
import ko_qualification

try:  # Im EXE/Server vorhanden; in schlanken Unit-Tests (bare Flask) optional.
    from extensions import socketio
except Exception:  # pragma: no cover
    socketio = None


def _emit(event, payload, **kw):
    """SocketIO-Emit, der in Tests ohne laufenden Server leise no-op bleibt."""
    if socketio is None:
        return
    try:
        socketio.emit(event, payload, **kw)
    except Exception:
        pass

ko_cup_bp = Blueprint('ko_cup_bp', __name__, template_folder='../templates',
                      url_prefix='/ko-cup')

EVENTS_FILE = 'events.json'

CATEGORY_ORDER = ko_cup.CATEGORY_ORDER
SOURCES = ["run", "fillup", "title_defender", "wildcard"]
SOURCE_LABELS = {
    "run": "Quali-Lauf",
    "fillup": "Auffüller",
    "title_defender": "Titelverteidiger",
    "wildcard": "Wildcard",
}


# ── Helfer ──────────────────────────────────────────────────────────────────

def _get_event(event_id: str):
    events = _load_data(EVENTS_FILE)
    event = next((e for e in events if e.get('id') == event_id), None)
    return events, event


def _ensure_ko_cup(event: dict) -> dict:
    ko = event.setdefault('ko_cup', {})
    ko.setdefault('enabled', True)
    ko.setdefault('finals', [])
    return ko


def _get_final(event: dict, final_id: str) -> dict | None:
    ko = _ensure_ko_cup(event)
    return next((f for f in ko['finals'] if f.get('id') == final_id), None)


def _to_float(value, default=None):
    v = (value or '').strip() if isinstance(value, str) else value
    if v in (None, ''):
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _to_int(value, default=0):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _parse_run_form(side: str, run_key: str) -> dict:
    """Liest ein Lauf-Teilergebnis (<side>_<run_key>_time/faults/refusals/dis)."""
    prefix = f"{side}_{run_key}"
    return {
        "time": _to_float(request.form.get(f"{prefix}_time")),
        "faults": _to_int(request.form.get(f"{prefix}_faults"), 0),
        "refusals": _to_int(request.form.get(f"{prefix}_refusals"), 0),
        "dis": bool(request.form.get(f"{prefix}_dis")),
    }


# ── Dashboard: Übersicht aller Finals ─────────────────────────────────────────

@ko_cup_bp.get('/config/<event_id>')
def ko_config(event_id):
    events, event = _get_event(event_id)
    if not event:
        abort(404)
    ko = _ensure_ko_cup(event)
    _save_data(EVENTS_FILE, events)

    finals_view = []
    for f in ko['finals']:
        finals_view.append({
            "final": f,
            "n_participants": len(f.get('participants', [])),
            "n_with_draw": sum(1 for p in f.get('participants', []) if p.get('draw_number') is not None),
            "status": ko_cup.bracket_status(f),
        })
    # feste Reihenfolge Large→Small
    order = {c: i for i, c in enumerate(CATEGORY_ORDER)}
    finals_view.sort(key=lambda v: order.get(v['final'].get('category_code'), 99))

    return render_template(
        'ko_cup_config.html',
        event=event,
        finals_view=finals_view,
        categories=CATEGORY_ORDER,
    )


@ko_cup_bp.post('/config/<event_id>')
def ko_config_post(event_id):
    events, event = _get_event(event_id)
    if not event:
        abort(404)
    ko = _ensure_ko_cup(event)
    action = request.form.get('action')

    if action == 'add_final':
        category = request.form.get('category_code', '').strip()
        if category not in CATEGORY_ORDER:
            flash("Ungültige Kategorie.", "error")
        elif any(f.get('category_code') == category for f in ko['finals']):
            flash(f"Für {category} existiert bereits ein Finale.", "error")
        else:
            ko['finals'].append({
                "id": ko_cup._gen_id("final"),
                "group_label": category,
                "category_code": category,
                "class_level": None,
                "participants": [],
                "matchups": [],
                "results": [],
                "is_published": False,
            })
            flash(f"Finale {category} angelegt.", "success")

    elif action == 'delete_final':
        fid = request.form.get('final_id')
        ko['finals'] = [f for f in ko['finals'] if f.get('id') != fid]
        flash("Finale entfernt.", "info")

    elif action == 'derive_finalists':
        result = ko_qualification.apply_ko_qualification(event)
        touched = result.get('finals_touched') or []
        if not touched:
            flash("Keine lauf-basierten Finalisten gefunden – passen Laufart/Schlüssel "
                  "zu den erfassten Läufen (Tunnellauf, Agility, Jumping)?", "warning")
        else:
            parts = []
            for cat in touched:
                c = result['counts'][cat]
                parts.append(f"{cat}: {c['derived']} abgeleitet"
                             + (f" + {c['manual']} manuell" if c['manual'] else ""))
            flash("Finalisten aus den Läufen abgeleitet (" + "; ".join(parts) + "). "
                  "Bestehende Brackets wurden zurückgesetzt; manuelle Einträge blieben erhalten.",
                  "success")

    _save_data(EVENTS_FILE, events)
    return redirect(url_for('ko_cup_bp.ko_config', event_id=event_id))


# ── Kombinierte Quali-Ranglisten (Tunnellauf klassenübergreifend) ─────────────

@ko_cup_bp.get('/rankings/<event_id>')
def ko_rankings(event_id):
    """Zeigt pro Schlüssel-Lauf die Rangliste je Kategorie — Tunnellauf
    klassenübergreifend kombiniert — mit Markierung, wer sich qualifiziert
    (inkl. Dedup/Nachrücken). Erfassungs-/Kontroll-Hilfe am Event-Tag."""
    events, event = _get_event(event_id)
    if not event:
        abort(404)
    blocks = ko_qualification.ranking_tables(event)
    return render_template(
        'ko_cup_rankings.html',
        event=event,
        blocks=blocks,
        category_order=CATEGORY_ORDER,
    )


# ── Ring-Startlisten: Laufreihenfolge UEBER ALLE Finals (Kategorien) ──────────

def _event_ring_startlists(ko: dict) -> list:
    """Baut je Ring (fix 2 — Reglement: jedes Duell nutzt beide Ringe, siehe
    ring_assignment) eine kombinierte Startliste UEBER ALLE Finals/Kategorien
    eines Events — die Ringe laufen nacheinander alle Kategorien, nicht nur eine.

    Nur Lauf 1 wird aufgelistet: bei Lauf 2 wechseln dieselben zwei Teams
    intern einfach den Ring (siehe ring_assignment) — ein eigener Eintrag
    dafuer ist ueberfluessig.

    Sortierung je Ring:
      1) Phase = Runden VOR der Entscheidung (0 = letzte Runde, also Final +
         Spiel um Platz 3; steigend fuer fruehere Runden). Fruehe Runden aller
         Kategorien laufen so zuerst, die Finalrunden aller Kategorien liegen
         gemeinsam am Schluss.
      2) Kategorie-Reihenfolge (CATEGORY_ORDER, S-M-I-L) als Tie-Breaker
         innerhalb derselben Phase — v.a. wirksam am Schluss bei den Finalrunden.
      3) Innerhalb der letzten Runde: Spiel um Platz 3 vor dem Final ("Grosses
         Finale" laeuft als letztes Duell des Events), sonst Duell-Nr.

    Hinweis: Dies ist eine generische Annaeherung (frueheste Runden zuerst,
    Finalrunden zuletzt in Kategorie-Reihenfolge) — keine exakte Nachbildung
    einer manuell erstellten Ablauftabelle, die zusaetzlich Ring-Auslastung
    pro Runde balanciert."""
    cat_rank = {c: i for i, c in enumerate(CATEGORY_ORDER)}
    type_rank = {"third_place": 0, "winner": 1}
    rows_by_ring: dict[int, list] = {1: [], 2: []}
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
                rings = ko_cup.ring_assignment(final, m)
                t_rank = type_rank.get(m.get('matchup_type'), 1)
                for side, part in (('a', pa), ('b', pb)):
                    ring_no = rings[side]['run1']
                    rows_by_ring[ring_no].append({
                        "sort_key": (-phase, c_rank, t_rank, m['matchup_no']),
                        "category": final.get('group_label') or final.get('category_code'),
                        "round_label": label,
                        "matchup_no": m['matchup_no'],
                        "dog_name": part.get('dog_name'),
                        "handler_name": part.get('handler_name'),
                        "start_number": part.get('start_number'),
                    })
    out = []
    for ring_no in (1, 2):
        rows = sorted(rows_by_ring[ring_no], key=lambda r: r['sort_key'])
        out.append({"ring": ring_no, "rows": rows})
    return out


@ko_cup_bp.get('/rings_print/<event_id>')
def ko_rings_print(event_id):
    """Druckansicht: Startliste pro Ring, kombiniert ueber alle Kategorien/
    Finals des Events (Laufreihenfolge respektiert Runden-Phase + Kategorie-
    Reihenfolge S-M-I-L)."""
    events, event = _get_event(event_id)
    if not event:
        abort(404)
    ko = _ensure_ko_cup(event)
    _save_data(EVENTS_FILE, events)
    logos = get_event_logo_data_uris(event)
    return render_template(
        'ko_cup_rings_print.html',
        event=event,
        ring_startlists=_event_ring_startlists(ko),
        title='Ring-Startlisten',
        event_logo_data=logos['event'],
        club_logo_data=logos['club'],
    )


# ── Finale-Detail: Finalisten, Losnummern, Bracket, Ergebnisse ────────────────

def _bracket_view(final: dict) -> list:
    """Viewmodel: pro Runde (label, matchups mit aufgelösten Namen + Ringen)."""
    rounds = ko_cup.matchups_by_round(final)
    view = []
    for rnd, label, matchups in rounds:
        mv = []
        for m in matchups:
            pa = ko_cup.get_participant(final, m.get('a_id'))
            pb = ko_cup.get_participant(final, m.get('b_id'))
            rings = ko_cup.ring_assignment(final, m) if (pa and pb) else None
            mv.append({
                "m": m,
                "a": pa, "b": pb,
                "a_total": ko_cup.score_side(m.get('a')),
                "b_total": ko_cup.score_side(m.get('b')),
                "rings": rings,
                "is_tie": ko_cup.is_tie(m),
                "winner": ko_cup.get_participant(final, m.get('winner_id')),
            })
        view.append({"round_no": rnd, "label": label, "matchups": mv})
    return view


def _results_view(final: dict) -> list:
    out = []
    for r in final.get('results', []):
        p = ko_cup.get_participant(final, r['participant_id'])
        if p:
            out.append({"rank": r['rank'], "p": p})
    return out


@ko_cup_bp.get('/final/<event_id>/<final_id>')
def ko_final_detail(event_id, final_id):
    events, event = _get_event(event_id)
    if not event:
        abort(404)
    final = _get_final(event, final_id)
    if not final:
        abort(404)

    return render_template(
        'ko_cup_final.html',
        event=event,
        final=final,
        sources=SOURCES,
        source_labels=SOURCE_LABELS,
        status=ko_cup.bracket_status(final),
        bracket=_bracket_view(final),
        results=_results_view(final),
    )


@ko_cup_bp.get('/final/<event_id>/<final_id>/print')
def ko_final_print(event_id, final_id):
    """Druckansicht: Duell-Laufzettel (mit Ring-/Startnummer-Zuteilung),
    Bracket-Übersicht und Endrangliste. Browser-Druck (wie übrige Drucksachen)."""
    events, event = _get_event(event_id)
    if not event:
        abort(404)
    final = _get_final(event, final_id)
    if not final:
        abort(404)

    # Finalisten in Losnummern-Reihenfolge (unglost ans Ende)
    participants = sorted(
        final.get('participants', []),
        key=lambda p: (p.get('draw_number') is None, p.get('draw_number') or 0),
    )
    logos = get_event_logo_data_uris(event)
    return render_template(
        'ko_cup_print.html',
        event=event,
        final=final,
        participants=participants,
        source_labels=SOURCE_LABELS,
        status=ko_cup.bracket_status(final),
        bracket=_bracket_view(final),
        results=_results_view(final),
        title='KO-Final %s' % (final.get('group_label') or ''),
        event_logo_data=logos['event'],
        club_logo_data=logos['club'],
    )


@ko_cup_bp.post('/final/<event_id>/<final_id>')
def ko_final_post(event_id, final_id):
    events, event = _get_event(event_id)
    if not event:
        abort(404)
    final = _get_final(event, final_id)
    if not final:
        abort(404)
    action = request.form.get('action')

    if action == 'add_participant':
        dog = request.form.get('dog_name', '').strip()
        handler = request.form.get('handler_name', '').strip()
        if not dog:
            flash("Hundename ist Pflicht.", "error")
        else:
            final.setdefault('participants', []).append({
                "id": ko_cup._gen_id("p"),
                "dog_name": dog,
                "handler_name": handler,
                "license_no": request.form.get('license_no', '').strip() or None,
                "start_number": _to_int(request.form.get('start_number'), None) if request.form.get('start_number') else None,
                "seeding_rank": _to_int(request.form.get('seeding_rank'), None) if request.form.get('seeding_rank') else None,
                "draw_number": _to_int(request.form.get('draw_number'), None) if request.form.get('draw_number') else None,
                "source": request.form.get('source', 'run'),
            })
            flash("Finalist hinzugefügt.", "success")

    elif action == 'delete_participant':
        pid = request.form.get('participant_id')
        final['participants'] = [p for p in final.get('participants', []) if p.get('id') != pid]
        final['matchups'] = []  # Bracket invalidieren
        final['results'] = []
        flash("Finalist entfernt – Bracket zurückgesetzt.", "info")

    elif action == 'set_draws':
        for p in final.get('participants', []):
            raw = request.form.get(f"draw_{p['id']}")
            p['draw_number'] = _to_int(raw, None) if raw and raw.strip() else None
        flash("Losnummern gespeichert.", "success")

    elif action == 'random_draws':
        parts = final.get('participants', [])
        numbers = list(range(1, len(parts) + 1))
        random.shuffle(numbers)
        for p, n in zip(parts, numbers):
            p['draw_number'] = n
        flash("Losnummern zufällig vergeben (Test).", "success")

    elif action == 'generate_bracket':
        parts = [p for p in final.get('participants', []) if p.get('draw_number') is not None]
        if len(parts) < 2:
            flash("Mindestens 2 Finalisten mit Losnummern nötig.", "error")
        else:
            final['matchups'] = ko_cup.build_bracket(final['participants'])
            ko_cup.recompute(final)
            flash(f"Bracket mit {len(parts)} Finalisten generiert.", "success")

    _save_data(EVENTS_FILE, events)
    return redirect(url_for('ko_cup_bp.ko_final_detail', event_id=event_id, final_id=final_id))


@ko_cup_bp.post('/matchup/<event_id>/<final_id>/<matchup_id>')
def ko_matchup_result(event_id, final_id, matchup_id):
    events, event = _get_event(event_id)
    if not event:
        abort(404)
    final = _get_final(event, final_id)
    if not final:
        abort(404)
    matchup = next((m for m in final.get('matchups', []) if m.get('id') == matchup_id), None)
    if not matchup:
        abort(404)

    forfeit = request.form.get('forfeit', '')
    if forfeit == 'a':
        matchup['forfeit_id'] = matchup.get('a_id')
    elif forfeit == 'b':
        matchup['forfeit_id'] = matchup.get('b_id')
    else:
        matchup['forfeit_id'] = None

    if not matchup['forfeit_id']:
        matchup['a'] = {"run1": _parse_run_form('a', 'run1'), "run2": _parse_run_form('a', 'run2')}
        matchup['b'] = {"run1": _parse_run_form('b', 'run1'), "run2": _parse_run_form('b', 'run2')}

    # Manueller Sieger (für Gleichstand) – 'a' | 'b' | ''
    manual = request.form.get('manual_winner', '')
    if manual == 'a':
        matchup['manual_winner_id'] = matchup.get('a_id')
    elif manual == 'b':
        matchup['manual_winner_id'] = matchup.get('b_id')
    else:
        matchup['manual_winner_id'] = None

    ko_cup.recompute(final)
    _save_data(EVENTS_FILE, events)
    flash("Ergebnis gespeichert.", "success")
    return redirect(url_for('ko_cup_bp.ko_final_detail', event_id=event_id, final_id=final_id))


# ── Live/2-Ring: JSON-State + Zeit-Ingest vom Ring-PC ─────────────────────────
#
# Betriebsmodell (Reglement): Pro Duell laufen beide Teams je 2x, einmal pro
# Ring. Zwischen Lauf 1 und Lauf 2 wechseln die Teams den Ring. Dadurch misst
# JEDER Ring pro Duell zwei Laeufe (je einen von jedem Team):
#   Ring der Seite-A-Lauf1 misst: A/run1 und B/run2
#   der andere Ring misst:        B/run1 und A/run2
# Die Zuteilung liefert ko_cup.ring_assignment (tiefere Startnummer -> Ring 1).

def _participant_brief(final: dict, pid: str | None) -> dict | None:
    p = ko_cup.get_participant(final, pid)
    if not p:
        return None
    return {
        "id": p["id"],
        "dog_name": p.get("dog_name"),
        "handler_name": p.get("handler_name"),
        "start_number": p.get("start_number"),
    }


def _matchup_json(final: dict, m: dict, label: str) -> dict:
    pa = ko_cup.get_participant(final, m.get("a_id"))
    pb = ko_cup.get_participant(final, m.get("b_id"))
    rings = ko_cup.ring_assignment(final, m) if (pa and pb) else None
    return {
        "id": m["id"],
        "round_no": m["round_no"],
        "matchup_no": m["matchup_no"],
        "matchup_type": m["matchup_type"],
        "label": label,
        "a": _participant_brief(final, m.get("a_id")),
        "b": _participant_brief(final, m.get("b_id")),
        "a_runs": m.get("a"),
        "b_runs": m.get("b"),
        "a_total": ko_cup.score_side(m.get("a")),
        "b_total": ko_cup.score_side(m.get("b")),
        "winner_id": m.get("winner_id"),
        "forfeit_id": m.get("forfeit_id"),
        "is_tie": ko_cup.is_tie(m),
        "rings": rings,
    }


def _final_json(final: dict) -> dict:
    rounds = ko_cup.matchups_by_round(final)
    matchups = []
    for rnd, label, ms in rounds:
        for m in ms:
            matchups.append(_matchup_json(final, m, label))
    return {
        "id": final["id"],
        "group_label": final.get("group_label"),
        "category_code": final.get("category_code"),
        "status": ko_cup.bracket_status(final),
        "matchups": matchups,
    }


@ko_cup_bp.get('/api/state/<event_id>')
def ko_api_state(event_id):
    """Vollständiger KO-Stand als JSON – vom Ring-PC (und der Live-Anzeige)
    gepollt/initial geladen."""
    events, event = _get_event(event_id)
    if not event:
        return jsonify({"success": False, "message": "Event nicht gefunden"}), 404
    ko = _ensure_ko_cup(event)
    order = {c: i for i, c in enumerate(CATEGORY_ORDER)}
    finals = sorted(ko['finals'], key=lambda f: order.get(f.get('category_code'), 99))
    return jsonify({
        "success": True,
        "event_id": event_id,
        "event_name": event.get("Bezeichnung"),
        "finals": [_final_json(f) for f in finals],
    })


@ko_cup_bp.post('/api/save_run/<event_id>/<final_id>/<matchup_id>')
def ko_api_save_run(event_id, final_id, matchup_id):
    """Schreibt EINEN Lauf (ein Team, ein Lauf) in ein Duell – aufgerufen vom
    Ring-PC nach TIMY-Impuls (oder manuell). Danach Bracket neu rechnen,
    speichern und Live-Update senden.

    Body (JSON): {side:'a'|'b', run:'run1'|'run2',
                  time: float|None, faults:int, refusals:int, dis:bool}
    """
    events, event = _get_event(event_id)
    if not event:
        return jsonify({"success": False, "message": "Event nicht gefunden"}), 404
    final = _get_final(event, final_id)
    if not final:
        return jsonify({"success": False, "message": "Finale nicht gefunden"}), 404
    matchup = next((m for m in final.get('matchups', []) if m.get('id') == matchup_id), None)
    if not matchup:
        return jsonify({"success": False, "message": "Duell nicht gefunden"}), 404

    data = request.get_json(force=True, silent=True) or {}
    side = data.get('side')
    run = data.get('run')
    if side not in ('a', 'b') or run not in ('run1', 'run2'):
        return jsonify({"success": False, "message": "side/run ungültig"}), 400
    if not matchup.get(f"{side}_id"):
        return jsonify({"success": False, "message": "Diese Seite ist (noch) nicht besetzt"}), 409

    matchup[side][run] = {
        "time": _to_float(data.get('time')),
        "faults": _to_int(data.get('faults'), 0),
        "refusals": _to_int(data.get('refusals'), 0),
        "dis": bool(data.get('dis')),
    }
    ko_cup.recompute(final)
    _save_data(EVENTS_FILE, events)

    _emit('ko_update', {"event_id": event_id, "final_id": final_id,
                        "matchup_id": matchup_id})
    return jsonify({
        "success": True,
        "matchup": _matchup_json(final, matchup, ""),
        "final_status": ko_cup.bracket_status(final),
    })


@ko_cup_bp.get('/ring/<event_id>')
def ko_ring(event_id):
    """Bedienseite für EINEN Ring-PC: nimmt TIMY-Zeiten vom lokalen Ring-Server
    entgegen und schreibt sie ins korrekte Duell auf dem Hauptserver.
    ?ring=N (Default 1). ?ring_url= überschreibt die Ring-Server-Adresse."""
    events, event = _get_event(event_id)
    if not event:
        abort(404)
    _ensure_ko_cup(event)
    _save_data(EVENTS_FILE, events)
    ring_no = _to_int(request.args.get('ring'), 1) or 1
    return render_template(
        'ko_cup_ring.html',
        event=event,
        ring_no=ring_no,
        ring_url_override=request.args.get('ring_url', ''),
    )
