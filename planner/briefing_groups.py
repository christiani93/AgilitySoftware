"""Helpers for building briefing group print data.

Pure-Python utilities that can be imported without Flask.
"""
from __future__ import annotations

from typing import Dict, Iterable, List, Tuple

from planner import schedule_planner

NON_RUN_LAUFARTS = {"Pause", "Umbau", "Briefing", "Vorbereitung", "Grossring"}


def _startnummer_key(entry: Dict) -> int:
    value = entry.get("Startnummer")
    try:
        return int(value)
    except (TypeError, ValueError):
        return 9999


def _category_label(category: str) -> str:
    value = (category or "").strip()
    mapping = {
        "Small": "S",
        "Medium": "M",
        "Intermediate": "I",
        "Large": "L",
    }
    return mapping.get(value, value[:1].upper() if value else "")


def _participant_sort_key(entry: Dict) -> Tuple[int]:
    return (_startnummer_key(entry),)


def _normalize_category(value: str) -> str:
    value = (value or "").strip().lower()
    mapping = {
        "small": "small",
        "s": "small",
        "medium": "medium",
        "m": "medium",
        "intermediate": "intermediate",
        "i": "intermediate",
        "large": "large",
        "l": "large",
    }
    return mapping.get(value, value)


def _category_rank(category: str, direction: str) -> int:
    ranks = {"small": 0, "medium": 1, "intermediate": 2, "large": 3}
    value = ranks.get(_normalize_category(category), 99)
    if (direction or "asc").lower() == "desc":
        return -value
    return value


def _class_rank(klasse: str, direction: str) -> int:
    ranks = {"1": 0, "2": 1, "3": 2}
    value = ranks.get(str(klasse), 99)
    if (direction or "asc").lower() == "desc":
        return -value
    return value


def build_participant_sort_key(sort_settings: Dict) -> callable:
    primary = (sort_settings or {}).get("primary") or {}
    secondary = (sort_settings or {}).get("secondary") or {}
    primary_field = (primary.get("field") or "none").lower()
    secondary_field = (secondary.get("field") or "none").lower()
    primary_dir = (primary.get("direction") or "asc").lower()
    secondary_dir = (secondary.get("direction") or "asc").lower()

    def _key(entry: Dict) -> Tuple:
        parts = []
        if primary_field == "category":
            parts.append(_category_rank(entry.get("Kategorie") or entry.get("kategorie"), primary_dir))
        elif primary_field == "class":
            parts.append(_class_rank(entry.get("Klasse") or entry.get("klasse"), primary_dir))

        if secondary_field == "category":
            parts.append(_category_rank(entry.get("Kategorie") or entry.get("kategorie"), secondary_dir))
        elif secondary_field == "class":
            parts.append(_class_rank(entry.get("Klasse") or entry.get("klasse"), secondary_dir))

        if not parts:
            return (_startnummer_key(entry),)
        return tuple(parts + [_startnummer_key(entry)])

    return _key


def _text_matches_briefing(value: str) -> bool:
    lowered = (value or "").lower()
    return any(token in lowered for token in ("brief", "begeh", "walkthrough", "inspection"))


def is_briefing_block(block: Dict) -> bool:
    """Return True if block looks like a briefing block."""
    for key in ("segment_type", "type", "kind", "block_type", "laufart"):
        value = (block.get(key) or "").lower()
        if value in {"briefing", "briefing_time", "begehung", "walkthrough", "inspection"}:
            return True
    for key in ("title", "label", "name"):
        if _text_matches_briefing(block.get(key) or ""):
            return True
    return False


def is_run_block(block: Dict) -> bool:
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
        if is_briefing_block(block):
            current = {
                "briefing_block": block,
                "run_blocks": [],
                "title": block.get("title") or block.get("label") or "Briefing",
            }
            sessions.append(current)
            continue
        if is_run_block(block) and current is not None:
            current["run_blocks"].append(block)
    return sessions


def build_briefing_sessions_from_timeline(timeline_items: Iterable[Dict]) -> List[Dict]:
    """Return ordered briefing sessions based on computed timeline items."""
    sessions: List[Dict] = []
    current = None
    for item in timeline_items or []:
        if is_briefing_block(item):
            current = {
                "briefing_block": item,
                "run_blocks": [],
                "title": item.get("label") or item.get("title") or "Briefing",
            }
            sessions.append(current)
            continue
        if (item.get("segment_type") or "").lower() == "run" and current is not None:
            block = item.get("block") or {}
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


def collect_participants_for_session(session: Dict, event: Dict, sort_settings: Dict | None = None) -> List[Dict]:
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
    if sort_settings:
        return sorted(participants.values(), key=build_participant_sort_key(sort_settings))
    return sorted(participants.values(), key=_participant_sort_key)


def _calculate_group_count(total: int, group_size: int, group_count: int | None) -> int:
    if group_count and group_count > 0:
        return group_count
    if group_size <= 0:
        group_size = 50
    return max(1, (total + group_size - 1) // group_size)


def _even_group_sizes(total: int, group_count: int) -> List[int]:
    base = total // group_count
    rest = total % group_count
    return [(base + 1 if idx < rest else base) for idx in range(group_count)]


def summarize_group_ranges(participants: List[Dict]) -> str:
    return summarize_group_ranges_with_occurrences(participants, {})


def build_group_segments(participants: List[Dict]) -> List[Dict]:
    segments = []
    current = None
    for entry in participants:
        category = entry.get("Kategorie") or entry.get("kategorie") or ""
        klasse = str(entry.get("Klasse") or entry.get("klasse") or "")
        label = f"{_category_label(category)}{klasse}"
        start_nr = entry.get("Startnummer")
        if current is None or current["label"] != label:
            current = {"label": label, "start": start_nr, "end": start_nr}
            segments.append(current)
        else:
            current["end"] = start_nr
    return segments


def summarize_group_ranges_with_occurrences(participants: List[Dict], occurrences: Dict[str, int]) -> str:
    segments = build_group_segments(participants)
    label_counts = {}
    for segment in segments:
        label_counts[segment["label"]] = label_counts.get(segment["label"], 0) + 1

    formatted = []
    for segment in segments:
        start = segment.get("start")
        end = segment.get("end")
        label = segment["label"]
        show_range = label_counts.get(label, 0) > 1 or occurrences.get(label, 0) > 1
        if not show_range and len(segments) == 1:
            formatted.append(label)
            continue
        if show_range:
            if start == end:
                formatted.append(f"{label} {start}")
            else:
                formatted.append(f"{label} {start}–{end}")
        else:
            formatted.append(label)
    return ", ".join(formatted)


def apply_group_summaries(groups: List[Dict]) -> None:
    occurrences: Dict[str, int] = {}
    for group in groups:
        labels = {segment["label"] for segment in build_group_segments(group.get("participants", []))}
        for label in labels:
            occurrences[label] = occurrences.get(label, 0) + 1

    for group in groups:
        participants = group.get("participants", [])
        group["summary"] = summarize_group_ranges_with_occurrences(participants, occurrences)


def session_title_from_run_blocks(run_blocks: List[Dict]) -> str | None:
    if not run_blocks:
        return None
    first = run_blocks[0]
    title = (first.get("title") or "").strip()
    if title:
        return title
    try:
        return schedule_planner.generate_run_title(first)
    except Exception:
        return None


def split_into_groups(participants: List[Dict], group_size: int, group_count: int | None = None) -> List[Dict]:
    """Split participants into evenly sized groups."""
    ordered_participants = list(participants)
    group_count = _calculate_group_count(len(ordered_participants), group_size, group_count)
    sizes = _even_group_sizes(len(ordered_participants), group_count)
    groups: List[Dict] = []
    offset = 0
    for group_index, size in enumerate(sizes, start=1):
        group_entries = ordered_participants[offset:offset + size]
        offset += size
        if not group_entries:
            groups.append({
                "group_index": group_index,
                "start_nr_von": None,
                "start_nr_bis": None,
                "participants": [],
                "summary": "",
            })
            continue
        groups.append({
            "group_index": group_index,
            "start_nr_von": group_entries[0].get("Startnummer"),
            "start_nr_bis": group_entries[-1].get("Startnummer"),
            "participants": group_entries,
            "summary": "",
        })
    return groups
