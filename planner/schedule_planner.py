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
    "tunnellauf": {
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
    # Portal-Parity: Blöcke atomar + Verhaltensfelder normieren (idempotent).
    migrate_schedule_to_atomic(schedule)
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

    # Tunnellauf wird pro Kategorie (klassenübergreifend) gelaufen – die Klasse
    # ist dort nicht massgeblich. Der Portal-Zeitplan markiert Tunnellauf-Blöcke
    # mit classes=["1"] (Default class_level=1), der zusammengefasste Software-Lauf
    # hat aber klasse="" (ein Lauf pro Kategorie). Darum beim Tunnellauf NICHT auf
    # die Klasse filtern – Übereinstimmung von Disziplin + Kategorie reicht.
    if block_laufart == "tunnellauf":
        return True
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
        "open": "Open",
        "tunnellauf": "Tunnellauf",
    }.get(run_type, "Other")

    prefix = "Open " if run_format == "open" and run_type != "open" else ""
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

    blocks = ring_data.get("blocks") or []

    def _run_group_key(blk: Dict) -> Tuple:
        return (
            (blk.get("timing_run_type") or "").strip().lower(),
            (blk.get("run_format") or "").strip().lower(),
            tuple(str(c) for c in (blk.get("classes") or [])),
        )

    # Aufeinanderfolgende Run-Blöcke mit gleicher Disziplin + Laufformat + Klasse
    # bilden EINE Gruppe: ein Umbau, ein gemeinsames Briefing, dann die Läufe
    # (eine Kategorie pro Block) in Folge. Das entspricht der Portal-Logik
    # (schedule_utils._split_into_groups). Der Portal-Export liefert einen Block
    # pro (Disziplin, Kategorie, Klasse); ohne Gruppierung entstünde sonst pro
    # Kategorie-Block ein eigener Umbau + Briefing (zu viele Briefings/Umbauten).
    n = len(blocks)
    i = 0
    while i < n:
        block = blocks[i]
        block_type = block.get("type")
        if block_type == "run":
            group = [block]
            key = _run_group_key(block)
            j = i + 1
            while j < n and blocks[j].get("type") == "run" and _run_group_key(blocks[j]) == key:
                group.append(blocks[j])
                j += 1

            # Pro-Block-Schätzung (für Lauf-Dauer/Starter) + Gruppen-Aggregat
            # (für das gemeinsame Briefing + die Umbaupause).
            per_block = []
            group_participants = 0
            for b in group:
                participants_by_class = collect_participants_by_class(event_runs, b)
                b["estimated"] = calculate_estimates(participants_by_class, b, settings)
                est = b.get("estimated") or {}
                group_participants += est.get("participants_total", 0)
                per_block.append((b, est))

            _, briefing_seconds, prep_seconds = calculate_briefing_and_prep(group_participants, planning)
            leader = group[0]
            add_segment("changeover", planning.get("changeover_seconds", 0), "Umbau", leader)
            add_segment("briefing", briefing_seconds, "Briefing", leader)
            if prep_seconds:
                add_segment("prep_pause", prep_seconds, "Prep-Pause", leader)
            for b, est in per_block:
                add_segment("run", est.get("run_seconds", 0), "Lauf", b, num_starters=est.get("participants_total", 0))
            i = j
        elif block_type == "rank_announcement":
            duration_seconds = block.get("duration_seconds") or planning.get("rank_announcement_default_seconds", 300)
            add_segment("rank_announcement", duration_seconds, block.get("title") or "Rangverkündigung", block)
            i += 1
        else:
            duration_seconds = block.get("duration_seconds", 0)
            add_segment(block_type or "other", duration_seconds, block.get("title") or block_type or "Block", block)
            i += 1

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


# =============================================================================
# Portal-Parity-Engine (atomare Blöcke) — Phase 1 des Zeitplan-Moduls-Ersatzes
# =============================================================================
#
# Alles unterhalb ist ein bewusst 1:1 gehaltener Port von
# AgilityPortal/app/blueprints/club/schedule_utils.py + app/services/
# schedule_service.py, angepasst auf das JSON-Event-Modell der Software
# (keine SQLAlchemy-Objekte, sondern dicts; dieselben Konstanten/Formeln).
#
# Kernunterschied zur Engine oberhalb (die bewusst unangetastet bleibt, bis
# Phase 2 Editor+Routen umstellt): ein Block hier ist ATOMAR — genau EIN
# Lauf (eine Disziplin × eine Kategorie × eine Klasse), analog Portal
# ScheduleBlock. Mehrere Kategorien "auf einen Schlag" gibt es hier nicht
# mehr; stattdessen gruppiert `split_into_groups` aufeinanderfolgende Blöcke
# mit gleicher Disziplin+Klasse automatisch zu einer Umbau-/Briefing-Einheit
# — exakt wie Portal `schedule_utils._split_into_groups`. Zusätzlich zur
# reinen Portierung bekommt jeder Block optional ein `run_id`-Feld: zeigt es
# auf eine echte `event['runs']`-ID, wird darüber verknüpft (stabil, keine
# Attribut-Matching-Fragilität); fehlt es (Block ohne passenden Lauf, z.B.
# in der Planungsphase vor dem Erstellen der Läufe), fällt die Suche auf
# Attribut-Matching (Disziplin+Kategorie+Klasse) zurück.
#
# Blockform (dict):
#   {
#     "id": str, "ring": str, "block_type": "run" | "rank_announcement",
#     "discipline": "agility"|"jumping"|"open"|"tunnel",   # nur block_type=="run"
#     "category": "Large"|"Intermediate"|"Medium"|"Small",  # nur block_type=="run"
#     "class_level": 1|2|3,                                  # nur block_type=="run"
#     "run_id": str | None,          # optionale feste Verknüpfung zu event['runs']
#     "title": str | None,
#     "notes": str | None,
#     "sort_index": int,
#     "skip_changeover": bool, "skip_briefing": bool, "force_new_group": bool,
#     "participant_count_override": int | None,
#     "duration_minutes": int | None,   # nur block_type=="rank_announcement"
#     "judge_id": str | None,
#   }

PORTAL_SECONDS_PER_STARTER = {"agility": 65, "jumping": 60, "open": 65, "tunnel": 60, "final": 240}
PORTAL_CHANGEOVER_SECONDS = 1200
PORTAL_BRIEFING_MINUTES_PER_50 = 8
PORTAL_BRIEFING_BLOCK_SIZE = 50
PORTAL_PREP_PAUSE_SECONDS = 300

PORTAL_DISCIPLINE_LABELS = {
    "agility": "Agility", "jumping": "Jumping", "open": "Open", "tunnel": "Tunnellauf",
    "final": "Finale",
}
# SW-Läufe tragen `laufart` als exaktes Literal (siehe exchange_service.py-Kommentar
# "Software matcht auf exakte Literale") — identisch zu PORTAL_DISCIPLINE_LABELS,
# als eigene Konstante nur zur Verdeutlichung der Matching-Richtung.
_DISCIPLINE_TO_LAUFART = dict(PORTAL_DISCIPLINE_LABELS)

PORTAL_CATEGORY_ORDER = ["Large", "Intermediate", "Medium", "Small"]
PORTAL_CATEGORY_SORT = {cat: i for i, cat in enumerate(PORTAL_CATEGORY_ORDER)}

# --- Dual-Read-Accessors ----------------------------------------------------
# Die Parity-Engine liest Blöcke über diese Helfer, damit sie SOWOHL die
# Portal-Keys (block_type/discipline/category/class_level) ALS AUCH die im
# Software-Storage genutzten Keys (type/timing_run_type/size_category/classes)
# versteht. So rechnet sie auf den real gespeicherten (atomaren) Blöcken, ohne
# dass die live-kritischen Verbraucher (die weiterhin die Storage-Keys lesen)
# umgeschrieben werden müssen. Portal-Key-Tests bleiben unverändert grün.
_TIMING_TO_DISCIPLINE = {"tunnellauf": "tunnel"}
_CATEGORY_CANON = {
    "small": "Small", "medium": "Medium", "intermediate": "Intermediate", "large": "Large",
    "s": "Small", "m": "Medium", "i": "Intermediate", "l": "Large",
}


def _timing_to_discipline(timing) -> str:
    t = (timing or "").strip().lower()
    return _TIMING_TO_DISCIPLINE.get(t, t)


def _canon_category(value):
    if not value or str(value).strip().lower() == "all":
        return None
    return _CATEGORY_CANON.get(str(value).strip().lower(), value)


def _blk_type(block: Dict) -> str:
    return block.get("block_type") or block.get("type") or "run"


def _blk_discipline(block: Dict) -> str:
    d = block.get("discipline") or _timing_to_discipline(block.get("timing_run_type"))
    return (d or "").lower()


def _blk_category(block: Dict):
    c = block.get("category")
    if not c:
        c = block.get("size_category")
    return _canon_category(c)


def _blk_class_level(block: Dict):
    cl = block.get("class_level")
    if cl in (None, ""):
        classes = block.get("classes") or []
        cl = classes[0] if classes else None
    return cl


# --- Migration: bestehende (evtl. Multi-Kat/Klasse-)Blöcke -> atomar ---------
# Wandelt gespeicherte Blöcke in atomare um (1 Kategorie × 1 Klasse) und ergänzt
# die Parity-Verhaltensfelder. Storage-Keys (type/timing_run_type/size_category/
# classes) bleiben erhalten -> live-kritische Verbraucher laufen unverändert.
# Idempotent: bereits atomare Blöcke werden nur mit Feldern/sort_index normiert.

def _is_atomic_run_block(block: Dict) -> bool:
    if _blk_type(block) != "run":
        return True
    size_cats = [s for s in (block.get("size_categories") or []) if s]
    classes = [c for c in (block.get("classes") or []) if str(c)]
    sc = (block.get("size_category") or "").strip().lower()
    if block.get("category") is not None:
        single_cat = True
    elif size_cats:
        single_cat = len(size_cats) == 1
    else:
        single_cat = sc not in ("", "all")
    single_cls = (block.get("class_level") is not None) or (len(classes) == 1)
    return single_cat and single_cls


def _expand_block_to_atomic(block: Dict) -> List[Dict]:
    sort = block.get("sort") or {}
    pairs = expand_size_class_groups(
        block.get("size_category"), block.get("classes"),
        sort.get("primary"), sort.get("secondary"),
        block.get("size_categories"))
    out = []
    for size, cls in pairs:
        nb = copy.deepcopy(block)
        nb["id"] = generate_block_id()
        nb["size_category"] = size
        nb["size_categories"] = []
        nb["classes"] = [str(cls)]
        nb.pop("category", None)
        nb.pop("class_level", None)
        nb["title"] = ""
        nb["run_id"] = None
        out.append(nb)
    return out or [block]


def migrate_schedule_to_atomic(schedule: Dict, event_runs: List[Dict] = None) -> Dict:
    """Stellt ein schedule-dict auf atomare Blöcke um + ergänzt Parity-Felder.
    Idempotent. Reindexiert sort_index je Ring (Listenreihenfolge ist
    autoritativ). Optionales event_runs verknüpft run_id stabil (Fallback bleibt
    Attribut-Matching)."""
    if not isinstance(schedule, dict):
        return schedule
    for ring_data in (schedule.get("rings") or {}).values():
        if not isinstance(ring_data, dict):
            continue
        new_blocks = []
        for block in ring_data.get("blocks") or []:
            if not isinstance(block, dict):
                continue
            if _blk_type(block) == "run" and not _is_atomic_run_block(block):
                new_blocks.extend(_expand_block_to_atomic(block))
            else:
                new_blocks.append(block)
        for i, block in enumerate(new_blocks):
            block["sort_index"] = i * 10
            if _blk_type(block) == "run":
                block.setdefault("skip_changeover", False)
                block.setdefault("skip_briefing", False)
                block.setdefault("force_new_group", False)
                block.setdefault("participant_count_override", None)
                block.setdefault("run_id", None)
                if event_runs is not None and block.get("run_id") is None:
                    link_block_to_run(block, event_runs)
        ring_data["blocks"] = new_blocks
    schedule["schedule_version"] = 2
    return schedule


def _portal_round_to_minutes(dt: datetime.datetime, minutes: int) -> datetime.datetime:
    discard = datetime.timedelta(
        minutes=dt.minute % minutes, seconds=dt.second, microseconds=dt.microsecond)
    dt -= discard
    if discard >= datetime.timedelta(minutes=minutes / 2):
        dt += datetime.timedelta(minutes=minutes)
    return dt


def _portal_advance(current: datetime.datetime, seconds: int, round_minutes: int):
    """Gibt (start_str, end_str, new_current) zurück."""
    start = _portal_round_to_minutes(current, round_minutes) if round_minutes else current
    end = start + datetime.timedelta(seconds=seconds)
    if round_minutes:
        end = _portal_round_to_minutes(end, round_minutes)
    return start.strftime("%H:%M"), end.strftime("%H:%M"), end


def _portal_briefing_seconds(participant_count: int) -> int:
    """8 Min pro 50 Starter (wie Portal, +1 Block auch bei 0 Startern)."""
    blocks = (participant_count // PORTAL_BRIEFING_BLOCK_SIZE) + 1
    return blocks * PORTAL_BRIEFING_MINUTES_PER_50 * 60


def _portal_prep_pause_seconds(participant_count: int) -> int:
    """5 Min Preppause nur wenn ein einzelner Briefing-Block reicht (<=50 Starter)."""
    blocks = (participant_count // PORTAL_BRIEFING_BLOCK_SIZE) + 1
    return PORTAL_PREP_PAUSE_SECONDS if blocks == 1 else 0


def _portal_secs_per_starter(discipline: str, run_time_config) -> int:
    cfg = run_time_config or PORTAL_SECONDS_PER_STARTER
    key = (discipline or "agility").lower()
    return cfg.get(key, PORTAL_SECONDS_PER_STARTER.get(key, 65))


def estimate_block(discipline: str, participant_count: int, run_time_config: Dict = None) -> Dict:
    """Geschätzte Dauer EINES atomaren Blocks (inkl. Umbau-Anteil). Portal-Pendant:
    schedule_utils.estimate_block."""
    secs = _portal_secs_per_starter(discipline, run_time_config)
    run_seconds = participant_count * secs
    brief_secs = _portal_briefing_seconds(participant_count)
    prep_secs = _portal_prep_pause_seconds(participant_count)
    total = PORTAL_CHANGEOVER_SECONDS + brief_secs + prep_secs + run_seconds
    return {
        "participants": participant_count,
        "changeover_sec": PORTAL_CHANGEOVER_SECONDS,
        "briefing_sec": brief_secs,
        "prep_pause_sec": prep_secs,
        "run_sec": run_seconds,
        "total_seconds": total,
        "total_min": total // 60,
    }


def auto_title(discipline: str, category: str, class_level) -> str:
    disc = PORTAL_DISCIPLINE_LABELS.get((discipline or "").lower(), discipline or "")
    return f"{disc} {category or ''} Kl. {class_level}".strip()


def link_block_to_run(block: Dict, event_runs: List[Dict]) -> Dict | None:
    """Findet den zu einem Block passenden `event['runs']`-Eintrag (find-only;
    anders als Portal legt die Software hier KEINEN leeren Lauf an — ein Lauf
    entsteht in der Software über den Anmeldungs-/Lauf-Workflow, nicht über den
    Zeitplan-Editor). Setzt bei Treffer `block['run_id']`. Portal-Pendant:
    schedule_service.link_block_to_run (dort find-or-CREATE, da EventRun dort
    ein leichtgewichtiges Metadaten-Objekt ohne eigene Entries ist)."""
    if _blk_type(block) != "run":
        return None
    discipline = _blk_discipline(block)
    laufart = _DISCIPLINE_TO_LAUFART.get(discipline, discipline)
    block_cat = _blk_category(block)
    block_cls = _blk_class_level(block)
    for run in event_runs or []:
        if not isinstance(run, dict):
            continue
        if (run.get("laufart") or "").strip().lower() != laufart.lower():
            continue
        if _canon_category(run.get("kategorie")) != block_cat:
            continue
        if str(run.get("klasse")) != str(block_cls):
            continue
        block["run_id"] = run.get("id")
        return run
    return None


def _find_run_for_block(block: Dict, event_runs: List[Dict]) -> Dict | None:
    """Liest den verknüpften Lauf: zuerst über `run_id` (stabil), sonst per
    Attribut-Matching (Fallback für Blöcke ohne Verknüpfung)."""
    run_id = block.get("run_id")
    if run_id is not None:
        for run in event_runs or []:
            if isinstance(run, dict) and run.get("id") == run_id:
                return run
        # run_id zeigt ins Leere (Lauf gelöscht/umbenannt) → wie unverknüpft behandeln
    return link_block_to_run(dict(block), event_runs)  # Kopie: kein Seiteneffekt beim reinen Lookup


def portal_participant_count(block: Dict, event_runs: List[Dict]) -> int:
    """Teilnehmerzahl für die Zeitplan-Berechnung: manueller Override hat Vorrang
    vor der Zahl aus dem verknüpften Lauf (z.B. Planung vor Anmeldeschluss).
    Portal-Pendant: routes.py._effective_participant_count."""
    override = block.get("participant_count_override")
    if override is not None:
        return int(override)
    run = _find_run_for_block(block, event_runs)
    return len(run.get("entries", [])) if run else 0


def _portal_group_key(block: Dict) -> Tuple:
    """Gruppierschlüssel: gleiche Disziplin + gleiche Klasse = eine Gruppe
    (Kategorie zählt bewusst NICHT mit — genau das lässt mehrere Kategorien
    automatisch zu einer Gruppe verschmelzen). Portal-Pendant: schedule_utils._group_key."""
    return (_blk_discipline(block), _blk_class_level(block) or 0)


def split_into_groups(sorted_blocks: List[Dict]) -> List[Tuple[str, object]]:
    """Teilt eine (bereits nach sort_index sortierte) Blockliste in Gruppen.

    Aufeinanderfolgende "run"-Blöcke mit gleicher Disziplin+Klasse bilden eine
    Gruppe (ein Umbau, ein gemeinsames Briefing). `force_new_group=True`
    erzwingt eine neue Gruppe auch bei gleichem Schlüssel. `rank_announcement`
    und `final` (eigene, fix berechnete Dauer, kein EventRun) unterbrechen
    immer und stehen standalone dazwischen. Portal-Pendant:
    schedule_utils._split_into_groups.

    Rückgabe: Liste von ("run_group", [block,...]) | ("rank", block) | ("final", block).
    """
    groups: List[Tuple[str, object]] = []
    current_grp: List[Dict] = []
    current_key = None

    for block in sorted_blocks:
        bt = _blk_type(block)
        if bt in ("rank_announcement", "final"):
            if current_grp:
                groups.append(("run_group", current_grp))
                current_grp = []
                current_key = None
            groups.append(("rank" if bt == "rank_announcement" else "final", block))
        else:
            key = _portal_group_key(block)
            force_split = bool(block.get("force_new_group")) and bool(current_grp)
            if current_key is not None and (key != current_key or force_split):
                groups.append(("run_group", current_grp))
                current_grp = []
            current_grp.append(block)
            current_key = key

    if current_grp:
        groups.append(("run_group", current_grp))
    return groups


def compute_timeline(blocks_by_ring: Dict[str, List[Dict]], ring_start_times: Dict[str, str],
                     event_date_str: str, event_runs: List[Dict] = None,
                     round_minutes: int = 0, run_time_config: Dict = None) -> Dict[str, List[Dict]]:
    """Timeline für den Zeitplan-Editor (ein Item pro Block). Portal-Pendant:
    schedule_utils.compute_timeline."""
    event_runs = event_runs or []
    timeline: Dict[str, List[Dict]] = {}

    for ring, blocks in blocks_by_ring.items():
        start_str = ring_start_times.get(ring, "08:00")
        try:
            current = datetime.datetime.strptime(f"{event_date_str} {start_str}", "%Y-%m-%d %H:%M")
        except Exception:
            current = datetime.datetime.now().replace(hour=8, minute=0, second=0, microsecond=0)

        items: List[Dict] = []
        groups = split_into_groups(sorted(blocks, key=lambda b: b.get("sort_index", 0)))

        for gtype, content in groups:
            if gtype == "rank":
                t = _portal_round_to_minutes(current, round_minutes) if round_minutes else current
                ts = t.strftime("%H:%M")
                items.append({
                    "block": content, "start_time": ts, "end_time": ts,
                    "participants": 0, "total_min": 0, "changeover_min": 0,
                    "briefing_min": 0, "prep_pause_min": 0, "run_min": 0,
                })
            elif gtype == "final":
                block = content
                count = portal_participant_count(block, event_runs)
                # Final-Block mit gesetzter Disziplin (BCCS Jumping/Agility-Finale) rechnet
                # mit der normalen Disziplin-Zeit; ohne Disziplin (KO/American) gilt 'final'.
                secs = _portal_secs_per_starter(_blk_discipline(block) or "final", run_time_config)
                run_s = max(count * secs, 60)
                s, e, current = _portal_advance(current, run_s, round_minutes)
                items.append({
                    "block": block, "start_time": s, "end_time": e,
                    "participants": count, "total_min": run_s // 60,
                    "changeover_min": 0, "briefing_min": 0, "prep_pause_min": 0,
                    "run_min": run_s // 60,
                })
            else:
                run_group = content
                leader = run_group[0]
                counts = [portal_participant_count(b, event_runs) for b in run_group]
                total_count = sum(counts)

                changeover_s = 0 if leader.get("skip_changeover") else PORTAL_CHANGEOVER_SECONDS
                if leader.get("skip_briefing"):
                    brief_s = prep_s = 0
                else:
                    brief_s = _portal_briefing_seconds(total_count)
                    prep_s = _portal_prep_pause_seconds(total_count)

                co_start = _portal_round_to_minutes(current, round_minutes) if round_minutes else current
                current = co_start + datetime.timedelta(seconds=changeover_s)
                if round_minutes:
                    current = _portal_round_to_minutes(current, round_minutes)

                _bs, _be, current = _portal_advance(current, brief_s, round_minutes)
                if prep_s:
                    _ps, _pe, current = _portal_advance(current, prep_s, round_minutes)

                run_times = {}
                for b, count in zip(run_group, counts):
                    secs = _portal_secs_per_starter(_blk_discipline(b), run_time_config)
                    run_s = max(count * secs, 60)
                    s, e, current = _portal_advance(current, run_s, round_minutes)
                    run_times[b.get("id")] = (s, e)

                first = True
                for b, count in zip(run_group, counts):
                    secs = _portal_secs_per_starter(_blk_discipline(b), run_time_config)
                    run_s = count * secs
                    r_start, r_end = run_times[b.get("id")]
                    items.append({
                        "block": b,
                        "start_time": co_start.strftime("%H:%M") if first else r_start,
                        "end_time": r_end,
                        "participants": count,
                        "changeover_min": changeover_s // 60 if first else 0,
                        "briefing_min": brief_s // 60 if first else 0,
                        "prep_pause_min": prep_s // 60 if first else 0,
                        "run_min": run_s // 60,
                        "total_min": ((changeover_s + brief_s + prep_s if first else 0) + run_s) // 60,
                    })
                    first = False

        timeline[ring] = items
    return timeline


def compute_detailed_segments(blocks_by_ring: Dict[str, List[Dict]], ring_start_times: Dict[str, str],
                               event_date_str: str, event_runs: List[Dict] = None,
                               round_minutes: int = 5, run_time_config: Dict = None) -> Dict[str, List[Dict]]:
    """Detaillierte Segment-Timeline für die Teilnehmer-/Druckansicht (Umbau/
    Briefing/Preppause/Lauf je eigenes Segment). Portal-Pendant:
    schedule_utils.compute_detailed_segments."""
    event_runs = event_runs or []
    segments_by_ring: Dict[str, List[Dict]] = {}

    for ring, blocks in blocks_by_ring.items():
        start_str = ring_start_times.get(ring, "08:00")
        try:
            current = datetime.datetime.strptime(f"{event_date_str} {start_str}", "%Y-%m-%d %H:%M")
        except Exception:
            current = datetime.datetime.now().replace(hour=8, minute=0, second=0, microsecond=0)

        items: List[Dict] = []
        groups = split_into_groups(sorted(blocks, key=lambda b: b.get("sort_index", 0)))
        briefing_item_indices = []

        for gtype, content in groups:
            if gtype == "rank":
                t = _portal_round_to_minutes(current, round_minutes) if round_minutes else current
                ts = t.strftime("%H:%M")
                items.append({
                    "segment": "rank_announcement",
                    "label": content.get("title") or "Rangverkündigung",
                    "block": content, "start_time": ts, "end_time": ts, "participants": 0,
                })
            elif gtype == "final":
                block = content
                count = portal_participant_count(block, event_runs)
                # Final-Block mit gesetzter Disziplin (BCCS Jumping/Agility-Finale) rechnet
                # mit der normalen Disziplin-Zeit; ohne Disziplin (KO/American) gilt 'final'.
                secs = _portal_secs_per_starter(_blk_discipline(block) or "final", run_time_config)
                run_s = max(count * secs, 60)
                s, e, current = _portal_advance(current, run_s, round_minutes)
                items.append({
                    "segment": "final", "label": block.get("title") or "Finale",
                    "block": block, "start_time": s, "end_time": e, "participants": count,
                })
            else:
                run_group = content
                leader = run_group[0]
                counts = [portal_participant_count(b, event_runs) for b in run_group]
                total_count = sum(counts)

                changeover_s = 0 if leader.get("skip_changeover") else PORTAL_CHANGEOVER_SECONDS
                if leader.get("skip_briefing"):
                    brief_s = prep_s = 0
                else:
                    brief_s = _portal_briefing_seconds(total_count)
                    prep_s = _portal_prep_pause_seconds(total_count)

                if changeover_s:
                    s, e, current = _portal_advance(current, changeover_s, round_minutes)
                    items.append({"segment": "changeover", "label": "Umbau", "block": leader,
                                  "start_time": s, "end_time": e, "participants": 0})

                if brief_s:
                    s, e, current = _portal_advance(current, brief_s, round_minutes)
                    disc = PORTAL_DISCIPLINE_LABELS.get(_blk_discipline(leader), _blk_discipline(leader))
                    briefing_item_indices.append(len(items))
                    items.append({
                        "segment": "briefing",
                        "label": f"Briefing {disc} Kl.{_blk_class_level(leader) or ''}",
                        "block": leader, "start_time": s, "end_time": e, "participants": total_count,
                    })

                if prep_s:
                    s, e, current = _portal_advance(current, prep_s, round_minutes)
                    items.append({"segment": "prep_pause", "label": "Vorbereitungspause", "block": leader,
                                  "start_time": s, "end_time": e, "participants": 0})

                for b, count in zip(run_group, counts):
                    title = b.get("title") or auto_title(_blk_discipline(b), _blk_category(b), _blk_class_level(b))
                    secs = _portal_secs_per_starter(_blk_discipline(b), run_time_config)
                    run_s = max(count * secs, 60)
                    s, e, current = _portal_advance(current, run_s, round_minutes)
                    items.append({"segment": "run", "label": title, "block": b,
                                  "start_time": s, "end_time": e, "participants": count})

        # Briefing-Fenster: end_time = Start des ersten nachfolgenden Laufs der eigenen Gruppe
        for idx in briefing_item_indices:
            first_run = next((it for it in items[idx + 1:] if it["segment"] == "run"), None)
            if first_run:
                items[idx]["end_time"] = first_run["start_time"]

        # Kompatibilitäts-Aliasse für bestehende Templates/Verbraucher, die noch
        # die alten Timeline-Item-Keys lesen (segment_type/num_starters/duration).
        for it in items:
            it["segment_type"] = it["segment"]
            it["num_starters"] = it.get("participants", 0)
            try:
                _s = datetime.datetime.strptime(it["start_time"], "%H:%M")
                _e = datetime.datetime.strptime(it["end_time"], "%H:%M")
                it["duration"] = max(int((_e - _s).total_seconds() // 60), 0)
            except Exception:
                it["duration"] = 0

        segments_by_ring[ring] = items
    return segments_by_ring
