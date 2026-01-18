import copy
import datetime
import uuid
from typing import Dict, List, Tuple

CATEGORY_ORDER_ASC = ["small", "medium", "intermediate", "large"]
CATEGORY_ORDER_DESC = list(reversed(CATEGORY_ORDER_ASC))
CLASS_ORDER_ASC = ["1", "2", "3"]
CLASS_ORDER_DESC = list(reversed(CLASS_ORDER_ASC))

DEFAULT_START_TIME_SECONDS = {
    "agility": {
        "small": {"1": 65, "2": 65, "3": 65},
        "medium": {"1": 65, "2": 65, "3": 65},
        "intermediate": {"1": 65, "2": 65, "3": 65},
        "large": {"1": 65, "2": 65, "3": 65},
    },
    "jumping": {
        "small": {"1": 60, "2": 60, "3": 60},
        "medium": {"1": 60, "2": 60, "3": 60},
        "intermediate": {"1": 60, "2": 60, "3": 60},
        "large": {"1": 60, "2": 60, "3": 60},
    },
    "other": {
        "small": {"1": 65, "2": 65, "3": 65},
        "medium": {"1": 65, "2": 65, "3": 65},
        "intermediate": {"1": 65, "2": 65, "3": 65},
        "large": {"1": 65, "2": 65, "3": 65},
    },
}

DEFAULT_SCHEDULE_PLANNING = {
    "changeover_seconds": 1200,
    "briefing_minutes_per_50_participants": 8,
    "briefing_blocks_size_participants": 50,
    "single_block_prep_pause_seconds": 300,
    "mixed_class_time_mode": "per_class_participants",
    "rank_announcement_default_seconds": 300,
}


def normalize_size(size_value: str) -> str:
    return (size_value or "").strip().lower()


def normalize_class(cls: str) -> str:
    return str(cls).strip()


def upgrade_settings(settings: Dict) -> Dict:
    settings = copy.deepcopy(settings or {})
    planning = settings.setdefault("schedule_planning", {})
    for key, val in DEFAULT_SCHEDULE_PLANNING.items():
        planning.setdefault(key, val)

    matrix = settings.setdefault("start_time_seconds", {})
    for run_type, size_map in DEFAULT_START_TIME_SECONDS.items():
        matrix.setdefault(run_type, {})
        for size_key, class_map in size_map.items():
            matrix[run_type].setdefault(size_key, {})
            for cls_key, seconds in class_map.items():
                matrix[run_type][size_key].setdefault(cls_key, seconds)
    return settings


def _ordered_sizes(direction: str) -> List[str]:
    if (direction or "").lower() == "desc":
        return CATEGORY_ORDER_DESC
    return CATEGORY_ORDER_ASC


def _ordered_classes(direction: str) -> List[str]:
    if (direction or "").lower() == "desc":
        return CLASS_ORDER_DESC
    return CLASS_ORDER_ASC


def expand_size_class_groups(size_category: str, classes: List[str], primary_sort: Dict, secondary_sort: Dict,
                             size_categories: List[str] = None) -> List[Tuple[str, str]]:
    if size_categories:
        target_sizes = [normalize_size(s) for s in size_categories if normalize_size(s)]
    else:
        target_sizes = CATEGORY_ORDER_ASC if normalize_size(size_category) == "all" else [normalize_size(size_category)]
    class_values = [normalize_class(c) for c in (classes or [])] or CLASS_ORDER_ASC

    size_order = target_sizes
    class_order = class_values

    if (primary_sort or {}).get("field") == "category":
        desired_order = _ordered_sizes((primary_sort or {}).get("direction", "asc"))
        size_order = [s for s in desired_order if s in target_sizes]
    if (secondary_sort or {}).get("field") == "class":
        desired_class_order = _ordered_classes((secondary_sort or {}).get("direction", "asc"))
        class_order = [c for c in desired_class_order if c in class_values]
    else:
        class_order = [c for c in CLASS_ORDER_ASC if c in class_values]

    groups = []
    for size in size_order:
        for cls in class_order:
            groups.append((size, cls))
    return groups


def calculate_briefing_and_prep(participants_total: int, planning_settings: Dict) -> Tuple[int, int, int]:
    blocks_size = planning_settings.get("briefing_blocks_size_participants", 50) or 50
    blocks = (participants_total // blocks_size) + 1
    minutes_per_block = planning_settings.get("briefing_minutes_per_50_participants", 8) or 8
    briefing_seconds = blocks * minutes_per_block * 60
    prep_seconds = planning_settings.get("single_block_prep_pause_seconds", 0) if blocks == 1 else 0
    return blocks, briefing_seconds, prep_seconds


def calculate_run_seconds(participants_by_class: Dict[str, int], timing_run_type: str, size_category: str, classes: List[str], settings: Dict) -> int:
    settings = upgrade_settings(settings)
    run_type_key = (timing_run_type or "other").strip().lower() or "other"
    matrix = settings.get("start_time_seconds", DEFAULT_START_TIME_SECONDS)
    time_matrix = matrix.get(run_type_key, matrix.get("other", {}))

    size = normalize_size(size_category)
    class_list = [normalize_class(c) for c in (classes or [])]
    if size == "all":
        sizes = CATEGORY_ORDER_ASC
    else:
        sizes = [size]

    # determine per class seconds map
    per_class_seconds = {}
    for cls in class_list:
        for sz in sizes:
            per_class_seconds.setdefault(cls, time_matrix.get(sz, {}).get(cls, 0))

    mode = settings.get("schedule_planning", {}).get("mixed_class_time_mode", "per_class_participants")
    if mode == "slowest_class_for_all":
        slowest = max(per_class_seconds.values() or [0])
        total_participants = sum(participants_by_class.values())
        return int(total_participants * slowest)

    seconds = 0
    for cls, count in participants_by_class.items():
        seconds += int(count * per_class_seconds.get(str(cls), 0))
    return seconds


def calculate_estimates(participants_by_class: Dict[str, int], block: Dict, settings: Dict) -> Dict:
    settings = upgrade_settings(settings)
    planning = settings.get("schedule_planning", {})
    participants_total = sum(participants_by_class.values())
    changeover_seconds = planning.get("changeover_seconds", 0)
    _, briefing_seconds, prep_pause_seconds = calculate_briefing_and_prep(participants_total, planning)
    run_seconds = calculate_run_seconds(participants_by_class, block.get("timing_run_type"), block.get("size_category"), block.get("classes", []), settings)
    total_seconds = changeover_seconds + briefing_seconds + prep_pause_seconds + run_seconds
    return {
        "participants_total": participants_total,
        "changeover_seconds": changeover_seconds,
        "briefing_seconds": briefing_seconds,
        "prep_pause_seconds": prep_pause_seconds,
        "run_seconds": run_seconds,
        "total_seconds": total_seconds,
    }


def ensure_schedule_root(event_id: str, num_rings: int, start_times: Dict[str, str], existing_schedule: Dict = None) -> Dict:
    schedule = copy.deepcopy(existing_schedule or {})
    schedule.setdefault("schedule_version", 1)
    schedule.setdefault("event_id", event_id)
    schedule.setdefault("rings", {})
    schedule.setdefault("meta", {})
    rings = schedule["rings"]
    for ring_idx in range(1, (num_rings or 1) + 1):
        ring_key = str(ring_idx)
        ring_obj = rings.setdefault(ring_key, {})
        ring_obj.setdefault("start_time", start_times.get(f"ring_{ring_idx}", "07:30"))
        ring_obj.setdefault("blocks", [])
    schedule["meta"].setdefault("last_updated", datetime.datetime.utcnow().isoformat())
    schedule["meta"].setdefault("updated_by", "system")
    return schedule


def generate_block_id() -> str:
    return f"blk_{uuid.uuid4().hex[:8]}"


def collect_participants_by_class(event_runs, block):
    counts = {}
    for run in event_runs or []:
        if not isinstance(run, dict):
            continue
        if block.get("type") != "run":
            continue
        if not _match_run_to_block(run, block):
            continue
        klasse = str(run.get("klasse"))
        counts[klasse] = counts.get(klasse, 0) + len(run.get("entries", []))
    return counts


def _match_run_to_block(run_item, block):
    laufart = normalize_size(run_item.get("laufart"))
    block_laufart = (block.get("timing_run_type") or "").strip().lower()
    if block_laufart and block_laufart != "other" and laufart != block_laufart:
        return False

    category = normalize_size(run_item.get("kategorie"))
    size_categories = [normalize_size(s) for s in (block.get("size_categories") or []) if normalize_size(s)]
    if size_categories:
        if category not in size_categories:
            return False
    else:
        size_cat = (block.get("size_category") or "").lower()
        if size_cat not in ("", "all") and category != size_cat:
            return False

    klasse = str(run_item.get("klasse"))
    if block.get("classes"):
        if str(klasse) not in [str(c) for c in block.get("classes", [])]:
            return False
    return True


def generate_run_title(block: Dict) -> str:
    run_format = (block.get("run_format") or "").strip().lower()
    run_type = (block.get("timing_run_type") or "").strip().lower()
    size_category = normalize_size(block.get("size_category"))
    classes = [normalize_class(c) for c in (block.get("classes") or [])]
    sort_primary = (block.get("sort") or {}).get("primary", {})

    run_type_label = {
        "agility": "Agility",
        "jumping": "Jumping",
    }.get(run_type, "Other")

    prefix = "Open " if run_format == "open" else ""
    class_part = "+".join(classes) if classes else ""

    category_label = None
    if size_category and size_category != "all":
        category_label = size_category.capitalize()
    elif (sort_primary or {}).get("field") == "category":
        direction = (sort_primary or {}).get("direction", "asc").lower()
        category_label = "Aufsteigend" if direction == "asc" else "Absteigend"

    parts = [prefix + run_type_label]
    if class_part:
        parts.append(class_part)
    if category_label:
        parts.append(category_label)
    elif size_category == "all":
        parts.append("Alle")
    return " ".join([p for p in parts if p]).strip()


def ensure_run_titles(schedule: Dict) -> Dict:
    schedule = schedule or {}
    rings = schedule.get("rings") or {}
    for ring in rings.values():
        for block in ring.get("blocks") or []:
            if block.get("type") != "run":
                continue
            title = (block.get("title") or "").strip()
            if not title:
                block["title"] = generate_run_title(block)
    return schedule


def _apply_rounding(dt_obj: datetime.datetime, minutes: int) -> datetime.datetime:
    discard = datetime.timedelta(minutes=dt_obj.minute % minutes, seconds=dt_obj.second, microseconds=dt_obj.microsecond)
    dt_obj -= discard
    if discard >= datetime.timedelta(minutes=minutes / 2):
        dt_obj += datetime.timedelta(minutes=minutes)
    return dt_obj


def _compute_timeline_for_ring(ring_id: str, ring_data: Dict, settings: Dict, event_runs, event_date: str, round_to_minutes=None):
    planning = settings.get("schedule_planning", {})
    start_time_str = ring_data.get("start_time", "07:30")
    try:
        current_time = datetime.datetime.strptime(f"{event_date} {start_time_str}", "%Y-%m-%d %H:%M")
    except Exception:
        current_time = datetime.datetime.now().replace(hour=7, minute=30, second=0, microsecond=0)

    timeline_items = []

    def add_segment(segment_type: str, duration_seconds: int, label: str, block: Dict, num_starters: int = 0):
        nonlocal current_time
        start_time = current_time
        end_time = current_time + datetime.timedelta(seconds=duration_seconds)
        if round_to_minutes:
            start_time = _apply_rounding(start_time, round_to_minutes)
            end_time = _apply_rounding(end_time, round_to_minutes)
        item = {
            "block": block,
            "segment_type": segment_type,
            "label": label,
            "start_time": start_time.strftime("%H:%M"),
            "end_time": end_time.strftime("%H:%M"),
            "duration": duration_seconds / 60 if duration_seconds else 0,
            "num_starters": num_starters,
        }
        timeline_items.append(item)
        current_time = end_time

    for block in ring_data.get("blocks") or []:
        block_type = block.get("type")
        if block_type == "run":
            participants_by_class = collect_participants_by_class(event_runs, block)
            block["estimated"] = calculate_estimates(participants_by_class, block, settings)
            est = block.get("estimated") or {}
            add_segment("changeover", est.get("changeover_seconds", planning.get("changeover_seconds", 0)), "Umbau", block)
            add_segment("briefing", est.get("briefing_seconds", 0), "Briefing", block)
            prep_seconds = est.get("prep_pause_seconds", 0)
            if prep_seconds:
                add_segment("prep_pause", prep_seconds, "Prep-Pause", block)
            add_segment("run", est.get("run_seconds", 0), "Lauf", block, num_starters=est.get("participants_total", 0))
        elif block_type == "rank_announcement":
            duration_seconds = block.get("duration_seconds") or planning.get("rank_announcement_default_seconds", 300)
            add_segment("rank_announcement", duration_seconds, block.get("title") or "Rangverkündigung", block)
        else:
            duration_seconds = block.get("duration_seconds", 0)
            add_segment(block_type or "other", duration_seconds, block.get("title") or block_type or "Block", block)

    return timeline_items


def compute_computed_timeline(schedule: Dict, event_runs=None, settings=None, start_times_by_ring=None, event_date=None, round_to_minutes=None):
    settings = upgrade_settings(settings or {})
    event_date = event_date or datetime.datetime.now().strftime("%Y-%m-%d")
    schedule = copy.deepcopy(schedule or {})
    rings = schedule.get("rings") or {}

    # apply start time fallback
    for ring_key, fallback in (start_times_by_ring or {}).items():
        key = str(ring_key).replace("ring_", "")
        if key in rings and fallback:
            rings[key].setdefault("start_time", fallback)

    timeline_by_ring = {}
    for ring_id in sorted(rings.keys(), key=lambda x: int(x) if str(x).isdigit() else str(x)):
        ring_data = rings.get(ring_id, {})
        timeline_by_ring[str(ring_id)] = _compute_timeline_for_ring(str(ring_id), ring_data, settings, event_runs or [], event_date, round_to_minutes)
    return timeline_by_ring
