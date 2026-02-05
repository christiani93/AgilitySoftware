"""Helpers for print-order planning.

Pure-Python utilities that can be imported without Flask.
"""
from __future__ import annotations

from typing import Dict, Iterable, List

from web_app.utils import _get_concrete_run_list, get_category_sort_key

NON_RUN_TYPES = {
    "Pause",
    "Umbau",
    "Briefing",
    "Vorbereitung",
    "Grossring",
}


def _startnummer_key(entry: Dict) -> int:
    value = entry.get("Startnummer")
    try:
        return int(value)
    except (TypeError, ValueError):
        return 9999


def _copy_run_with_sorted_entries(run: Dict) -> Dict:
    run_copy = dict(run)
    entries = run_copy.get("entries") or []
    run_copy["entries"] = sorted(entries, key=_startnummer_key)
    return run_copy


def _fallback_run_sort_key(run: Dict) -> tuple:
    return (
        run.get("assigned_ring") or "",
        run.get("laufart") or "",
        get_category_sort_key(run.get("kategorie", "")),
        str(run.get("klasse") or ""),
        run.get("name") or "",
        run.get("id") or "",
    )


def get_ordered_runs_for_print(event: Dict) -> List[Dict]:
    """Return runs in print order based on the concrete schedule.

    Filters non-run blocks (Pause/Umbau/Briefing/etc.) and sorts entries by start number.
    Falls back to event.runs ordering when schedule/run_order is incomplete.
    """
    try:
        concrete_runs = _get_concrete_run_list(event)
    except Exception:
        concrete_runs = []

    ordered_runs = [
        run for run in concrete_runs
        if run.get("laufart") not in NON_RUN_TYPES
    ]

    if not ordered_runs:
        fallback_runs = list(event.get("runs", []) or [])
        ordered_runs = sorted(fallback_runs, key=_fallback_run_sort_key)

    return [_copy_run_with_sorted_entries(run) for run in ordered_runs]


def group_runs_by_timeplan_sections(ordered_runs: Iterable[Dict]) -> List[Dict]:
    """Group consecutive runs into sections, preserving order."""
    sections: List[Dict] = []
    for run in ordered_runs:
        title = run.get("name") or run.get("laufart") or "Lauf"
        if not sections or sections[-1]["title"] != title:
            sections.append({"title": title, "runs": [run]})
        else:
            sections[-1]["runs"].append(run)
    return sections


def _block_matches_run(block: Dict, run: Dict) -> bool:
    if block.get("laufart") and block.get("laufart") != run.get("laufart"):
        return False
    block_kat = block.get("kategorie")
    if block_kat and block_kat != "Alle" and block_kat != run.get("kategorie"):
        return False
    block_klasse = block.get("klasse")
    if block_klasse and str(block_klasse) != "Alle" and str(block_klasse) != str(run.get("klasse")):
        return False
    return True


def _collect_participants_for_block(event: Dict, block: Dict) -> List[Dict]:
    participants: List[Dict] = []
    for run in event.get("runs", []):
        if _block_matches_run(block, run):
            participants.extend(run.get("entries", []))
    return participants


def build_briefing_sessions(event: Dict, group_size: int = 50) -> List[Dict]:
    """Build briefing sessions based on run_order blocks.

    Each session starts with a briefing block and includes all blocks until the next briefing.
    Participants are deduplicated by license number and split into groups of the given size.
    """
    run_order = event.get("run_order", []) or []
    if not run_order:
        participants = []
        for run in event.get("runs", []) or []:
            participants.extend(run.get("entries", []))
        participants_by_license = {
            p.get("Lizenznummer"): p
            for p in participants
            if p.get("Startnummer")
        }
        sorted_participants = sorted(participants_by_license.values(), key=_startnummer_key)
        groups = []
        for group_index, offset in enumerate(range(0, len(sorted_participants), group_size), start=1):
            group_entries = sorted_participants[offset:offset + group_size]
            if not group_entries:
                continue
            groups.append({
                "group_index": group_index,
                "start_nr_von": group_entries[0].get("Startnummer"),
                "start_nr_bis": group_entries[-1].get("Startnummer"),
                "participants": group_entries,
            })
        return [{"title": "Begehung 1", "groups": groups}]

    briefing_indices = [
        i for i, block in enumerate(run_order)
        if block.get("laufart") == "Briefing"
    ]

    session_starts = briefing_indices or [0]
    sessions: List[Dict] = []

    for index, start_index in enumerate(session_starts):
        start_block = run_order[start_index] if briefing_indices else None
        end_index = session_starts[index + 1] if index + 1 < len(session_starts) else len(run_order)
        session_scope = run_order[start_index + 1:end_index] if briefing_indices else run_order

        participants_in_session: List[Dict] = []
        for block in session_scope:
            if block.get("laufart") in NON_RUN_TYPES:
                continue
            participants_in_session.extend(_collect_participants_for_block(event, block))

        participants_by_license = {
            p.get("Lizenznummer"): p
            for p in participants_in_session
            if p.get("Startnummer")
        }
        sorted_participants = sorted(participants_by_license.values(), key=_startnummer_key)
        groups = []
        for group_index, offset in enumerate(range(0, len(sorted_participants), group_size), start=1):
            group_entries = sorted_participants[offset:offset + group_size]
            if not group_entries:
                continue
            groups.append({
                "group_index": group_index,
                "start_nr_von": group_entries[0].get("Startnummer"),
                "start_nr_bis": group_entries[-1].get("Startnummer"),
                "participants": group_entries,
            })

        title = None
        if isinstance(start_block, dict):
            title = start_block.get("label")
        sessions.append({
            "title": title or f"Begehung {index + 1}",
            "groups": groups,
        })

    return sessions
