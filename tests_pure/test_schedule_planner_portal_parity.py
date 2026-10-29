"""
Pure-Python-Tests für die Portal-Parity-Engine (atomare Blöcke) in
planner/schedule_planner.py.

Portiert von AgilityPortal/tests/test_schedule.py (dort DB-/ORM-basiert) auf
die Software's dict-basiertes Event-Modell. Ziel: dieselben Verhaltens-
garantien wie das Portal-Zeitplanmodul — gleiche Konstanten, gleiche
Gruppierung (Disziplin+Klasse, Kategorie irrelevant für die Gruppe), gleiche
Skip-/Split-Schalter, gleiche Teilnehmerzahl-Override-Priorität.
"""
from planner.schedule_planner import (
    estimate_block,
    auto_title,
    link_block_to_run,
    portal_participant_count,
    split_into_groups,
    compute_timeline,
    compute_detailed_segments,
    PORTAL_CHANGEOVER_SECONDS,
)


def _block(id, discipline, category, class_level, sort_index=0, **overrides):
    b = {
        "id": id, "ring": "Ring 1", "block_type": "run",
        "discipline": discipline, "category": category, "class_level": class_level,
        "sort_index": sort_index, "run_id": None, "title": None,
        "skip_changeover": False, "skip_briefing": False, "force_new_group": False,
        "participant_count_override": None,
    }
    b.update(overrides)
    return b


def _rank(id, sort_index, title="Rangverkündigung"):
    return {"id": id, "ring": "Ring 1", "block_type": "rank_announcement",
            "title": title, "sort_index": sort_index}


def _run(id, laufart, kategorie, klasse, n_entries):
    return {"id": id, "laufart": laufart, "kategorie": kategorie, "klasse": klasse,
            "entries": [{"Lizenznummer": f"L{i}"} for i in range(n_entries)]}


# ---------------------------------------------------------------------------
# estimate_block / auto_title
# ---------------------------------------------------------------------------

def test_estimate_block_matches_portal_constants():
    est = estimate_block("agility", 40)
    assert est["changeover_sec"] == PORTAL_CHANGEOVER_SECONDS == 1200
    assert est["briefing_sec"] == 8 * 60          # 40 Starter -> 1 Block -> 8 Min
    assert est["prep_pause_sec"] == 300           # 1 Block -> Preppause
    assert est["run_sec"] == 40 * 65              # Agility = 65s/Starter


def test_estimate_block_briefing_jumps_at_50():
    assert estimate_block("agility", 49)["briefing_sec"] == 8 * 60
    assert estimate_block("agility", 50)["briefing_sec"] == 16 * 60
    assert estimate_block("agility", 50)["prep_pause_sec"] == 0   # >1 Block -> keine Preppause


def test_auto_title():
    assert auto_title("agility", "Large", 1) == "Agility Large Kl. 1"
    assert auto_title("tunnel", "Small", 1) == "Tunnellauf Small Kl. 1"


# ---------------------------------------------------------------------------
# link_block_to_run / portal_participant_count
# ---------------------------------------------------------------------------

def test_link_block_to_run_matches_discipline_category_class():
    runs = [
        _run("r1", "Agility", "Large", "1", 5),
        _run("r2", "Jumping", "Large", "1", 3),
        _run("r3", "Agility", "Small", "1", 2),
    ]
    block = _block("b1", "agility", "Large", 1)
    found = link_block_to_run(block, runs)
    assert found["id"] == "r1"
    assert block["run_id"] == "r1"


def test_link_block_to_run_no_match_leaves_run_id_none():
    runs = [_run("r1", "Agility", "Large", "1", 5)]
    block = _block("b1", "jumping", "Large", 1)
    assert link_block_to_run(block, runs) is None
    assert block["run_id"] is None


def test_participant_count_override_wins_over_run():
    runs = [_run("r1", "Agility", "Large", "1", 5)]
    block = _block("b1", "agility", "Large", 1, run_id="r1", participant_count_override=99)
    assert portal_participant_count(block, runs) == 99


def test_participant_count_via_run_id_direct_link():
    runs = [_run("r1", "Agility", "Large", "1", 7)]
    block = _block("b1", "agility", "Large", 1, run_id="r1")
    assert portal_participant_count(block, runs) == 7


def test_participant_count_falls_back_to_attribute_match_without_run_id():
    runs = [_run("r1", "Agility", "Large", "1", 4)]
    block = _block("b1", "agility", "Large", 1)   # kein run_id
    assert portal_participant_count(block, runs) == 4


def test_participant_count_stale_run_id_falls_back():
    """run_id zeigt auf einen nicht mehr existierenden Lauf (gelöscht/umbenannt)
    -> Fallback auf Attribut-Matching statt Crash/0."""
    runs = [_run("r1", "Agility", "Large", "1", 6)]
    block = _block("b1", "agility", "Large", 1, run_id="GONE")
    assert portal_participant_count(block, runs) == 6


# ---------------------------------------------------------------------------
# split_into_groups
# ---------------------------------------------------------------------------

def test_same_discipline_class_different_category_one_group():
    """Kategorie zählt NICHT zum Gruppierschlüssel -- mehrere Kategorien
    derselben Disziplin+Klasse bilden automatisch eine Gruppe (Portal-Kern-
    verhalten: ein Portal-Export-Block pro Kategorie, trotzdem EIN Briefing)."""
    blocks = [
        _block("b1", "tunnel", "Small", 1, sort_index=10),
        _block("b2", "tunnel", "Medium", 1, sort_index=20),
        _block("b3", "tunnel", "Intermediate", 1, sort_index=30),
        _block("b4", "tunnel", "Large", 1, sort_index=40),
    ]
    groups = split_into_groups(blocks)
    assert len(groups) == 1
    assert groups[0][0] == "run_group"
    assert [b["id"] for b in groups[0][1]] == ["b1", "b2", "b3", "b4"]


def test_discipline_change_starts_new_group():
    blocks = [
        _block("b1", "agility", "Large", 1, sort_index=10),
        _block("b2", "jumping", "Large", 1, sort_index=20),
    ]
    groups = split_into_groups(blocks)
    assert len(groups) == 2


def test_class_change_starts_new_group():
    blocks = [
        _block("b1", "agility", "Large", 1, sort_index=10),
        _block("b2", "agility", "Large", 2, sort_index=20),
    ]
    groups = split_into_groups(blocks)
    assert len(groups) == 2


def test_force_new_group_splits_same_key():
    """Freitag-Fall: Tunnellauf Kl.1 S/M und I/L sind dieselbe (Disziplin,
    Klasse) -> ohne force_new_group EIN Briefing fürs ganze Feld. Das
    Reglement will aber 2 getrennte Briefings -> force_new_group auf dem
    ersten I/L-Block."""
    blocks = [
        _block("b1", "tunnel", "Small", 1, sort_index=10),
        _block("b2", "tunnel", "Medium", 1, sort_index=20),
        _block("b3", "tunnel", "Intermediate", 1, sort_index=30, force_new_group=True),
        _block("b4", "tunnel", "Large", 1, sort_index=40),
    ]
    groups = split_into_groups(blocks)
    assert len(groups) == 2
    assert [b["id"] for b in groups[0][1]] == ["b1", "b2"]
    assert [b["id"] for b in groups[1][1]] == ["b3", "b4"]


def test_rank_announcement_interrupts_group():
    blocks = [
        _block("b1", "agility", "Large", 1, sort_index=10),
        _rank("rk1", sort_index=20),
        _block("b2", "agility", "Large", 1, sort_index=30),
    ]
    groups = split_into_groups(blocks)
    assert [g[0] for g in groups] == ["run_group", "rank", "run_group"]


# ---------------------------------------------------------------------------
# compute_timeline
# ---------------------------------------------------------------------------

def _two_group_blocks():
    return {
        "Ring 1": [
            _block(1, "agility", "Large", 1, sort_index=0),
            _block(2, "open", "Large", 1, sort_index=10,
                   skip_changeover=True, skip_briefing=True),
        ]
    }


def test_timeline_skip_removes_changeover_and_briefing():
    runs = [_run(1, "Agility", "Large", "1", 10), _run(2, "Open", "Large", "1", 10)]
    tl = compute_timeline(_two_group_blocks(), {"Ring 1": "08:00"}, "2026-05-10", event_runs=runs)
    first, second = tl["Ring 1"]
    assert first["changeover_min"] > 0
    assert first["briefing_min"] > 0
    assert second["changeover_min"] == 0
    assert second["briefing_min"] == 0
    # Lückenlos: zweite Gruppe startet, wenn die erste endet
    assert second["start_time"] == first["end_time"]


def test_timeline_shares_one_briefing_across_categories():
    """4 Tunnellauf-Blöcke (S/M/I/L, gleiche Disziplin+Klasse) -> genau EIN
    Umbau+Briefing für die Gruppe, dimensioniert auf die SUMME aller Starter."""
    blocks_by_ring = {"Ring 1": [
        _block("b1", "tunnel", "Small", 1, sort_index=10),
        _block("b2", "tunnel", "Medium", 1, sort_index=20),
        _block("b3", "tunnel", "Intermediate", 1, sort_index=30),
        _block("b4", "tunnel", "Large", 1, sort_index=40),
    ]}
    runs = [
        _run("b1", "Tunnellauf", "Small", "1", 10),
        _run("b2", "Tunnellauf", "Medium", "1", 10),
        _run("b3", "Tunnellauf", "Intermediate", "1", 10),
        _run("b4", "Tunnellauf", "Large", "1", 19),
    ]
    for b, r in zip(blocks_by_ring["Ring 1"], runs):
        b["run_id"] = r["id"]
    tl = compute_timeline(blocks_by_ring, {"Ring 1": "17:00"}, "2026-10-30", event_runs=runs)
    items = tl["Ring 1"]
    assert len(items) == 4
    # Nur das erste Item der Gruppe trägt Umbau/Briefing-Minuten
    assert items[0]["changeover_min"] > 0 and items[0]["briefing_min"] > 0
    for it in items[1:]:
        assert it["changeover_min"] == 0 and it["briefing_min"] == 0
    # 49 Starter gesamt (10+10+10+19, < 50) -> 1 Briefing-Block -> 8 Min + Preppause
    assert items[0]["briefing_min"] == 8
    assert items[0]["prep_pause_min"] == 5


# ---------------------------------------------------------------------------
# compute_detailed_segments
# ---------------------------------------------------------------------------

def test_detailed_segments_skip_omits_umbau_briefing():
    runs = [_run(1, "Agility", "Large", "1", 10), _run(2, "Open", "Large", "1", 10)]
    segs = compute_detailed_segments(_two_group_blocks(), {"Ring 1": "08:00"}, "2026-05-10", event_runs=runs)
    seg_types = {(s["segment"], s["block"].get("discipline")) for s in segs["Ring 1"]}
    assert ("changeover", "agility") in seg_types
    assert ("briefing", "agility") in seg_types
    assert ("changeover", "open") not in seg_types
    assert ("briefing", "open") not in seg_types
    assert ("run", "open") in seg_types


def test_detailed_segments_briefing_window_extends_to_first_run():
    blocks_by_ring = {"Ring 1": [_block("b1", "agility", "Large", 1, sort_index=0)]}
    runs = [_run("b1", "Agility", "Large", "1", 5)]
    blocks_by_ring["Ring 1"][0]["run_id"] = "b1"
    segs = compute_detailed_segments(blocks_by_ring, {"Ring 1": "08:00"}, "2026-05-10", event_runs=runs)["Ring 1"]
    briefing = next(s for s in segs if s["segment"] == "briefing")
    run = next(s for s in segs if s["segment"] == "run")
    assert briefing["end_time"] == run["start_time"]


# ---------------------------------------------------------------------------
# Dual-Read: Engine rechnet auch auf den real gespeicherten Storage-Key-Blöcken
# (type / timing_run_type / size_category / classes) statt der Portal-Keys.
# ---------------------------------------------------------------------------

def _storage_block(id, timing_run_type, size_category, klasse, sort_index=0, **overrides):
    """Atomarer Block im Software-Storage-Format (wie _apply_eventexport_schedule
    ihn schreibt): Einzel-size_category + genau eine Klasse in classes[]."""
    b = {
        "id": id, "ring": "Ring 1", "type": "run",
        "timing_run_type": timing_run_type, "size_category": size_category,
        "size_categories": [], "classes": [str(klasse)],
        "sort_index": sort_index, "run_id": None, "title": "",
        "skip_changeover": False, "skip_briefing": False, "force_new_group": False,
        "participant_count_override": None,
    }
    b.update(overrides)
    return b


def test_storage_keys_group_by_discipline_and_class():
    # Zwei atomare Storage-Blöcke gleiche Disziplin+Klasse, andere Kategorie ->
    # EINE Gruppe (Kategorie zählt nicht), exakt wie bei Portal-Keys.
    blocks = [
        _storage_block("b1", "agility", "large", 1, sort_index=10),
        _storage_block("b2", "agility", "medium", 1, sort_index=20),
        _storage_block("b3", "jumping", "large", 1, sort_index=30),
    ]
    groups = split_into_groups(sorted(blocks, key=lambda b: b["sort_index"]))
    assert [(t, len(c) if isinstance(c, list) else 1) for t, c in groups] == [
        ("run_group", 2), ("run_group", 1)]


def test_storage_keys_timeline_and_override_and_tunnellauf():
    # Override greift; tunnellauf -> tunnel-Zeitfaktor (60s); Timeline läuft durch.
    blocks = [_storage_block("b1", "tunnellauf", "large", 1, sort_index=10,
                             participant_count_override=10)]
    tl = compute_timeline({"Ring 1": blocks}, {"Ring 1": "08:00"}, "2026-10-30")
    item = tl["Ring 1"][0]
    assert item["participants"] == 10
    assert item["run_min"] == (10 * 60) // 60   # tunnel = 60s/Starter


def test_storage_block_links_run_via_attributes():
    # Ohne run_id matcht der Storage-Block den Lauf über laufart/kategorie/klasse.
    block = _storage_block("b1", "agility", "large", 3)
    runs = [_run("r1", "Agility", "Large", 3, 7)]
    assert portal_participant_count(block, runs) == 7


# ---------------------------------------------------------------------------
# Migration: Multi-Kat/Klasse-Blöcke -> atomar (Storage-Keys bleiben)
# ---------------------------------------------------------------------------
from planner.schedule_planner import migrate_schedule_to_atomic, _is_atomic_run_block


def test_migrate_expands_multiblock_to_atomic():
    schedule = {"rings": {"1": {"start_time": "08:00", "blocks": [
        {"id": "b1", "type": "run", "timing_run_type": "agility",
         "size_category": "all", "size_categories": [], "classes": ["1", "2"],
         "sort": {"primary": {"field": "category", "direction": "asc"},
                  "secondary": {"field": "class", "direction": "asc"}}},
    ]}}}
    migrate_schedule_to_atomic(schedule)
    blocks = schedule["rings"]["1"]["blocks"]
    # 4 Kategorien x 2 Klassen = 8 atomare Blöcke
    assert len(blocks) == 8
    assert all(_is_atomic_run_block(b) for b in blocks)
    assert all(len(b["classes"]) == 1 and b["size_categories"] == [] for b in blocks)
    # Verhaltensfelder + sequenzieller sort_index
    assert all("skip_changeover" in b and "force_new_group" in b
               and "participant_count_override" in b for b in blocks)
    assert [b["sort_index"] for b in blocks] == [i * 10 for i in range(8)]
    assert schedule["schedule_version"] == 2


def test_migrate_is_idempotent():
    schedule = {"rings": {"1": {"start_time": "08:00", "blocks": [
        {"id": "b1", "type": "run", "timing_run_type": "agility",
         "size_category": "large", "size_categories": [], "classes": ["3"]},
    ]}}}
    migrate_schedule_to_atomic(schedule)
    first = [dict(b) for b in schedule["rings"]["1"]["blocks"]]
    migrate_schedule_to_atomic(schedule)
    second = schedule["rings"]["1"]["blocks"]
    assert len(second) == 1 and len(first) == 1
    assert second[0]["id"] == first[0]["id"]           # keine Neu-Expansion
    assert second[0]["sort_index"] == 0


def test_migrate_keeps_rank_block():
    schedule = {"rings": {"1": {"start_time": "08:00", "blocks": [
        {"id": "r1", "type": "rank_announcement", "title": "RV", "duration_seconds": 300},
        {"id": "b1", "type": "run", "timing_run_type": "jumping",
         "size_category": "medium", "size_categories": [], "classes": ["2"]},
    ]}}}
    migrate_schedule_to_atomic(schedule)
    blocks = schedule["rings"]["1"]["blocks"]
    assert len(blocks) == 2
    assert blocks[0]["type"] == "rank_announcement"
    assert blocks[0]["sort_index"] == 0 and blocks[1]["sort_index"] == 10


# ---------------------------------------------------------------------------
# block_type "final" (American/KO) — Portal-Pendant: schedule_utils "final"
# ---------------------------------------------------------------------------

def _final(id, sort_index, participant_count_override=None, title=None):
    return {"id": id, "ring": "Ring 1", "block_type": "final",
            "title": title, "sort_index": sort_index,
            "participant_count_override": participant_count_override}


def test_final_block_interrupts_group_like_rank():
    blocks = [
        _block("b1", "agility", "Large", 1, sort_index=10),
        _final("f1", sort_index=20, participant_count_override=32),
        _block("b2", "agility", "Large", 1, sort_index=30),
    ]
    groups = split_into_groups(blocks)
    assert [g[0] for g in groups] == ["run_group", "final", "run_group"]


def test_timeline_final_block_duration_from_override():
    blocks_by_ring = {"Ring 1": [_final("f1", sort_index=0, participant_count_override=32)]}
    tl = compute_timeline(blocks_by_ring, {"Ring 1": "09:00"}, "2026-10-31")
    item = tl["Ring 1"][0]
    assert item["participants"] == 32
    assert item["run_min"] == (32 * 240) // 60      # 240s/Finalstarter Default
    assert item["changeover_min"] == 0 and item["briefing_min"] == 0


def test_timeline_final_block_minimum_duration_when_empty():
    blocks_by_ring = {"Ring 1": [_final("f1", sort_index=0)]}
    tl = compute_timeline(blocks_by_ring, {"Ring 1": "09:00"}, "2026-10-31")
    item = tl["Ring 1"][0]
    assert item["participants"] == 0
    assert item["run_min"] == 1                     # Mindestdauer 60s, aufgerundet auf 1 Min


def test_detailed_segments_final_block_has_label_and_segment():
    blocks_by_ring = {"Ring 1": [_final("f1", sort_index=0, participant_count_override=16, title="Finale Large")]}
    segs = compute_detailed_segments(blocks_by_ring, {"Ring 1": "09:00"}, "2026-10-31")
    seg = segs["Ring 1"][0]
    assert seg["segment"] == "final"
    assert seg["label"] == "Finale Large"
    assert seg["participants"] == 16
    assert seg["segment_type"] == "final" and seg["num_starters"] == 16
