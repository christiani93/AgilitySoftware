"""
Team-Challenge – Blueprint für Team-Verwaltung und -Auswertung.

Analog zu routes_skbs_sm.py, aber für das 2er-Team-Format:
  - 4 fixe Läufe (Agility/Jumping × Soft/Expert), Grösse im Lauf gemischt
  - Teams bilden sich aus 2 bereits erfassten Startern derselben Grösse
  - Team-Mitgliedschaft synchronisiert automatisch die Lauf-Entries
    (manage_run_participants eignet sich hier nicht, da dessen Kategorie/
    Klasse-Abgleich gegen den literalen Lauf-Wert prüft, der bei
    Team-Läufen aber "Team"/"Soft"/"Expert" ist statt der echten
    Hunde-Kategorie/-Klasse).

Konzept: `AgilityPortal/KONZEPT_Team-Challenge.md`.
"""
import uuid

from flask import (Blueprint, render_template, request, redirect,
                    url_for, flash, abort, Response)
import csv
import io

from utils import _load_data, _save_data, _load_settings, recalc_and_store, _safe_http_filename
from team_challenge_qualification import (
    calculate_team_challenge_results, group_by_category_and_level,
    LEVELS, RUN_TYPES, CATEGORIES,
)

team_challenge_bp = Blueprint('team_challenge_bp', __name__, template_folder='../templates',
                               url_prefix='/team-challenge')

EVENTS_FILE = 'events.json'
DOGS_FILE = 'dogs.json'
HANDLERS_FILE = 'handlers.json'

VERANSTALTUNGSART = 'Team-Challenge'

# Soft = Grad/Klasse 1+2, Expert = Grad/Klasse 3 (Edelweiss-Reglement 2027)
CLASS_LEVELS_BY_LEVEL = {"soft": ["1", "2"], "expert": ["3"]}
LEVEL_LABELS = {"soft": "Soft (Kl. 1+2)", "expert": "Expert (Kl. 3)"}


def _norm(s):
    return (s or "").replace("﻿", "").strip()


# ── Helfer ────────────────────────────────────────────────────────────────

def _get_event(event_id: str):
    events = _load_data(EVENTS_FILE)
    event = next((e for e in events if e.get('id') == event_id), None)
    return events, event


def _is_team_challenge_event(event: dict) -> bool:
    return event.get('Veranstaltungsart') == VERANSTALTUNGSART


def _is_team_challenge_run(run: dict) -> bool:
    return bool(run.get('is_team_challenge'))


def ensure_team_challenge_runs(event: dict) -> bool:
    """Legt die 4 fixen Team-Challenge-Läufe an, falls sie fehlen (idempotent).
    Returns True wenn event['runs'] verändert wurde (Aufrufer muss speichern)."""
    event.setdefault('runs', [])
    existing = {
        (r.get('team_level'), r.get('laufart'))
        for r in event['runs'] if _is_team_challenge_run(r)
    }
    changed = False
    for level in LEVELS:
        for laufart in RUN_TYPES:
            if (level, laufart) in existing:
                continue
            event['runs'].append({
                "id": str(uuid.uuid4()),
                "name": f"Team-Challenge {LEVEL_LABELS[level]} – {laufart}",
                "laufart": laufart,
                "kategorie": "Team",   # Sentinel: Grösse ist im Lauf gemischt
                "klasse": level.capitalize(),  # "Soft"/"Expert" (manuelle SCT-Eingabe,
                                                # siehe _calculate_run_results-Fallback)
                "is_team_challenge": True,
                "team_level": level,
                "entries": [],
                "laufdaten": {},
            })
            changed = True
    return changed


def _team_runs(event: dict) -> dict:
    """{"soft": {"Agility": run, "Jumping": run}, "expert": {...}}"""
    by_level = {lvl: {} for lvl in LEVELS}
    for run in event.get('runs', []):
        if not _is_team_challenge_run(run):
            continue
        level = run.get('team_level')
        if level in by_level and run.get('laufart') in RUN_TYPES:
            by_level[level][run.get('laufart')] = run
    return by_level


def _all_teams(event: dict) -> list:
    return event.setdefault('teams', [])


def _licenses_in_use(event: dict, exclude_team_id: str | None = None) -> set:
    used = set()
    for t in _all_teams(event):
        if t.get('id') == exclude_team_id:
            continue
        used.add(_norm(t.get('mitglied_agility_lizenz')))
        used.add(_norm(t.get('mitglied_jumping_lizenz')))
    used.discard('')
    return used


def _eligible_dogs(event: dict, kategorie: str, level: str, exclude_team_id=None) -> list:
    """Hunde, die Kategorie + Klassen-Level passen und noch in keinem anderen Team stecken."""
    dogs = [d for d in _load_data(DOGS_FILE) if isinstance(d, dict) and d.get('Lizenznummer')]
    handler_map = {h['id']: h for h in _load_data(HANDLERS_FILE) if isinstance(h, dict) and h.get('id')}
    allowed_classes = CLASS_LEVELS_BY_LEVEL.get(level, [])
    used = _licenses_in_use(event, exclude_team_id)

    result = []
    for d in dogs:
        if _norm(d.get('Kategorie')) != _norm(kategorie):
            continue
        if str(d.get('Klasse')) not in allowed_classes:
            continue
        lic = _norm(d.get('Lizenznummer'))
        if lic in used:
            continue
        h = handler_map.get(d.get('Hundefuehrer_ID'))
        handler_name = f"{h.get('Vorname', '')} {h.get('Nachname', '')}".strip() if h else ""
        result.append({
            "license": lic,
            "dog_name": d.get('Hundename', ''),
            "handler_name": handler_name,
            "label": f"{handler_name} mit {d.get('Hundename', '')} ({lic})".strip(),
        })
    return sorted(result, key=lambda x: x['label'].lower())


def _dog_and_handler(license_no: str):
    dogs = _load_data(DOGS_FILE)
    handler_map = {h['id']: h for h in _load_data(HANDLERS_FILE) if isinstance(h, dict) and h.get('id')}
    dog = next((d for d in dogs if _norm(d.get('Lizenznummer')) == _norm(license_no)), None)
    if not dog:
        return None, None
    return dog, handler_map.get(dog.get('Hundefuehrer_ID'))


def _remove_member_entry(run: dict, license_no: str) -> None:
    if not run or not license_no:
        return
    lic = _norm(license_no)
    run['entries'] = [e for e in run.get('entries', []) if _norm(e.get('Lizenznummer')) != lic]


def _add_member_entry(run: dict, license_no: str) -> None:
    if not run or not license_no:
        return
    lic = _norm(license_no)
    if any(_norm(e.get('Lizenznummer')) == lic for e in run.get('entries', [])):
        return
    dog, handler = _dog_and_handler(lic)
    run.setdefault('entries', []).append({
        "Lizenznummer": lic,
        "Hundename": (dog or {}).get('Hundename', ''),
        "Hundefuehrer": f"{(handler or {}).get('Vorname', '')} {(handler or {}).get('Nachname', '')}".strip(),
    })


def _sync_team_into_runs(event: dict, team: dict, old_team: dict | None) -> None:
    """Entfernt veraltete Entries (falls Mitglied/Rolle geändert) und fügt die
    aktuellen Team-Mitglieder in die passenden Läufe (level × Rolle) ein."""
    runs = _team_runs(event)
    level_runs = runs.get(team.get('level'), {})
    agility_run = level_runs.get('Agility')
    jumping_run = level_runs.get('Jumping')

    if old_team:
        old_level_runs = runs.get(old_team.get('level'), {})
        old_agi = old_level_runs.get('Agility')
        old_jump = old_level_runs.get('Jumping')
        if old_agi and _norm(old_team.get('mitglied_agility_lizenz')) != _norm(team.get('mitglied_agility_lizenz')):
            _remove_member_entry(old_agi, old_team.get('mitglied_agility_lizenz'))
        if old_jump and _norm(old_team.get('mitglied_jumping_lizenz')) != _norm(team.get('mitglied_jumping_lizenz')):
            _remove_member_entry(old_jump, old_team.get('mitglied_jumping_lizenz'))
        # Level gewechselt -> aus den alten Läufen ganz entfernen
        if old_team.get('level') != team.get('level'):
            _remove_member_entry(old_agi, old_team.get('mitglied_agility_lizenz'))
            _remove_member_entry(old_jump, old_team.get('mitglied_jumping_lizenz'))

    _add_member_entry(agility_run, team.get('mitglied_agility_lizenz'))
    _add_member_entry(jumping_run, team.get('mitglied_jumping_lizenz'))


def _remove_team_from_runs(event: dict, team: dict) -> None:
    runs = _team_runs(event).get(team.get('level'), {})
    _remove_member_entry(runs.get('Agility'), team.get('mitglied_agility_lizenz'))
    _remove_member_entry(runs.get('Jumping'), team.get('mitglied_jumping_lizenz'))


# ── Routen ────────────────────────────────────────────────────────────────

@team_challenge_bp.get('/dashboard/<event_id>')
def team_challenge_dashboard(event_id):
    events, event = _get_event(event_id)
    if not event:
        abort(404)

    settings = _load_settings()
    for run in event.get('runs', []):
        if _is_team_challenge_run(run):
            recalc_and_store(run, settings)
    _save_data(EVENTS_FILE, events)

    results = calculate_team_challenge_results(event)
    grouped = group_by_category_and_level(results)
    # Feste Reihenfolge für die 8 Kacheln: Grösse × Level
    ordered_groups = [
        (kat, lvl) for kat in CATEGORIES for lvl in LEVELS
        if (kat, lvl) in grouped
    ]

    return render_template(
        'team_challenge_dashboard.html',
        event=event,
        grouped=grouped,
        ordered_groups=ordered_groups,
        level_labels=LEVEL_LABELS,
        teams_count=len(_all_teams(event)),
    )


@team_challenge_bp.route('/config/<event_id>', methods=['GET', 'POST'])
def team_challenge_config(event_id):
    events, event = _get_event(event_id)
    if not event:
        abort(404)

    changed = ensure_team_challenge_runs(event)
    teams = _all_teams(event)

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'add_team':
            kategorie = request.form.get('kategorie', '').strip()
            level = request.form.get('level', '').strip()
            agi_lic = _norm(request.form.get('mitglied_agility_lizenz'))
            jump_lic = _norm(request.form.get('mitglied_jumping_lizenz'))
            name = request.form.get('name', '').strip()

            error = _validate_team(event, kategorie, level, agi_lic, jump_lic, exclude_team_id=None)
            if error:
                flash(error, 'error')
            else:
                team = {
                    "id": str(uuid.uuid4()),
                    "external_id": str(uuid.uuid4()),
                    "name": name,
                    "kategorie": kategorie,
                    "level": level,
                    "mitglied_agility_lizenz": agi_lic,
                    "mitglied_jumping_lizenz": jump_lic,
                    "source": "software",
                }
                teams.append(team)
                _sync_team_into_runs(event, team, old_team=None)
                flash("Team hinzugefügt.", "success")
            _save_data(EVENTS_FILE, events)
            return redirect(url_for('team_challenge_bp.team_challenge_config', event_id=event_id))

        if action == 'delete_team':
            team_id = request.form.get('team_id')
            team = next((t for t in teams if t.get('id') == team_id), None)
            if team:
                _remove_team_from_runs(event, team)
                event['teams'] = [t for t in teams if t.get('id') != team_id]
                flash("Team entfernt.", "info")
            _save_data(EVENTS_FILE, events)
            return redirect(url_for('team_challenge_bp.team_challenge_config', event_id=event_id))

    if changed:
        _save_data(EVENTS_FILE, events)

    # Für jedes bestehende Team + fürs Add-Formular: eligible Hunde pro Grösse+Level
    eligible_by_group = {}
    for kat in CATEGORIES:
        for lvl in LEVELS:
            eligible_by_group[(kat, lvl)] = _eligible_dogs(event, kat, lvl)

    return render_template(
        'team_challenge_config.html',
        event=event,
        teams=teams,
        categories=CATEGORIES,
        levels=LEVELS,
        level_labels=LEVEL_LABELS,
        eligible_by_group=eligible_by_group,
    )


def _validate_team(event, kategorie, level, agi_lic, jump_lic, exclude_team_id=None) -> str | None:
    if kategorie not in CATEGORIES:
        return "Ungültige Grössenkategorie."
    if level not in LEVELS:
        return "Ungültiges Level."
    if not agi_lic or not jump_lic:
        return "Beide Mitglieder (Agility + Jumping) sind Pflicht."
    if agi_lic == jump_lic:
        return "Die beiden Teammitglieder müssen unterschiedliche Hunde sein."

    allowed_classes = CLASS_LEVELS_BY_LEVEL.get(level, [])
    used = _licenses_in_use(event, exclude_team_id)
    for lic, role in ((agi_lic, "Agility"), (jump_lic, "Jumping")):
        if lic in used:
            return f"Lizenz {lic} ist bereits einem anderen Team zugeordnet."
        dog, _h = _dog_and_handler(lic)
        if not dog:
            return f"Hund mit Lizenz {lic} nicht gefunden."
        if _norm(dog.get('Kategorie')) != _norm(kategorie):
            return f"Hund {lic} ({dog.get('Kategorie')}) passt nicht zur Grösse {kategorie}."
        if str(dog.get('Klasse')) not in allowed_classes:
            return f"Hund {lic} (Klasse {dog.get('Klasse')}) passt nicht zu Level {level} ({'/'.join(allowed_classes)})."
    return None


@team_challenge_bp.get('/export-csv/<event_id>')
def team_challenge_export_csv(event_id):
    events, event = _get_event(event_id)
    if not event:
        abort(404)

    settings = _load_settings()
    for run in event.get('runs', []):
        if _is_team_challenge_run(run):
            recalc_and_store(run, settings)

    results = calculate_team_challenge_results(event)
    grouped = group_by_category_and_level(results)

    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')

    for kat in CATEGORIES:
        for lvl in LEVELS:
            rows = grouped.get((kat, lvl))
            if not rows:
                continue
            writer.writerow([f"# {kat} – {LEVEL_LABELS[lvl]}"])
            writer.writerow([
                'Rang', 'Team', 'Agility-Hund', 'Agility-Fehler', 'Agility-Zeit',
                'Jumping-Hund', 'Jumping-Fehler', 'Jumping-Zeit',
                'Gesamt-Fehler', 'Gesamt-Zeit', 'Status',
            ])
            for r in rows:
                writer.writerow([
                    r.get('rank') if r.get('rank') is not None else '',
                    r.get('team_name', ''),
                    r['agility'].get('dog_name', ''),
                    r['agility'].get('fehler_total', ''),
                    r['agility'].get('zeit_total', ''),
                    r['jumping'].get('dog_name', ''),
                    r['jumping'].get('fehler_total', ''),
                    r['jumping'].get('zeit_total', ''),
                    round(r.get('total_faults', 0), 2),
                    round(r.get('total_time', 0), 2),
                    r.get('status', ''),
                ])
            writer.writerow([])

    filename = f"Team-Challenge_{_safe_http_filename(event.get('Bezeichnung') or event_id)}.csv"
    return Response(
        output.getvalue().encode('utf-8-sig'),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'},
    )
