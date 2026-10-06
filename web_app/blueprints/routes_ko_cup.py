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
                   url_for, flash, abort)

from utils import _load_data, _save_data
import ko_cup

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

    _save_data(EVENTS_FILE, events)
    return redirect(url_for('ko_cup_bp.ko_config', event_id=event_id))


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
    return render_template(
        'ko_cup_print.html',
        event=event,
        final=final,
        participants=participants,
        source_labels=SOURCE_LABELS,
        status=ko_cup.bracket_status(final),
        bracket=_bracket_view(final),
        results=_results_view(final),
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
