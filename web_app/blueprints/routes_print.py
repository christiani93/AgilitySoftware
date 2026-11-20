# blueprints/routes_print.py
from flask import Blueprint, render_template, render_template_string, abort, request, redirect, url_for, flash, Response, jsonify
from flask_babel import gettext as _
from datetime import datetime
import csv
import io
from utils import (_load_data, _save_data, _calculate_run_results, _load_settings,
                   _calculate_timelines, get_category_sort_key, get_run_award_sort_key,
                   resolve_judge_id, resolve_judge_name,
                   get_event_logo_data_uris, _starts_at_end)
from planner.print_order import get_ordered_runs_for_print
from planner.print_schedule_order import (
    build_schedule_print_sections,
    build_schedule_steward_sections,
)
from planner.briefing_groups import (
    apply_group_summaries,
    build_briefing_sessions,
    build_briefing_sessions_from_timeline,
    collect_participants_for_session,
    dedup_preserve_order,
    get_sort_settings_from_run_blocks,
    is_briefing_block,
    session_title_from_run_blocks,
    sort_participants,
    split_into_groups,
)

from ioc_codes import extract_country_code, is_valid_ioc_code

print_bp = Blueprint('print_bp', __name__, template_folder='../templates')


def _safe_timelines(event):
    """Berechnet timelines_by_ring mit denselben Fallbacks wie print_schedule."""
    try:
        timelines_by_ring = _calculate_timelines(event, round_to_minutes=5)
    except Exception:
        timelines_by_ring = None
    if not timelines_by_ring:
        fallback_event = dict(event)
        fallback_event.pop('schedule', None)
        try:
            timelines_by_ring = _calculate_timelines(fallback_event, round_to_minutes=5)
        except Exception:
            timelines_by_ring = None
    if not timelines_by_ring:
        num_rings = event.get('num_rings') or 1
        timelines_by_ring = {str(ring): [] for ring in range(1, num_rings + 1)}
    return timelines_by_ring


@print_bp.route('/print/<event_id>')
def print_index(event_id):
    """Übersichtsseite für Vorbereitungsdrucksachen."""
    event = next((e for e in _load_data('events.json') if e.get('id') == event_id), None)
    if not event: abort(404)
    return render_template('print/index.html', event=event)


@print_bp.route('/print/all/<event_id>')
def print_all(event_id):
    """Sammeldruck aller Vorbereitungsdrucksachen in einem Dokument (ein Druckauftrag),
    gegliedert in drei Bündel mit Titelseiten:
      1. Teilnehmerinfo (Alle Ringe): Zeitplan + Startlisten
      2. Einweiser (pro Ring): Ring-Zeitplan + Einweiserliste nach Ringzeitplan
      3. Ringbüro (pro Ring): Ring-Zeitplan + Ringschreiberliste nach Ringzeitplan
    """
    event = next((e for e in _load_data('events.json') if e.get('id') == event_id), None)
    if not event: abort(404)

    # Auswahl, welche Bündel gedruckt werden (Checkboxen auf der Übersichtsseite).
    # Ohne ``parts``-Parameter (z.B. direkter Aufruf der URL) alle drei drucken –
    # abwärtskompatibel zum bisherigen Verhalten.
    parts = request.args.getlist('parts')
    if parts:
        show_teilnehmer = 'teilnehmer' in parts
        show_einweiser  = 'einweiser' in parts
        show_ringbuero  = 'ringbuero' in parts
    else:
        show_teilnehmer = show_einweiser = show_ringbuero = True

    judges = _load_data('judges.json')
    judges_map = {j['id']: f"{j.get('firstname', '')} {j.get('lastname', '')}".strip() for j in judges}
    logos = get_event_logo_data_uris(event)

    timelines_by_ring = _safe_timelines(event)
    ring_keys = sorted(timelines_by_ring.keys(), key=lambda x: int(x) if str(x).isdigit() else str(x))

    # Bündel 1: 1 Satz Startlisten pro Kategorie/Klasse, laufunspezifisch
    startlist_groups = _build_participant_startlist_groups(event)

    # Bündel 2: Einweiserlisten als Master-Tabelle (1 pro Kategorie/Klasse, alle
    # zugehörigen Läufe als Spalten), pro Ring gefiltert
    # Bündel 3: Ringschreiberlisten nach Ringzeitplan, pro Ring gruppiert
    scribe_sections = _enrich_sections_rasse_verein(build_schedule_print_sections(event))
    for section in scribe_sections:
        first_run = (section.get("runs") or [{}])[0]
        section["judge_name"] = resolve_judge_name(event, first_run, judges, section.get("block"))

    einweiser_by_ring = {
        rk: {
            "timeline": timelines_by_ring.get(rk, []),
            "sections": _build_master_steward_groups(event, judges, ring_key=rk),
        }
        for rk in ring_keys
    }
    ringbuero_by_ring = {
        rk: {
            "timeline": timelines_by_ring.get(rk, []),
            "sections": [s for s in scribe_sections if str(s.get("ring")) == str(rk)],
        }
        for rk in ring_keys
    }

    now_str = datetime.now().strftime('%d.%m.%Y %H:%M')
    return render_template(
        'print/all.html',
        event=event,
        judges_map=judges_map,
        event_logo_data=logos['event'],
        club_logo_data=logos['club'],
        timelines_by_ring=timelines_by_ring,
        ring_keys=ring_keys,
        startlist_groups=startlist_groups,
        einweiser_by_ring=einweiser_by_ring,
        ringbuero_by_ring=ringbuero_by_ring,
        show_teilnehmer=show_teilnehmer,
        show_einweiser=show_einweiser,
        show_ringbuero=show_ringbuero,
        now_str=now_str,
    )

def _get_enriched_participants(event):
    """Hilfsfunktion, um Teilnehmerdaten mit Kategorie und Klasse anzureichern."""
    all_entries = [entry for run in event.get('runs', []) for entry in run.get('entries', []) if entry.get('Startnummer')]
    unique_participants_dict = {v['Lizenznummer']: v for v in all_entries}
    
    dog_map = {d['Lizenznummer']: d for d in _load_data('dogs.json')}

    participants_with_data = []
    for lic, entry in unique_participants_dict.items():
        dog_info = dog_map.get(lic, {})
        entry.update({
            'Kategorie': dog_info.get('Kategorie', 'N/A'),
            'Klasse': str(dog_info.get('Klasse', 'N/A'))
        })
        participants_with_data.append(entry)
    
    return participants_with_data

@print_bp.route('/print/schedule/<event_id>')
def print_schedule(event_id):
    """Druckansicht für den Zeitplan."""
    event = next((e for e in _load_data('events.json') if e.get('id') == event_id), None)
    if not event: abort(404)
    timelines_by_ring = _safe_timelines(event)
    judges_map = {j['id']: f"{j.get('firstname', '')} {j.get('lastname', '')}" for j in _load_data('judges.json')}
    logos = get_event_logo_data_uris(event)
    return render_template('print/schedule.html', event=event, timelines_by_ring=timelines_by_ring, judges_map=judges_map,
                           event_logo_data=logos['event'], club_logo_data=logos['club'])

@print_bp.route('/print/briefing_groups')
@print_bp.route('/print/briefing_groups/<event_id>')
def print_briefing_groups(event_id=None):
    """Druckansicht für die Begehungsgruppen, neu strukturiert pro Begehung."""
    events = _load_data('events.json')
    if event_id is None:
        event = events[0] if events else None
    else:
        event = next((e for e in events if e.get('id') == event_id), None)
    if not event:
        abort(404)

    settings = _load_settings()
    briefing_settings = settings.get('briefing') or {}
    group_size = briefing_settings.get('group_size', 50)
    group_count = briefing_settings.get('group_count')
    show_participants_table = briefing_settings.get('show_participants_table', False)

    try:
        timelines_by_ring = _calculate_timelines(event, round_to_minutes=5)
    except Exception:
        timelines_by_ring = None
    if not timelines_by_ring:
        fallback_event = dict(event)
        fallback_event.pop('schedule', None)
        try:
            timelines_by_ring = _calculate_timelines(fallback_event, round_to_minutes=5)
        except Exception:
            timelines_by_ring = None
    if not timelines_by_ring:
        num_rings = event.get('num_rings') or 1
        timelines_by_ring = {str(ring): [] for ring in range(1, num_rings + 1)}

    schedule = event.get('schedule') or {}
    schedule_blocks_count = 0
    briefing_blocks_count = 0
    dogs_map = {d['Lizenznummer']: d for d in _load_data('dogs.json')}
    sessions_by_ring = []
    for ring_key in sorted(timelines_by_ring.keys(), key=lambda x: int(x) if str(x).isdigit() else str(x)):
        timeline_items = timelines_by_ring.get(ring_key) or []
        schedule_blocks_count += len(timeline_items)
        briefing_blocks_count += sum(1 for item in timeline_items if is_briefing_block(item))
        sessions = build_briefing_sessions_from_timeline(timeline_items)
        ring_sessions = []
        for index, session in enumerate(sessions, start=1):
            run_blocks = session.get("run_blocks", [])
            sort_settings, raw_sort_block = get_sort_settings_from_run_blocks(run_blocks)
            participants = collect_participants_for_session(session, event)
            for entry in participants:
                dog_info = dogs_map.get(entry.get('Lizenznummer'), {})
                entry.setdefault('Kategorie', dog_info.get('Kategorie'))
                entry.setdefault('Klasse', dog_info.get('Klasse'))
            participants = dedup_preserve_order(participants)
            participants_sorted = sort_participants(participants, sort_settings)
            groups = split_into_groups(participants_sorted, group_size, group_count)
            apply_group_summaries(groups)
            group_sizes = [len(group.get("participants", []) or []) for group in groups]
            group_sizes_label = "/".join(str(size) for size in group_sizes) if group_sizes else "—"
            session_title = session_title_from_run_blocks(run_blocks)
            ring_sessions.append({
                "title": session_title or session.get("title") or f"Briefing {index}",
                "session_index": index,
                "participant_count": len(participants_sorted),
                "group_count": len(groups),
                "group_sizes_label": group_sizes_label,
                "groups": groups,
                "sort_settings": sort_settings,
                "raw_sort_block": {
                    "type": raw_sort_block.get("type"),
                    "segment_type": raw_sort_block.get("segment_type"),
                    "laufart": raw_sort_block.get("laufart"),
                    "title": raw_sort_block.get("title"),
                    "label": raw_sort_block.get("label"),
                    "sort": raw_sort_block.get("sort"),
                    "primary_sort_field": raw_sort_block.get("primary_sort_field"),
                    "primary_sort_dir": raw_sort_block.get("primary_sort_dir"),
                    "secondary_sort_field": raw_sort_block.get("secondary_sort_field"),
                    "secondary_sort_dir": raw_sort_block.get("secondary_sort_dir"),
                    "sort_primary_field": raw_sort_block.get("sort_primary_field"),
                    "sort_primary_dir": raw_sort_block.get("sort_primary_dir"),
                    "sort_secondary_field": raw_sort_block.get("sort_secondary_field"),
                    "sort_secondary_dir": raw_sort_block.get("sort_secondary_dir"),
                },
            })
        sessions_by_ring.append({
            "ring": ring_key,
            "sessions": ring_sessions,
        })

    sessions_count = sum(len(ring_data.get('sessions', [])) for ring_data in sessions_by_ring)
    logos = get_event_logo_data_uris(event)
    return render_template(
        'print/briefing_groups.html',
        event=event,
        sessions_by_ring=sessions_by_ring,
        schedule=schedule,
        schedule_blocks_count=schedule_blocks_count,
        briefing_blocks_count=briefing_blocks_count,
        sessions_count=sessions_count,
        debug_enabled=False,
        show_participants_table=show_participants_table,
        event_logo_data=logos['event'],
        club_logo_data=logos['club'],
    )

def _enrich_entry_rasse_verein(entry, dogs_map, handlers_map, clubs_map):
    """Reichert einen einzelnen Entry um Rasse (aus dogs.json) und Vereinsname
    (handlers.json → clubs.json) an. Fehlende Werte bleiben leer (z.B. Rasse
    nicht erfasst)."""
    dog = dogs_map.get(entry.get('Lizenznummer'), {})
    if not entry.get('Rasse'):
        entry['Rasse'] = dog.get('Rasse', '')
    handler = handlers_map.get(dog.get('Hundefuehrer_ID'), {})
    vn = str(handler.get('Vereinsnummer', '') or '').strip()
    verein = clubs_map.get(vn, '')
    if not verein and vn and not vn.isdigit():
        # Ausland/Gastverein: club_name ist Freitext (keine CH-Vereinsnummer)
        # → Rohwert anzeigen, analog Portal-club_display_name.
        verein = vn
    entry['Verein'] = verein
    # Ausland-Kennzeichnung: FOREIGN-Lizenz (Format "AAA-12345", nicht rein
    # numerisch). Nur Daten-Flags setzen; die Beschriftung übernimmt das
    # Template (Übersetzung gehört nicht in die Datenaufbereitung).
    lic = str(entry.get('Lizenznummer', '') or '').strip()
    if lic and not lic.isdigit():
        entry['is_foreign'] = True
        entry['foreign_cc'] = lic.split('-', 1)[0] if '-' in lic else ''
    return entry


def _enrich_entries_rasse_verein(ordered_runs):
    """Reichert die Entries der Läufe um Rasse und Vereinsname an, damit die
    Listen der SportyDog-Vorlage entsprechen."""
    dogs_map = {d['Lizenznummer']: d for d in _load_data('dogs.json')}
    handlers_map = {h['id']: h for h in _load_data('handlers.json')}
    clubs_map = {str(c.get('nummer')): c.get('name', '') for c in _load_data('clubs.json')}
    for run in ordered_runs:
        for entry in run.get('entries', []):
            _enrich_entry_rasse_verein(entry, dogs_map, handlers_map, clubs_map)
    return ordered_runs


def _enrich_sections_rasse_verein(sections):
    """Reichert die Teilnehmer der Zeitplan-Sektionen um Rasse/Verein und die
    Ausland-Flags (is_foreign/foreign_cc) an – analog _enrich_entries_rasse_verein
    für Lauf-Entries."""
    dogs_map = {d['Lizenznummer']: d for d in _load_data('dogs.json')}
    handlers_map = {h['id']: h for h in _load_data('handlers.json')}
    clubs_map = {str(c.get('nummer')): c.get('name', '') for c in _load_data('clubs.json')}
    for section in sections:
        for entry in section.get('participants', []):
            _enrich_entry_rasse_verein(entry, dogs_map, handlers_map, clubs_map)
    return sections


def _enrich_participants_rasse_verein(participants):
    """Reichert eine flache Teilnehmerliste um Rasse/Verein und die Ausland-Flags
    (is_foreign/foreign_cc) an – für Einweiserlisten, die auf
    _get_enriched_participants statt auf Lauf-Entries basieren."""
    dogs_map = {d['Lizenznummer']: d for d in _load_data('dogs.json')}
    handlers_map = {h['id']: h for h in _load_data('handlers.json')}
    clubs_map = {str(c.get('nummer')): c.get('name', '') for c in _load_data('clubs.json')}
    for p in participants:
        _enrich_entry_rasse_verein(p, dogs_map, handlers_map, clubs_map)
    return participants


def _build_participant_startlist_groups(event):
    """Baut 1 Startliste pro Kategorie/Klasse, unabhängig vom einzelnen Lauf
    (laufunspezifisch) – ein Satz Startlisten statt einer Liste je Lauf."""
    participants = _get_enriched_participants(event)
    dogs_map = {d['Lizenznummer']: d for d in _load_data('dogs.json')}
    handlers_map = {h['id']: h for h in _load_data('handlers.json')}
    clubs_map = {str(c.get('nummer')): c.get('name', '') for c in _load_data('clubs.json')}
    for p in participants:
        _enrich_entry_rasse_verein(p, dogs_map, handlers_map, clubs_map)

    grouped = {}
    for p in participants:
        cat, cls = p.get('Kategorie', 'N/A'), str(p.get('Klasse', 'N/A'))
        grouped.setdefault(cat, {}).setdefault(cls, []).append(p)

    groups = []
    for cat in sorted(grouped.keys(), key=get_category_sort_key):
        for cls in sorted(grouped[cat].keys()):
            participants_sorted = sorted(grouped[cat][cls], key=lambda p: (_starts_at_end(p), int(p.get('Startnummer', 9999))))
            groups.append({'kategorie': cat, 'klasse': cls, 'participants': participants_sorted})
    return groups


def _build_master_steward_groups(event, judges, ring_key=None):
    """Baut die Einweiser-Gruppen als Master-Tabelle: 1 Tabelle pro Kategorie/
    Klasse mit allen zugehörigen Läufen als Spalten (wie print_master_steward_list),
    statt einer separaten Tabelle pro einzelnem Zeitplan-Block/Lauf. Optional auf
    einen Ring gefiltert (über run.assigned_ring)."""
    participants = _enrich_participants_rasse_verein(_get_enriched_participants(event))
    grouped_participants = {}
    for p in participants:
        cat, cls = p.get('Kategorie', 'N/A'), str(p.get('Klasse', 'N/A'))
        grouped_participants.setdefault(cat, {}).setdefault(cls, []).append(p)

    ordered_runs = get_ordered_runs_for_print(event)
    # Zeitplan-Position je Lauf (ordered_runs ist bereits in Laufreihenfolge) →
    # erlaubt es, die Einweiser-Gruppen am Ende nach Zeitplan statt nach fixer
    # Kategorie-Reihenfolge zu sortieren (Wunsch print/all).
    run_pos = {r.get('id'): i for i, r in enumerate(ordered_runs)}
    groups = []
    for cat in sorted(grouped_participants.keys(), key=get_category_sort_key):
        for cls in sorted(grouped_participants[cat].keys()):
            participants_in_group = grouped_participants[cat][cls]
            runs_for_group = [r for r in ordered_runs if r.get('kategorie') == cat and (str(r.get('klasse')) == cls or r.get('klasse') == '')]
            if ring_key is not None:
                runs_for_group = [r for r in runs_for_group if str(r.get('assigned_ring')) == f"ring_{ring_key}"]
                if not runs_for_group:
                    continue
            for run in runs_for_group:
                run['judge_display'] = resolve_judge_name(event, run, judges)
            participant_run_map = {p['Lizenznummer']: {r['id']: False for r in runs_for_group} for p in participants_in_group}
            for run in runs_for_group:
                for entry in run.get('entries', []):
                    if entry['Lizenznummer'] in participant_run_map:
                        participant_run_map[entry['Lizenznummer']][run['id']] = True
            participants_sorted = sorted(participants_in_group, key=lambda p: (_starts_at_end(p), int(p.get('Startnummer', 9999))))
            groups.append({
                'ring': ring_key,
                'title': f"{_('Kategorie')}: {cat} - {_('Klasse')}: {cls}",
                'runs': runs_for_group,
                'participants': participants_sorted,
                'run_map': participant_run_map,
                '_sched_pos': min((run_pos.get(r.get('id'), 10**9) for r in runs_for_group), default=10**9),
            })
    # Nach Zeitplan-Reihenfolge sortieren (früheste zugehörige Lauf-Position).
    groups.sort(key=lambda g: g['_sched_pos'])
    return groups


@print_bp.route('/print/startlists/<event_id>')
def print_startlists(event_id):
    """Offizielle Startliste, sortiert nach Zeitplan-Reihenfolge."""
    event = next((e for e in _load_data('events.json') if e.get('id') == event_id), None)
    if not event: abort(404)
    ordered_runs = _enrich_entries_rasse_verein(get_ordered_runs_for_print(event))
    now_str = datetime.now().strftime('%d.%m.%Y %H:%M')
    logos = get_event_logo_data_uris(event)
    return render_template('print_startlists.html', event=event, ordered_runs=ordered_runs, now_str=now_str,
                           event_logo_data=logos['event'], club_logo_data=logos['club'])


@print_bp.route('/print/startlists_by_schedule/<event_id>')
def print_startlists_by_schedule(event_id):
    """Startliste nach Zeitplan-Reihenfolge."""
    event = next((e for e in _load_data('events.json') if e.get('id') == event_id), None)
    if not event:
        abort(404)
    sections = build_schedule_print_sections(event)
    logos = get_event_logo_data_uris(event)
    return render_template('print/startlists_by_schedule.html', event=event, sections=sections,
                           event_logo_data=logos['event'], club_logo_data=logos['club'])

@print_bp.route('/print/stewardlists/<event_id>')
def print_stewardlists(event_id):
    """Ringschreiber-Listen in Zeitplan-Reihenfolge."""
    event = next((e for e in _load_data('events.json') if e.get('id') == event_id), None)
    if not event: abort(404)
    ordered_runs = _enrich_entries_rasse_verein(get_ordered_runs_for_print(event))
    judges = _load_data('judges.json')
    for run in ordered_runs:
        run["judge_display"] = resolve_judge_name(event, run, judges)
    logos = get_event_logo_data_uris(event)
    return render_template('print/scribe_list.html', event=event, title=_("Ringschreiberlisten"), ordered_runs=ordered_runs, judges=judges,
                           event_logo_data=logos['event'], club_logo_data=logos['club'])


@print_bp.route('/print/stewardlists_by_schedule/<event_id>', endpoint='print_stewardlists_by_schedule_view')
def print_stewardlists_by_schedule_view(event_id):
    """Ringschreiber-Listen nach Zeitplan-Reihenfolge."""
    event = next((e for e in _load_data('events.json') if e.get('id') == event_id), None)
    if not event:
        abort(404)
    judges = _load_data('judges.json')
    sections = _enrich_sections_rasse_verein(build_schedule_print_sections(event))
    for section in sections:
        section["judge_name"] = resolve_judge_name(event, section.get("runs", [{}])[0], judges, section.get("block"))
    logos = get_event_logo_data_uris(event)
    return render_template(
        'print/scribe_list_by_schedule.html',
        event=event,
        title=_("Ringschreiberlisten (nach Zeitplan)"),
        sections=sections,
        judges=judges,
        event_logo_data=logos['event'],
        club_logo_data=logos['club'],
    )

@print_bp.route('/print/master_steward_list/<event_id>')
def print_master_steward_list(event_id):
    """Erstellt eine Master-Einweiserliste: 1 Zeile pro Teilnehmer, 1 Spalte pro Lauf."""
    event = next((e for e in _load_data('events.json') if e.get('id') == event_id), None)
    if not event: abort(404)
    judges = _load_data('judges.json')
    participants, grouped_participants = _enrich_participants_rasse_verein(_get_enriched_participants(event)), {}
    for p in participants:
        cat, cls = p.get('Kategorie', 'N/A'), str(p.get('Klasse', 'N/A'))
        if cat not in grouped_participants: grouped_participants[cat] = {}
        if cls not in grouped_participants[cat]: grouped_participants[cat][cls] = []
        grouped_participants[cat][cls].append(p)
    final_grouped_data, ordered_runs, sorted_cats = {}, get_ordered_runs_for_print(event), sorted(grouped_participants.keys(), key=get_category_sort_key)
    for cat in sorted_cats:
        final_grouped_data[cat] = {}
        for cls, participants_in_group in grouped_participants[cat].items():
            runs_for_group = [r for r in ordered_runs if r.get('kategorie') == cat and str(r.get('klasse')) == cls]
            for run in runs_for_group:
                run['judge_display'] = resolve_judge_name(event, run, judges)
            participant_run_map = {p['Lizenznummer']: {r['id']: False for r in runs_for_group} for p in participants_in_group}
            for run in runs_for_group:
                for entry in run.get('entries', []):
                    if entry['Lizenznummer'] in participant_run_map:
                        participant_run_map[entry['Lizenznummer']][run['id']] = True
            participants_in_group.sort(key=lambda p: (_starts_at_end(p), int(p.get('Startnummer', 9999))))
            final_grouped_data[cat][cls] = {'participants': participants_in_group, 'runs': runs_for_group, 'run_map': participant_run_map}
    logos = get_event_logo_data_uris(event)
    return render_template('print/master_steward_list.html', event=event, final_grouped_data=final_grouped_data,
                           event_logo_data=logos['event'], club_logo_data=logos['club'])


@print_bp.route('/print/master_steward_list_by_schedule/<event_id>')
def print_master_steward_list_by_schedule(event_id):
    """Master-Einweiserliste nach Zeitplan-Reihenfolge."""
    event = next((e for e in _load_data('events.json') if e.get('id') == event_id), None)
    if not event:
        abort(404)
    sections = _enrich_sections_rasse_verein(build_schedule_steward_sections(event))
    logos = get_event_logo_data_uris(event)
    return render_template('print/master_steward_list_by_schedule.html', event=event, sections=sections,
                           event_logo_data=logos['event'], club_logo_data=logos['club'])

@print_bp.route('/print/participant_list/<event_id>')
def print_participant_list(event_id):
    """Alphabetische Teilnehmerliste mit Startnummer."""
    event = next((e for e in _load_data('events.json') if e.get('id') == event_id), None)
    if not event: abort(404)
    all_entries, unique_participants_dict = [entry for run in event.get('runs', []) for entry in run.get('entries', [])], {v['Lizenznummer']: v for v in [entry for run in event.get('runs', []) for entry in run.get('entries', [])]}
    handlers_map, dogs_map, participants_with_data = {h['id']: h for h in _load_data('handlers.json')}, {d['Lizenznummer']: d for d in _load_data('dogs.json')}, []
    for lic, entry in unique_participants_dict.items():
        dog_info = dogs_map.get(lic, {})
        handler_info = handlers_map.get(dog_info.get('Hundefuehrer_ID'), {})
        entry.update({'Kategorie': dog_info.get('Kategorie'), 'Klasse': dog_info.get('Klasse'), 'Hundefuehrer_Nachname': handler_info.get('Nachname', ''), 'Hundefuehrer_Vorname': handler_info.get('Vorname', '')})
        participants_with_data.append(entry)
    sorted_participants = sorted(participants_with_data, key=lambda x: (x.get('Hundefuehrer_Nachname', 'z').lower(), x.get('Hundefuehrer_Vorname', 'z').lower()))
    return render_template('print/participant_list.html', event=event, participants=sorted_participants)

@print_bp.route('/print/fr_formulaire/<event_id>')
def print_fr_formulaire_list(event_id):
    """Liste aller ausländischen Teilnehmer (Lizenz-Präfix, z.B. FRA) mit
    Download-Link fürs ausgefüllte CNEAC-Ergebnisformular.

    Deutsche Starter (DEU/GER) werden hier bewusst ausgeschlossen - CNEAC ist
    ein französisches Formular, für DEU gibt es das separate VDH-Formular
    (print_vdh_formulaire_list)."""
    event = next((e for e in _load_data('events.json') if e.get('id') == event_id), None)
    if not event: abort(404)
    dogs_map = {d['Lizenznummer']: d for d in _load_data('dogs.json')}
    seen = {}
    for run in event.get('runs', []):
        for entry in run.get('entries', []):
            lic = str(entry.get('Lizenznummer') or '')
            prefix = lic.split('-', 1)[0] if '-' in lic else ''
            if not prefix or prefix.isdigit() or prefix.upper() in ('DEU', 'GER') or lic in seen:
                continue
            seen[lic] = {
                'lizenznummer': lic,
                'foreign_cc': prefix,
                'hundename': entry.get('Hundename') or dogs_map.get(lic, {}).get('Hundename', ''),
                'hundefuehrer': entry.get('Hundefuehrer', ''),
                'startnummer': entry.get('Startnummer'),
            }
    foreign_participants = sorted(seen.values(), key=lambda p: (p['foreign_cc'], p['hundefuehrer'] or ''))
    return render_template('print/fr_formulaire_list.html', event=event, participants=foreign_participants)

@print_bp.route('/print/fr_formulaire/<event_id>/<lizenznummer>')
def print_fr_formulaire(event_id, lizenznummer):
    """Füllt das offizielle CNEAC-Ergebnisformular für diesen Teilnehmer aus
    (Overlay auf der Originalvorlage) und liefert es als PDF."""
    event = next((e for e in _load_data('events.json') if e.get('id') == event_id), None)
    if not event: abort(404)
    from forms_fr import generate_fr_result_pdf
    pdf_bytes = generate_fr_result_pdf(event, lizenznummer)
    filename = f"formulaire_resultats_{lizenznummer}.pdf"
    return Response(pdf_bytes, mimetype='application/pdf',
                    headers={'Content-Disposition': f'inline; filename="{filename}"'})

@print_bp.route('/print/vdh_formulaire/<event_id>')
def print_vdh_formulaire_list(event_id):
    """Liste aller deutschen Teilnehmer (Lizenz-Ländercode DEU/GER) mit Link
    zum VDH-Formular "Bestätigung für Auslandsergebnisse"."""
    event = next((e for e in _load_data('events.json') if e.get('id') == event_id), None)
    if not event: abort(404)
    dogs_map = {d['Lizenznummer']: d for d in _load_data('dogs.json')}
    seen = {}
    for run in event.get('runs', []):
        for entry in run.get('entries', []):
            lic = str(entry.get('Lizenznummer') or '')
            prefix = lic.split('-', 1)[0].upper() if '-' in lic else ''
            if prefix not in ('DEU', 'GER') or lic in seen:
                continue
            seen[lic] = {
                'lizenznummer': lic,
                'foreign_cc': prefix,
                'hundename': entry.get('Hundename') or dogs_map.get(lic, {}).get('Hundename', ''),
                'hundefuehrer': entry.get('Hundefuehrer', ''),
                'startnummer': entry.get('Startnummer'),
                'leistungsbuch': dogs_map.get(lic, {}).get('Leistungsbuch', ''),
            }
    participants = sorted(seen.values(), key=lambda p: (p['hundefuehrer'] or ''))
    return render_template('print/vdh_formulaire_list.html', event=event, participants=participants)

@print_bp.route('/print/vdh_formulaire/<event_id>/<lizenznummer>/leistungsbuch', methods=['POST'])
def save_vdh_leistungsbuch(event_id, lizenznummer):
    """Speichert die deutsche VDH-Leistungsbuchnummer (z.B. "K-33333") am Hund.

    Separates Feld von der Schweizer Lizenznummer (= Lookup-Key hier), da es im
    System sonst nirgends erfasst wird. Direkt an dogs.json, event-unabhängig
    (die Nummer gehört zum Hund, nicht zum Event)."""
    dogs = _load_data('dogs.json')
    dog = next((d for d in dogs if str(d.get('Lizenznummer')) == str(lizenznummer)), None)
    if not dog:
        return jsonify(success=False, message="Hund nicht gefunden"), 404
    payload = request.get_json(silent=True) or {}
    dog['Leistungsbuch'] = str(payload.get('leistungsbuch') or '').strip()
    _save_data('dogs.json', dogs)
    return jsonify(success=True, leistungsbuch=dog['Leistungsbuch'])

@print_bp.route('/print/vdh_formulaire/<event_id>/<lizenznummer>')
def print_vdh_formulaire(event_id, lizenznummer):
    """Rendert das VDH-Formular "Bestätigung für Auslandsergebnisse" (ein Bogen
    pro Lauf) für diesen deutschen Teilnehmer als Druckseite."""
    event = next((e for e in _load_data('events.json') if e.get('id') == event_id), None)
    if not event: abort(404)
    from forms_vdh import collect_vdh_sheets, RUN_CODES, GRADE_CODES, CATEGORY_CODES
    header, sheets = collect_vdh_sheets(event, lizenznummer)
    return render_template('print/vdh_formulaire.html', event=event, header=header, sheets=sheets,
                           run_codes=RUN_CODES, grade_codes=GRADE_CODES, category_codes=CATEGORY_CODES)

@print_bp.route('/print/ranking_single/<event_id>/<run_id>')
def print_ranking_single(event_id, run_id):
    """Archiv-Rangliste."""
    run_id = str(run_id)
    settings, event = _load_settings(), next((e for e in _load_data('events.json') if e.get('id') == event_id), None)
    run = next((r for r in event.get('runs', []) if r.get('id') == run_id), None)
    if not event or not run: abort(404)
    results = _calculate_run_results(run, settings)
    judges = _load_data('judges.json')
    judge_display = resolve_judge_name(event, run, judges)
    return render_template('print_ranking_single.html', event=event, run=run, results=results, judges=judges, judge_display=judge_display)

@print_bp.route('/print/select_award_list/<event_id>', methods=['GET', 'POST'])
def select_award_list(event_id):
    """Zeigt die Auswahlseite für die Siegerehrungs-Rangliste an und verarbeitet die Auswahl."""
    event = next((e for e in _load_data('events.json') if e.get('id') == event_id), None)
    if not event: abort(404)
    if request.method == 'POST':
        run_ids = request.form.getlist('run_ids')
        if not run_ids: flash(_("Keine Läufe für die Liste ausgewählt."), "warning"); return redirect(url_for('print_bp.select_award_list', event_id=event_id))
        events = _load_data('events.json')
        event_to_update = next((e for e in events if e.get('id') == event_id), None)
        for run in event_to_update.get('runs', []):
            if run.get('id') in run_ids:
                run['awarded_at'] = datetime.now().isoformat()
        _save_data('events.json', events)
        return redirect(url_for('print_bp.print_award_list', event_id=event_id, run_ids=",".join(run_ids)))
    all_runs = event.get('runs', [])
    available_categories = sorted(list(set(r['kategorie'] for r in all_runs if r.get('kategorie'))), key=get_category_sort_key)
    available_classes = sorted(list(set(str(r['klasse']) for r in all_runs if r.get('klasse'))))
    available_rings = sorted(list(set(r['assigned_ring'] for r in all_runs if r.get('assigned_ring'))))
    return render_template('select_award_list.html', event=event, all_runs=all_runs, available_categories=available_categories, available_classes=available_classes, available_rings=available_rings)

@print_bp.route('/print/award_list/<event_id>')
def print_award_list(event_id):
    """Druckt die eigentliche Siegerehrungsliste für ausgewählte Läufe."""
    run_ids = request.args.get('run_ids', '').split(',')
    settings, event = _load_settings(), next((e for e in _load_data('events.json') if e.get('id') == event_id), None)
    if not event: abort(404)
    award_data, runs_to_print = [], [r for r in event.get('runs', []) if r.get('id') in run_ids]
    runs_to_print.sort(key=get_run_award_sort_key)  # Lauf → Kategorie → Klasse
    judges = _load_data('judges.json')
    for run in runs_to_print:
        results = _calculate_run_results(run, settings)
        award_data.append({
            'name': run.get('name'),
            'full_judge_name': resolve_judge_name(event, run, judges),
            'rankings': results,
        })
    logos = get_event_logo_data_uris(event)
    return render_template('print_award_list.html', event=event, event_name=event.get('Bezeichnung'),
                           award_data=award_data, event_id=event_id,
                           event_logo_data=logos['event'], club_logo_data=logos['club'])

# Laufarten, die an das TKAMO-System gemeldet werden (Agility/Jumping/Open).
_TKAMO_MELDEPFLICHTIGE_LAUFARTEN = ['Agility', 'Jumping', 'Open', 'Open-Agility']

# Qualifikations-Codes, die ein abgeschlossenes (meldbares) Resultat markieren.
# 'N/A' = gestartet/gemeldet, aber noch kein Resultat erfasst (vergessen); 'DNS'
# = nicht gestartet (wird ohnehin nicht gemeldet).
_TKAMO_DONE_QUALIS = {'V0', 'V', 'SG', 'G', 'NB', 'DIS', 'ABR'}


def _tkamo_run_status(run, settings):
    """Vollständigkeits-Status eines Laufs für den TKAMO-Export (SWG-R-12).

    Rückgabe (status, missing):
      'skip'        – nicht meldepflichtige Laufart (kein Resultat-Upload)
      'not_started' – kein Team hat Resultat/DIS → Lauf noch nicht gelaufen
      'incomplete'  – mind. ein Team klassiert/DIS, aber mind. ein gestartetes
                      Team ohne Resultat und ohne DIS/ABR → Export dieser
                      Kategorie/Klasse gemäss Weisung gesperrt
      'complete'    – alle gestarteten Teams haben Resultat oder DIS/ABR
    """
    if run.get('laufart') not in _TKAMO_MELDEPFLICHTIGE_LAUFARTEN:
        return ('skip', 0)
    done = 0
    missing = 0
    for res in _calculate_run_results(run, settings):
        qual = res.get('qualifikation')
        if qual == 'DNS':
            continue  # nicht gestartet – wird ohnehin nicht gemeldet
        if qual in _TKAMO_DONE_QUALIS:
            done += 1
        else:
            missing += 1  # 'N/A' = gestartet, aber kein Resultat erfasst
    if done == 0:
        return ('not_started', missing)
    return ('incomplete', missing) if missing > 0 else ('complete', 0)


# Interstitial-Seite, wenn unvollständige Läufe den Export blockieren (SWG-R-12).
_TKAMO_INCOMPLETE_HTML = """<!doctype html>
<html lang="de"><head><meta charset="utf-8">
<title>TKAMO-Export – unvollständig</title>
<style>
 body{font-family:system-ui,sans-serif;max-width:720px;margin:2rem auto;padding:0 1rem;color:#222}
 .warn{background:#fff3cd;border:1px solid #ffe69c;padding:1rem;border-radius:6px}
 table{border-collapse:collapse;width:100%;margin:1.2rem 0}
 td,th{border:1px solid #ccc;padding:.4rem .6rem;text-align:left}
 th{background:#f5f5f5}
 a.btn{display:inline-block;background:#0d6efd;color:#fff;padding:.55rem 1rem;border-radius:6px;text-decoration:none}
 a.back{margin-left:1rem;color:#555}
</style></head><body>
<h1>TKAMO-Export nicht möglich</h1>
<div class="warn"><p>Folgende Läufe sind <strong>unvollständig</strong>: mindestens ein
gestartetes Team hat weder ein Resultat noch einen DIS/ABR-Vermerk. Gemäss TKAMO-Weisung
(SWG-R-12) dürfen nur vollständige Kategorien/Klassen hochgeladen werden.</p></div>
<table><thead><tr><th>Kategorie</th><th>Klasse</th><th>Lauf</th><th>Fehlende Resultate</th></tr></thead>
<tbody>
{% for r in incomplete %}<tr><td>{{ r.kategorie }}</td><td>{{ r.klasse }}</td><td>{{ r.laufart }}</td><td>{{ r.missing }}</td></tr>
{% endfor %}</tbody></table>
<p>Erfasse für diese Teams ein Resultat oder DIS/ABR – oder exportiere jetzt nur die
bereits vollständigen Läufe:</p>
<p><a class="btn" href="{{ export_url }}">Nur vollständige Läufe exportieren</a></p>
</body></html>"""


def _invalid_ioc_licenses(all_runs, run_statuses, settings):
    """Ausländische Lizenzen mit ungültigem IOC-Ländercode in den zu
    exportierenden (vollständigen) Läufen (SWG-R-10). Dedupliziert nach Lizenz."""
    seen = {}
    for run, (status, _missing) in zip(all_runs, run_statuses):
        if status != 'complete':
            continue
        for res in _calculate_run_results(run, settings):
            if res.get('qualifikation') == 'DNS':
                continue
            raw_lic = str(res.get('Lizenznummer', '') or '').strip()
            if not raw_lic or raw_lic.isdigit():
                continue  # keine ausländische Lizenz (CH = rein numerisch)
            code = extract_country_code(raw_lic)
            if not is_valid_ioc_code(code):
                seen[raw_lic] = {
                    'lizenz': raw_lic,
                    'code': code or '—',
                    'hund': res.get('Hundename', ''),
                    'fuehrer': res.get('Hundefuehrer', ''),
                }
    return list(seen.values())


# Interstitial-Seite, wenn ausländische Lizenzen einen ungültigen IOC-Code tragen.
_TKAMO_IOC_HTML = """<!doctype html>
<html lang="de"><head><meta charset="utf-8">
<title>TKAMO-Export – ungültiger Ländercode</title>
<style>
 body{font-family:system-ui,sans-serif;max-width:720px;margin:2rem auto;padding:0 1rem;color:#222}
 .warn{background:#f8d7da;border:1px solid #f1aeb5;padding:1rem;border-radius:6px}
 table{border-collapse:collapse;width:100%;margin:1.2rem 0}
 td,th{border:1px solid #ccc;padding:.4rem .6rem;text-align:left}
 th{background:#f5f5f5}
 a.btn{display:inline-block;background:#dc3545;color:#fff;padding:.55rem 1rem;border-radius:6px;text-decoration:none}
 code{background:#eee;padding:.1rem .3rem;border-radius:3px}
</style></head><body>
<h1>Ungültiger IOC-Ländercode</h1>
<div class="warn"><p>Folgende ausländische Lizenzen tragen <strong>keinen gültigen
IOC-Ländercode</strong>. Die TKAMO verlangt IOC-Codes (z.&nbsp;B. Deutschland =
<code>GER</code>, nicht <code>DEU</code>). Die fehlende/falsche Kennzeichnung ist
einer der häufigsten Fehler bei der Resultatmeldung (SWG-R-10).</p></div>
<table><thead><tr><th>Lizenz</th><th>Code</th><th>Hund</th><th>Hundeführer</th></tr></thead>
<tbody>
{% for r in invalid %}<tr><td>{{ r.lizenz }}</td><td>{{ r.code }}</td><td>{{ r.hund }}</td><td>{{ r.fuehrer }}</td></tr>
{% endfor %}</tbody></table>
<p>Korrigiere die Ländercodes in den Hundedaten – oder exportiere trotzdem
(nur wenn du sicher bist, dass die Codes stimmen):</p>
<p><a class="btn" href="{{ export_url }}">Trotzdem exportieren</a></p>
</body></html>"""


@print_bp.route('/print/tkamo_export/<event_id>')
def tkamo_export(event_id):
    """Erstellt eine reglementskonforme CSV-Datei für den TKAMO-Upload."""
    event = next((e for e in _load_data('events.json') if e.get('id') == event_id), None)
    if not event: abort(404)

    settings = _load_settings()
    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')
    
    header = ['Turniernummer', 'Lizenznummer', 'Hundename', 'Hundefuehrer', 'Club', 'Kategorie', 'Klasse', 'Rang', 'Laufzeit', 'Geschwindigkeit', 'Fehler', 'Verweigerung', 'Zeitfehler', 'Gesamtfehler', 'Disqualifiziert', 'Lauf', 'Richter', 'Parcourslaenge', 'Geraetezahl', 'Standardzeit', 'Maximalzeit', 'Datum', 'ASMV Rang', 'ASMV Team', 'ASMV Punkte']
    writer.writerow(header)
    
    all_runs = event.get('runs', [])

    # SWG-R-12: Kategorien/Klassen mit vergessenen Resultaten dürfen nicht
    # exportiert werden. Status je Lauf bestimmen; unvollständige Läufe blockieren
    # den Export, bis die Resultate erfasst sind – oder der Veranstalter bewusst
    # nur die bereits vollständigen Läufe exportiert (?only_complete=1).
    run_statuses = [_tkamo_run_status(run, settings) for run in all_runs]
    incomplete = [
        {'kategorie': run.get('kategorie', ''), 'klasse': run.get('klasse', ''),
         'laufart': run.get('laufart', ''), 'missing': missing}
        for run, (status, missing) in zip(all_runs, run_statuses)
        if status == 'incomplete'
    ]
    if incomplete and request.args.get('only_complete') != '1':
        return render_template_string(
            _TKAMO_INCOMPLETE_HTML,
            incomplete=incomplete,
            export_url=url_for('print_bp.tkamo_export', event_id=event_id, only_complete=1),
        )

    # SWG-R-10: Vor dem Export prüfen, dass jede ausländische Lizenz einen
    # gültigen IOC-Ländercode trägt. Override via ?force_ioc=1 (falls die eigene
    # Codeliste unvollständig ist), only_complete bleibt dabei erhalten.
    invalid_ioc = _invalid_ioc_licenses(all_runs, run_statuses, settings)
    if invalid_ioc and request.args.get('force_ioc') != '1':
        export_kwargs = {'event_id': event_id, 'force_ioc': 1}
        if request.args.get('only_complete') == '1':
            export_kwargs['only_complete'] = 1
        return render_template_string(
            _TKAMO_IOC_HTML,
            invalid=invalid_ioc,
            export_url=url_for('print_bp.tkamo_export', **export_kwargs),
        )

    judges = _load_data('judges.json')

    # Lade Hundeführer- und Hundedaten für den Export
    handlers_data = _load_data('handlers.json')
    dogs_map = {d['Lizenznummer']: d for d in _load_data('dogs.json')}
    handler_map = {h['id']: h for h in handlers_data}

    for run, (status, _missing) in zip(all_runs, run_statuses):
        # Nur vollständige Läufe exportieren (SWG-R-12). 'skip'/'not_started'/
        # 'incomplete' werden übersprungen.
        if status != 'complete':
            continue

        results = _calculate_run_results(run, settings)
        
        for res in results:
            if not res.get('result'): continue
                
            # Nicht gestartete Teams (DNS) dürfen gemäss Weisung Resultatmeldung
            # Ziff. 2 nicht in die Resultatdatei (sonst Upload-Rückweisung).
            if res.get('qualifikation') == 'DNS':
                continue

            dog_info = dogs_map.get(res['Lizenznummer'], {})
            handler_info = handler_map.get(dog_info.get('Hundefuehrer_ID'), {})

            # Ausländische Lizenz = nicht rein numerisch (intern "AAA-12345").
            raw_lic = str(res.get('Lizenznummer', '') or '').strip()
            is_foreign = bool(raw_lic) and not raw_lic.isdigit()
            if is_foreign:
                # Weisung Ziff. 3.1: IOC-Ländercode voranstellen OHNE Trenner
                # ("FIN54321"); intern gespeichert als "FIN-54321".
                lizenznummer_col = raw_lic.replace('-', '')
                # Club bei ausländischen Lizenzen: kein Wert (Weisung Ziff. 3.1).
                club_col = ''
            else:
                lizenznummer_col = raw_lic
                club_col = handler_info.get('Vereinsnummer', '')

            # Disqualifikation-Feld gemäss Reglement (leer oder Kürzel)
            disq_value = res.get('qualifikation', '') if res.get('qualifikation') in ['DIS', 'ABR'] else ''

            # Bei DIS/ABR sind Rang, Laufzeit, Geschwindigkeit und sämtliche
            # Fehlerspalten gemäss Weisung Resultatmeldung Ziff. 3.1 "Kein Wert"
            # (leer). Die intern nur zur Sortierung genutzten Sentinel-Werte
            # (zeit_total=999.99, fehler_total=999 …) dürfen NICHT exportiert
            # werden – sonst weist der TKAMO-Upload die Datei zurück.
            if disq_value:
                rang_col = ''
                laufzeit_col = ''
                geschwindigkeit_col = ''
                fehler_col = ''
                verweigerung_col = ''
                zeitfehler_col = ''
                gesamtfehler_col = ''
            else:
                rang_col = res.get('platz', '')
                laufzeit_col = f"{res.get('zeit_total', 0):.2f}".replace('.',',')
                geschwindigkeit_col = f"{(float(run['laufdaten'].get('parcours_laenge', 1)) / res.get('zeit_total', 1)):.2f}".replace('.',',') if res.get('zeit_total') else ''
                fehler_col = res.get('fehler_parcours_anzahl', 0) * 5
                verweigerung_col = res.get('verweigerung_parcours_anzahl', 0) * 5
                zeitfehler_col = f"{res.get('fehler_zeit', 0):.2f}".replace('.',',')
                gesamtfehler_col = f"{res.get('fehler_total', 0):.2f}".replace('.',',')

            row = [
                event.get('Turniernummer', ''),
                lizenznummer_col,
                res.get('Hundename', ''),
                res.get('Hundefuehrer', ''),
                club_col,
                run.get('kategorie', ''),
                run.get('klasse', ''),
                rang_col,
                laufzeit_col,
                geschwindigkeit_col,
                fehler_col,
                verweigerung_col,
                zeitfehler_col,
                gesamtfehler_col,
                disq_value,
                run.get('laufart', ''),
                resolve_judge_id(event, run),
                run.get('laufdaten',{}).get('parcours_laenge', ''),
                run.get('laufdaten',{}).get('anzahl_hindernisse', ''),
                run.get('laufdaten',{}).get('standardzeit_sct_berechnet', ''),
                run.get('laufdaten',{}).get('maximalzeit_mct_berechnet', ''),
                datetime.strptime(event.get('Datum'), '%Y-%m-%d').strftime('%d.%m.%Y'),
                # ASMV-Spalten (Stafette): in AgilitySoftware (noch) nicht erfasst,
                # bleiben wie in der offiziellen TKAMO-Vorlage leer.
                '',  # ASMV Rang
                '',  # ASMV Team
                '',  # ASMV Punkte
            ]
            writer.writerow(row)
            
    return Response(
        output.getvalue().encode('utf-8'),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment;filename=tkamo_export_{event_id}.csv"},
    )


# ── Lizenzcheck (TKAMO-Workflow) ──────────────────────────────────────────────

import re as _re

_CAT_LABEL_LC = {"L": "Large", "I": "Intermediate", "M": "Medium", "S": "Small"}
_CAT_FROM_CODE_LC = {"L": "L", "I": "I", "M": "M", "S": "S"}
_CAT_SHORT = {v: k for k, v in _CAT_LABEL_LC.items()}  # Large→L etc.


def _lizenzcheck_participants(event):
    """Liefert eine deduplizierte, sortierte Liste aller Teilnehmer (nach Kat/Klasse),
    analog zum CSV-Export: je Lizenznummer nur einmal, mit Kat/Klasse aus dogs.json."""
    dogs_map     = {d['Lizenznummer']: d for d in _load_data('dogs.json')}
    handlers_map = {h['id']: h for h in _load_data('handlers.json')}

    seen = {}
    for run in event.get('runs', []):
        for entry in run.get('entries', []):
            lic = entry.get('Lizenznummer', '').strip()
            if not lic or lic in seen:
                continue
            dog     = dogs_map.get(lic, {})
            handler = handlers_map.get(dog.get('Hundefuehrer_ID', ''), {})
            seen[lic] = {
                'Lizenznummer': lic,
                'Hundename':    dog.get('Hundename', entry.get('Hundename', '')),
                'Kategorie':    dog.get('Kategorie', entry.get('Kategorie', '')),
                'Klasse':       str(dog.get('Klasse', entry.get('Klasse', ''))),
                'Vorname':      handler.get('Vorname', ''),
                'Nachname':     handler.get('Nachname', ''),
                'Vereinsnummer':handler.get('Vereinsnummer', ''),
                'handler_id':   dog.get('Hundefuehrer_ID', ''),
            }

    # Gleiche Sortierung wie CSV → Zeilen-Mapping stimmt
    return sorted(seen.values(), key=lambda p: (p['Kategorie'], p['Klasse'], p['Lizenznummer']))


@print_bp.route('/print/lizenzcheck/<event_id>', methods=['GET'])
def lizenzcheck_index(event_id):
    """Lizenzcheck-Seite: CSV-Download-Button + Textarea für TKAMO-Ergebnis."""
    event = next((e for e in _load_data('events.json') if e.get('id') == event_id), None)
    if not event: abort(404)
    return render_template('print/lizenzcheck.html', event=event,
                           done=event.get('lizenzcheck_done'),
                           pending=bool(event.get('lizenzcheck_csv_exported_at')),
                           report=None)


@print_bp.route('/print/lizenzcheck_cancel/<event_id>', methods=['POST'])
def lizenzcheck_cancel(event_id):
    """Pending-CSV-Export abbrechen ohne Ergebnis zu importieren."""
    all_events = _load_data('events.json')
    event = next((e for e in all_events if e.get('id') == event_id), None)
    if not event: abort(404)
    event.pop('lizenzcheck_csv_exported_at', None)
    _save_data('events.json', all_events)
    flash(_('Lizenzcheck-Export abgebrochen.'), 'info')
    return redirect(url_for('print_bp.lizenzcheck_index', event_id=event_id))


@print_bp.route('/print/lizenzcheck_csv/<event_id>')
def lizenzcheck_csv(event_id):
    """CSV-Export für TKAMO. ?filter=flagged → nur Lizenzen aus letztem Report."""
    all_events = _load_data('events.json')
    event = next((e for e in all_events if e.get('id') == event_id), None)
    if not event: abort(404)

    only_flagged = request.args.get('filter') == 'flagged'
    flagged_set  = set(event.get('lizenzcheck_flagged_licenses', []))

    participants = _lizenzcheck_participants(event)
    if only_flagged and flagged_set:
        participants = [p for p in participants if p['Lizenznummer'] in flagged_set]

    output = io.StringIO()
    writer = csv.writer(output, delimiter=';', lineterminator='\r\n')
    writer.writerow(['Lizenznummer', 'Kategorie', 'Klasse', 'Hundename',
                     'Vereinsnummer', 'Vorname', 'Nachname'])
    for p in participants:
        writer.writerow([
            p['Lizenznummer'],
            p['Kategorie'],
            p['Klasse'],
            p['Hundename'],
            p['Vereinsnummer'],
            p['Vorname'],
            p['Nachname'],
        ])

    # Pending-Status setzen — zwingt zur Verarbeitung oder zum Abbrechen
    from datetime import datetime as _dt
    event['lizenzcheck_csv_exported_at'] = _dt.utcnow().isoformat()
    if not only_flagged:
        event['lizenzcheck_done'] = False  # Neuer Vollcheck → Status zurücksetzen
    _save_data('events.json', all_events)

    suffix = '_abweichungen' if only_flagged else ''
    return Response(
        output.getvalue().encode('utf-8'),
        mimetype='text/csv; charset=utf-8',
        headers={'Content-Disposition': f'attachment; filename="lizenzcheck{suffix}_{event_id}.csv"'},
    )


@print_bp.route('/print/lizenzcheck/<event_id>', methods=['POST'])
def lizenzcheck_process(event_id):
    """TKAMO-Ergebnistext verarbeiten und Korrekturen automatisch übernehmen."""
    all_events = _load_data('events.json')
    event = next((e for e in all_events if e.get('id') == event_id), None)
    if not event: abort(404)

    report_text = request.form.get('tkamo_result', '').strip()
    if not report_text:
        flash(_('Bitte TKAMO-Ergebnis einfügen.'), 'warning')
        return redirect(url_for('print_bp.lizenzcheck_index', event_id=event_id))

    dogs_all = _load_data('dogs.json')
    dogs_map  = {d['Lizenznummer']: d for d in dogs_all}

    # Zeilennummer → Lizenznummer (identische Reihenfolge wie CSV)
    # Hundename-Zeilen enthalten NIE eine Lizenznummer — nur Zeile N
    participants   = _lizenzcheck_participants(event)
    row_to_license = {i + 2: p['Lizenznummer'] for i, p in enumerate(participants)}

    name_changes:      list[str] = []
    class_changes:     list[str] = []
    inactive_licenses: list[str] = []
    warnings:          list[str] = []
    flagged_licenses:  set       = set()

    for line in report_text.splitlines():
        line = line.strip()
        if not line:
            continue

        # ── "Verein stimmt nicht überein" → komplett ignorieren ──────────────
        if _re.search(r'Verein stimmt', line, _re.IGNORECASE):
            continue

        # ── Inaktive Lizenz ───────────────────────────────────────────────────
        if _re.search(r'inaktiv|nicht aktiv|gesperrt|inactif|inactive', line, _re.IGNORECASE):
            m_lic = _re.search(r'Lizenz\s+(\S+)', line, _re.IGNORECASE)
            lic = m_lic.group(1).rstrip('.,') if m_lic else '?'
            flagged_licenses.add(lic)
            inactive_licenses.append(f"⛔ Inaktive Lizenz {lic} — nicht startberechtigt!")
            continue

        # ── Warnung (z.B. Oldie) → als Info anzeigen ─────────────────────────
        if line.lower().startswith('warnung'):
            m_lic = _re.search(r'Lizenz\s+(\S+)', line, _re.IGNORECASE)
            lic = m_lic.group(1).rstrip('.,') if m_lic else None
            if lic:
                flagged_licenses.add(lic)
            warnings.append(f"ℹ️ {line}")
            continue

        # ── Falsche Klasse → direkt übernehmen (TKAMO ist autoritativ) ───────
        if 'Klasse im System' in line:
            m_cls = _re.search(
                r'Lizenz\s+(\S+).*?Klasse im System:\s*([SMIL])(\d)',
                line, _re.IGNORECASE
            )
            if m_cls:
                lic           = m_cls.group(1).rstrip('.,')
                sys_cat_short = m_cls.group(2).upper()
                sys_cls       = m_cls.group(3)
                sys_cat       = _CAT_LABEL_LC.get(sys_cat_short, sys_cat_short)

                m_imp   = _re.search(r'Klasse im Import:\s*([SMIL])(\d)', line, _re.IGNORECASE)
                imp_cat = _CAT_LABEL_LC.get(m_imp.group(1).upper(), m_imp.group(1).upper()) if m_imp else sys_cat
                imp_cls = m_imp.group(2) if m_imp else sys_cls

                flagged_licenses.add(lic)
                dog = dogs_map.get(lic)
                if dog:
                    dog['Kategorie'] = sys_cat
                    dog['Klasse']    = sys_cls
                    for run in event.get('runs', []):
                        for entry in run.get('entries', []):
                            if entry.get('Lizenznummer') == lic:
                                entry['Kategorie'] = sys_cat
                                entry['Klasse']    = sys_cls
                    class_changes.append(
                        f"🔄 Klasse: {lic} — {imp_cat} Kl.{imp_cls} → {sys_cat} Kl.{sys_cls}"
                    )
                else:
                    class_changes.append(f"⚠️ Lizenz {lic} nicht im System — Klasse nicht angepasst.")
            continue

        # ── Hundename → immer TKAMO-System-Namen übernehmen ──────────────────
        # Format: "Hundename im File: X / Im System Y"
        # Lizenz ist NICHT in dieser Zeile, nur Zeile N
        if 'Hundename' in line:
            m_name = _re.search(r'Im System\s+(.+)$', line, _re.IGNORECASE)
            if not m_name:
                continue
            system_name = m_name.group(1).strip()

            lic = None
            m_lic = _re.search(r'Lizenz\s+(\S+)', line, _re.IGNORECASE)
            if m_lic:
                lic = m_lic.group(1).rstrip('.,')
            else:
                m_row = _re.search(r'Zeile\s+(\d+)', line, _re.IGNORECASE)
                if m_row:
                    lic = row_to_license.get(int(m_row.group(1)))

            if not lic:
                name_changes.append(f"⚠️ Hundename-Zeile — Zeile nicht gefunden: {line}")
                continue

            flagged_licenses.add(lic)
            dog = dogs_map.get(lic)
            if dog:
                old_name = dog.get('Hundename', '')
                # Immer übernehmen (Gross/Klein, Encoding-Unterschiede)
                dog['Hundename'] = system_name
                for run in event.get('runs', []):
                    for entry in run.get('entries', []):
                        if entry.get('Lizenznummer') == lic:
                            entry['Hundename'] = system_name
                if old_name != system_name:
                    name_changes.append(f"✏️ Hundename: {lic} '{old_name}' → '{system_name}'")
                else:
                    name_changes.append(f"✏️ Hundename: {lic} '{system_name}' (Schreibweise bestätigt)")
            else:
                name_changes.append(f"⚠️ Lizenz {lic} nicht im System — Name nicht angepasst.")

    # Speichern
    _save_data('dogs.json', dogs_all)
    event['lizenzcheck_done']            = True
    event['lizenzcheck_done_at']         = __import__('datetime').datetime.utcnow().isoformat()
    event['lizenzcheck_flagged_licenses'] = list(flagged_licenses)
    event.pop('lizenzcheck_csv_exported_at', None)  # Pending aufheben
    _save_data('events.json', all_events)

    report = {
        'name_changes':      name_changes,
        'class_changes':     class_changes,
        'inactive_licenses': inactive_licenses,
        'warnings':          warnings,
        'report_text':       report_text,
    }
    return render_template('print/lizenzcheck.html', event=event, done=True,
                           pending=False, report=report)
