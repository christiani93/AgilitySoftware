"""Utilities for schedule-based print ordering."""
from __future__ import annotations

from typing import Dict, Iterable, List

from planner import schedule_planner
from planner.briefing_groups import build_participant_sort_key, dedup_preserve_order, sort_participants


def _iter_schedule_blocks(event: Dict) -> Iterable[Dict]:
    schedule = event.get("schedule") or {}
    rings = schedule.get("rings") or {}
    for ring_key in sorted(rings.keys(), key=lambda x: int(x) if str(x).isdigit() else str(x)):
        ring = rings.get(ring_key) or {}
        for block in ring.get("blocks") or []:
            yield ring_key, block


def _block_title(block: Dict) -> str:
    title = (block.get("title") or "").strip()
    if title:
        return title
    return schedule_planner.generate_run_title(block)


def _category_order_label(block: Dict) -> str | None:
    size_category = (block.get("size_category") or "").lower()
    size_categories = block.get("size_categories") or []
    if size_category == "all" or len(size_categories) >= 4:
        direction = ((block.get("sort") or {}).get("primary") or {}).get("direction", "asc")
        if str(direction).lower() == "desc":
            return "L/I/M/S"
        return "S/M/I/L"
    return None


def format_block_title(block: Dict) -> str:
    label = _category_order_label(block)
    title = _block_title(block)
    if label:
        return f"{title} ({label})"
    return title


def _collect_runs_for_block(event: Dict, block: Dict) -> List[Dict]:
    runs = []
    for run in event.get("runs", []) or []:
        if not isinstance(run, dict):
            continue
        if schedule_planner._match_run_to_block(run, block):
            runs.append(run)
    sort_settings = block.get("sort") or {}
    key = build_participant_sort_key(sort_settings)
    runs.sort(key=lambda run: key({
        "Kategorie": run.get("kategorie"),
        "Klasse": run.get("klasse"),
        "Startnummer": 0,
    }))
    return runs


def build_schedule_print_sections(event: Dict) -> List[Dict]:
    sections = []
    for ring_key, block in _iter_schedule_blocks(event):
        if (block.get("type") or "").lower() != "run":
            continue
        runs = _collect_runs_for_block(event, block)
        participants = []
        for run in runs:
            for entry in run.get("entries", []) or []:
                entry.setdefault("Kategorie", run.get("kategorie"))
                entry.setdefault("Klasse", run.get("klasse"))
                participants.append(entry)
        participants_sorted = sort_participants(participants, block.get("sort") or {})
        sections.append({
            "ring": ring_key,
            "block": block,
            "title": format_block_title(block),
            "runs": runs,
            "participants": participants_sorted,
        })
    return sections


def build_schedule_steward_sections(event: Dict) -> List[Dict]:
    sections = []
    for ring_key, block in _iter_schedule_blocks(event):
        if (block.get("type") or "").lower() != "run":
            continue
        runs = _collect_runs_for_block(event, block)
        participants = []
        run_map = {}
        for run in runs:
            for entry in run.get("entries", []) or []:
                entry.setdefault("Kategorie", run.get("kategorie"))
                entry.setdefault("Klasse", run.get("klasse"))
                participants.append(entry)
                license_no = entry.get("Lizenznummer")
                if not license_no:
                    continue
                run_map.setdefault(license_no, {})
                run_map[license_no][run.get("id")] = True
        participants = dedup_preserve_order(participants)
        participants_sorted = sort_participants(participants, block.get("sort") or {})
        sections.append({
            "ring": ring_key,
            "block": block,
            "title": format_block_title(block),
            "runs": runs,
            "participants": participants_sorted,
            "run_map": run_map,
        })
    return sections
