"""Helpers for building briefing group print data.

Pure-Python utilities that can be imported without Flask.
"""
from __future__ import annotations

from typing import Dict, Iterable, List

from planner import schedule_planner

NON_RUN_LAUFARTS = {"Pause", "Umbau", "Briefing", "Vorbereitung", "Grossring"}


def _startnummer_key(entry: Dict) -> int:
    value = entry.get("Startnummer")
    try:
        return int(value)
    except (TypeError, ValueError):
        return 9999


def _is_briefing_block(block: Dict) -> bool:
    return (block.get("type") or "").lower() == "briefing" or block.get("laufart") == "Briefing"


def _is_run_block(block: Dict) -> bool:
    block_type = (block.get("type") or "").lower()
    if block_type:
        return block_type == "run"
    laufart = block.get("laufart")
    return laufart and laufart not in NON_RUN_LAUFARTS


def build_briefing_sessions(schedule_blocks: Iterable[Dict]) -> List[Dict]:
    """Return ordered briefing sessions based on schedule blocks."""
    sessions: List[Dict] = []
    current = None
    for block in schedule_blocks or []:
        if _is_briefing_block(block):
            current = {
                "briefing_block": block,
                "run_blocks": [],
                "title": block.get("title") or block.get("label") or "Briefing",
            }
            sessions.append(current)
            continue
        if _is_run_block(block) and current is not None:
            current["run_blocks"].append(block)
    return sessions


def _match_run_to_block(run_item: Dict, block: Dict) -> bool:
    if (block.get("type") or "").lower() == "run":
        return schedule_planner._match_run_to_block(run_item, block)

    if block.get("laufart") and block.get("laufart") != run_item.get("laufart"):
        return False
    block_kat = block.get("kategorie")
    if block_kat and block_kat != "Alle" and block_kat != run_item.get("kategorie"):
        return False
    block_klasse = block.get("klasse")
    if block_klasse and str(block_klasse) != "Alle" and str(block_klasse) != str(run_item.get("klasse")):
        return False
    return True


def collect_participants_for_session(session: Dict, event: Dict) -> List[Dict]:
    """Collect unique participants for a session based on its run blocks."""
    participants: Dict[str, Dict] = {}
    runs = event.get("runs", []) or []
    for block in session.get("run_blocks", []) or []:
        for run in runs:
            if not isinstance(run, dict):
                continue
            if _match_run_to_block(run, block):
                for entry in run.get("entries", []) or []:
                    license_no = entry.get("Lizenznummer")
                    if not license_no:
                        continue
                    participants.setdefault(license_no, entry)
    return sorted(participants.values(), key=_startnummer_key)


def split_into_groups(participants: List[Dict], group_size: int) -> List[Dict]:
    """Split participants into groups of the given size."""
    if group_size <= 0:
        group_size = 50
    sorted_participants = sorted(participants, key=_startnummer_key)
    groups: List[Dict] = []
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
    return groups
