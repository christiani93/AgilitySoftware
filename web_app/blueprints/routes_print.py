# blueprints/routes_print.py
from flask import Blueprint, render_template, abort, request, redirect, url_for, flash, Response
from datetime import datetime
import csv
import io
from utils import (_load_data, _save_data, _calculate_run_results, _load_settings,
                   _calculate_timelines, get_category_sort_key, resolve_judge_id, resolve_judge_name)
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

print_bp = Blueprint('print_bp', __name__, template_folder='../templates')

@print_bp.route('/print/<event_id>')
def print_index(event_id):
    """Übersichtsseite für Vorbereitungsdrucksachen."""
    event = next((e for e in _load_data('events.json') if e.get('id') == event_id), None)
    if not event: abort(404)
    return render_template('print/index.html', event=event)

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
    judges_map = {j['id']: f"{j.get('firstname', '')} {j.get('lastname', '')}" for j in _load_data('judges.json')}
    return render_template('print/schedule.html', event=event, timelines_by_ring=timelines_by_ring, judges_map=judges_map)

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
    )

@print_bp.route('/print/startlists/<event_id>')
def print_startlists(event_id):
    """Offizielle Startliste, sortiert nach Zeitplan-Reihenfolge."""
    event = next((e for e in _load_data('events.json') if e.get('id') == event_id), None)
    if not event: abort(404)
    ordered_runs = get_ordered_runs_for_print(event)
    return render_template('print_startlists.html', event=event, ordered_runs=ordered_runs)


@print_bp.route('/print/startlists_by_schedule/<event_id>')
def print_startlists_by_schedule(event_id):
    """Startliste nach Zeitplan-Reihenfolge."""
    event = next((e for e in _load_data('events.json') if e.get('id') == event_id), None)
    if not event:
        abort(404)
    sections = build_schedule_print_sections(event)
    return render_template('print/startlists_by_schedule.html', event=event, sections=sections)

@print_bp.route('/print/stewardlists/<event_id>')
def print_stewardlists(event_id):
    """Ringschreiber-Listen in Zeitplan-Reihenfolge."""
    event = next((e for e in _load_data('events.json') if e.get('id') == event_id), None)
    if not event: abort(404)
    ordered_runs = get_ordered_runs_for_print(event)
    judges = _load_data('judges.json')
    for run in ordered_runs:
        run["judge_display"] = resolve_judge_name(event, run, judges)
    return render_template('print/scribe_list.html', event=event, title="Ringschreiberlisten", ordered_runs=ordered_runs, judges=judges)


@print_bp.route('/print/stewardlists_by_schedule/<event_id>', endpoint='print_stewardlists_by_schedule_view')
def print_stewardlists_by_schedule_view(event_id):
    """Ringschreiber-Listen nach Zeitplan-Reihenfolge."""
    event = next((e for e in _load_data('events.json') if e.get('id') == event_id), None)
    if not event:
        abort(404)
    judges = _load_data('judges.json')
    sections = build_schedule_print_sections(event)
    for section in sections:
        section["judge_name"] = resolve_judge_name(event, section.get("runs", [{}])[0], judges, section.get("block"))
    return render_template(
        'print/scribe_list_by_schedule.html',
        event=event,
        title="Ringschreiberlisten (nach Zeitplan)",
        sections=sections,
        judges=judges,
    )

@print_bp.route('/print/master_steward_list/<event_id>')
def print_master_steward_list(event_id):
    """Erstellt eine Master-Einweiserliste: 1 Zeile pro Teilnehmer, 1 Spalte pro Lauf."""
    event = next((e for e in _load_data('events.json') if e.get('id') == event_id), None)
    if not event: abort(404)
    participants, grouped_participants = _get_enriched_participants(event), {}
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
            participant_run_map = {p['Lizenznummer']: {r['id']: False for r in runs_for_group} for p in participants_in_group}
            for run in runs_for_group:
                for entry in run.get('entries', []):
                    if entry['Lizenznummer'] in participant_run_map:
                        participant_run_map[entry['Lizenznummer']][run['id']] = True
            participants_in_group.sort(key=lambda p: int(p.get('Startnummer', 9999)))
            final_grouped_data[cat][cls] = {'participants': participants_in_group, 'runs': runs_for_group, 'run_map': participant_run_map}
    return render_template('print/master_steward_list.html', event=event, final_grouped_data=final_grouped_data)


@print_bp.route('/print/master_steward_list_by_schedule/<event_id>')
def print_master_steward_list_by_schedule(event_id):
    """Master-Einweiserliste nach Zeitplan-Reihenfolge."""
    event = next((e for e in _load_data('events.json') if e.get('id') == event_id), None)
    if not event:
        abort(404)
    sections = build_schedule_steward_sections(event)
    return render_template('print/master_steward_list_by_schedule.html', event=event, sections=sections)

@print_bp.route('/print/participant_list/<event_id>')
def print_participant_list(event_id):
    """Alphabetische Teilnehmerliste mit Startnummer."""
    event = next((e for e in _load_data('events.json') if e.get('id') == event_id), None)
    if not event: abort(404)
    all_entries, unique_participants_dict = [entry for run in event.get('runs', []) for entry in run.get('entries', [])], {v['Lizenznummer']: v for v in [entry for run in event.get('runs', []) for entry in run.get('entries', [])]}
    handlers_map, dogs_map, participants_with_data = {h['id']: h for h in _load_data('handlers.json')}, {d['Lizenznummer']: d for d in _load_data('dogs.json')}, []
    for lic, entry in unique_participants_dict.items():
        dog_info, handler_info = dogs_map.get(lic, {}), handlers_map.get(dog_info.get('Hundefuehrer_ID'), {})
        entry.update({'Kategorie': dog_info.get('Kategorie'), 'Klasse': dog_info.get('Klasse'), 'Hundefuehrer_Nachname': handler_info.get('Nachname', ''), 'Hundefuehrer_Vorname': handler_info.get('Vorname', '')})
        participants_with_data.append(entry)
    sorted_participants = sorted(participants_with_data, key=lambda x: (x.get('Hundefuehrer_Nachname', 'z').lower(), x.get('Hundefuehrer_Vorname', 'z').lower()))
    return render_template('print/participant_list.html', event=event, participants=sorted_participants)

@print_bp.route('/print/ranking_single/<event_id>/<uuid:run_id>')
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
        if not run_ids: flash("Keine Läufe für die Liste ausgewählt.", "warning"); return redirect(url_for('print_bp.select_award_list', event_id=event_id))
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
    judges = _load_data('judges.json')
    for run in runs_to_print:
        results = _calculate_run_results(run, settings)
        award_data.append({
            'name': run.get('name'),
            'full_judge_name': resolve_judge_name(event, run, judges),
            'rankings': results,
        })
    return render_template('print_award_list.html', event=event, event_name=event.get('Bezeichnung'), award_data=award_data, event_id=event_id)

@print_bp.route('/print/tkamo_export/<event_id>')
def tkamo_export(event_id):
    """Erstellt eine reglementskonforme CSV-Datei für den TKAMO-Upload."""
    event = next((e for e in _load_data('events.json') if e.get('id') == event_id), None)
    if not event: abort(404)
    
    settings = _load_settings()
    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')
    
    header = ['Turniernummer', 'Lizenznummer', 'Hundename', 'Hundefuehrer', 'Club', 'Kategorie', 'Klasse', 'Rang', 'Laufzeit', 'Geschwindigkeit', 'Fehler', 'Verweigerung', 'Zeitfehler', 'Gesamtfehler', 'Disqualifiziert', 'Lauf', 'Richter', 'Parcourslaenge', 'Geraetezahl', 'Standardzeit', 'Maximalzeit', 'Datum']
    writer.writerow(header)
    
    all_runs = event.get('runs', [])
    judges = _load_data('judges.json')
    
    # Lade Hundeführer- und Hundedaten für den Export
    handlers_data = _load_data('handlers.json')
    dogs_map = {d['Lizenznummer']: d for d in _load_data('dogs.json')}
    handler_map = {h['id']: h for h in handlers_data}

    for run in all_runs:
        if run.get('laufart') not in ['Agility', 'Jumping', 'Open', 'Open-Agility']: continue
            
        results = _calculate_run_results(run, settings)
        
        for res in results:
            if not res.get('result'): continue
                
            dog_info = dogs_map.get(res['Lizenznummer'], {})
            handler_info = handler_map.get(dog_info.get('Hundefuehrer_ID'), {})
            
            # Disqualifikation-Feld gemäss Reglement (leer oder Kürzel)
            disq_value = res.get('qualifikation', '') if res.get('qualifikation') in ['DIS', 'ABR'] else ''
            
            row = [
                event.get('Turniernummer', ''),
                res.get('Lizenznummer', ''),
                res.get('Hundename', ''),
                res.get('Hundefuehrer', ''),
                handler_info.get('Vereinsnummer', ''), # Vereinsnummer des Hundeführers
                run.get('kategorie', ''),
                run.get('klasse', ''),
                res.get('platz', ''),
                f"{res.get('zeit_total', 0):.2f}".replace('.',','),
                f"{(float(run['laufdaten'].get('parcours_laenge', 1)) / res.get('zeit_total', 1)):.2f}".replace('.',',') if res.get('zeit_total') else '',
                res.get('fehler_parcours_anzahl', 0) * 5,
                res.get('verweigerung_parcours_anzahl', 0) * 5,
                f"{res.get('fehler_zeit', 0):.2f}".replace('.',','),
                f"{res.get('fehler_total', 0):.2f}".replace('.',','),
                disq_value,
                run.get('laufart', ''),
                resolve_judge_id(event, run),
                run.get('laufdaten',{}).get('parcours_laenge', ''),
                run.get('laufdaten',{}).get('anzahl_hindernisse', ''),
                run.get('laufdaten',{}).get('standardzeit_sct_berechnet', ''),
                run.get('laufdaten',{}).get('maximalzeit_mct_berechnet', ''),
                datetime.strptime(event.get('Datum'), '%Y-%m-%d').strftime('%d.%m.%Y')
            ]
            writer.writerow(row)
            
    output.seek(0)
    return Response(output, mimetype="text/csv", headers={"Content-Disposition": f"attachment;filename=tkamo_export_{event_id}.csv"})
