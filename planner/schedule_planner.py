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


def expand_size_class_groups(size_category: str, classes: List[str], primary_sort: Dict, secondary_sort: Dict) -> List[Tuple[str, str]]:
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
