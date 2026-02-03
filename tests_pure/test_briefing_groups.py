from planner.briefing_groups import (
    apply_group_summaries,
    build_briefing_sessions,
    build_briefing_sessions_from_timeline,
    build_participant_sort_key,
    collect_participants_for_session,
    is_briefing_block,
    session_title_from_run_blocks,
    split_into_groups,
    summarize_group_ranges_with_occurrences,
)


def _entry(start_nr, license_nr, handler_name):
    return {
        "Startnummer": str(start_nr),
        "Lizenznummer": license_nr,
        "Hundefuehrer": handler_name,
        "Hundename": f"Hund {start_nr}",
    }


def test_build_briefing_sessions_from_schedule_blocks():
    blocks = [
        {"type": "briefing", "title": "Begehung 1"},
        {"type": "run", "timing_run_type": "agility", "size_category": "large", "classes": ["1"]},
        {"type": "briefing", "title": "Begehung 2"},
        {"type": "run", "timing_run_type": "jumping", "size_category": "large", "classes": ["1"]},
    ]

    sessions = build_briefing_sessions(blocks)
    assert len(sessions) == 2
    assert len(sessions[0]["run_blocks"]) == 1
    assert len(sessions[1]["run_blocks"]) == 1


def test_collect_participants_and_grouping():
    blocks = [
        {"type": "briefing", "title": "Begehung 1"},
        {"type": "run", "timing_run_type": "agility", "size_category": "large", "classes": ["1"]},
        {"type": "briefing", "title": "Begehung 2"},
        {"type": "run", "timing_run_type": "jumping", "size_category": "large", "classes": ["1"]},
    ]
    sessions = build_briefing_sessions(blocks)

    event = {
        "runs": [
            {"laufart": "Agility", "kategorie": "large", "klasse": "1", "entries": [_entry(1, "L1", "A"), _entry(2, "L2", "B"), _entry(3, "L3", "C")]},
            {"laufart": "Jumping", "kategorie": "large", "klasse": "1", "entries": [_entry(2, "L2", "B"), _entry(4, "L4", "D"), _entry(5, "L5", "E"), _entry(6, "L6", "F"), _entry(7, "L7", "G")]},
        ],
    }

    first_participants = collect_participants_for_session(sessions[0], event)
    second_participants = collect_participants_for_session(sessions[1], event)

    assert {p["Lizenznummer"] for p in first_participants} == {"L1", "L2", "L3"}
    assert {p["Lizenznummer"] for p in second_participants} == {"L2", "L4", "L5", "L6", "L7"}

    groups = split_into_groups(second_participants, group_size=3)
    assert len(groups) == 2
    assert groups[0]["start_nr_von"] == "2"
    assert groups[0]["start_nr_bis"] == "5"
    assert groups[1]["start_nr_von"] == "6"
    assert groups[1]["start_nr_bis"] == "7"


def test_is_briefing_block_detects_labels():
    assert is_briefing_block({"type": "briefing"})
    assert is_briefing_block({"segment_type": "briefing"})
    assert is_briefing_block({"label": "Begehung Ring 1"})
    assert is_briefing_block({"title": "Briefing Pause"})
    assert not is_briefing_block({"type": "run"})


def test_build_sessions_from_timeline_items():
    timeline_items = [
        {"segment_type": "briefing", "label": "Briefing"},
        {"segment_type": "run", "block": {"type": "run", "timing_run_type": "agility", "size_category": "large", "classes": ["1"]}},
        {"segment_type": "briefing", "label": "Briefing 2"},
        {"segment_type": "run", "block": {"type": "run", "timing_run_type": "jumping", "size_category": "large", "classes": ["1"]}},
    ]

    sessions = build_briefing_sessions_from_timeline(timeline_items)
    assert len(sessions) == 2
    assert len(sessions[0]["run_blocks"]) == 1
    assert len(sessions[1]["run_blocks"]) == 1


def test_even_group_split_110_into_3():
    participants = [_entry(idx, f"L{idx}", f"H{idx}") for idx in range(1, 111)]
    groups = split_into_groups(participants, group_size=50, group_count=3)
    assert [len(group["participants"]) for group in groups] == [37, 37, 36]


def test_group_count_from_size():
    participants = [_entry(idx, f"L{idx}", f"H{idx}") for idx in range(1, 111)]
    groups = split_into_groups(participants, group_size=50)
    assert len(groups) == 3


def test_range_summarization():
    participants = [
        {"Startnummer": "1", "Kategorie": "Large", "Klasse": "1"},
        {"Startnummer": "2", "Kategorie": "Large", "Klasse": "1"},
        {"Startnummer": "3", "Kategorie": "Large", "Klasse": "2"},
        {"Startnummer": "4", "Kategorie": "Large", "Klasse": "2"},
        {"Startnummer": "5", "Kategorie": "Large", "Klasse": "3"},
    ]
    summary = summarize_group_ranges_with_occurrences(participants, {})
    assert summary == "L1, L2, L3"


def test_range_summarization_with_split_segment():
    participants = [
        {"Startnummer": "1", "Kategorie": "Large", "Klasse": "3"},
        {"Startnummer": "2", "Kategorie": "Large", "Klasse": "3"},
        {"Startnummer": "3", "Kategorie": "Intermediate", "Klasse": "3"},
        {"Startnummer": "4", "Kategorie": "Large", "Klasse": "3"},
    ]
    summary = summarize_group_ranges_with_occurrences(participants, {})
    assert summary == "L3 1–2, I3, L3 4"


def test_occurrence_based_ranges():
    participants = [_entry(idx, f"L{idx}", f"H{idx}") for idx in range(1, 111)]
    for entry in participants:
        entry["Kategorie"] = "Large"
        entry["Klasse"] = "2"
    groups = split_into_groups(participants, group_size=50, group_count=3)
    apply_group_summaries(groups)
    assert groups[0]["summary"].startswith("L2 ")
    assert groups[1]["summary"].startswith("L2 ")
    assert groups[2]["summary"].startswith("L2 ")


def test_session_title_uses_first_run_title():
    run_blocks = [{
        "type": "run",
        "timing_run_type": "agility",
        "size_category": "large",
        "classes": ["1"],
    }]
    title = session_title_from_run_blocks(run_blocks)
    assert title and "Agility" in title


def test_sort_category_asc():
    participants = [
        {"Kategorie": "Large", "Klasse": "1", "Startnummer": "1"},
        {"Kategorie": "Small", "Klasse": "1", "Startnummer": "2"},
        {"Kategorie": "Medium", "Klasse": "1", "Startnummer": "3"},
        {"Kategorie": "Intermediate", "Klasse": "1", "Startnummer": "4"},
    ]
    key = build_participant_sort_key({"primary": {"field": "category", "direction": "asc"}})
    sorted_entries = [p["Kategorie"] for p in sorted(participants, key=key)]
    assert sorted_entries == ["Small", "Medium", "Intermediate", "Large"]


def test_sort_category_desc():
    participants = [
        {"Kategorie": "Large", "Klasse": "1", "Startnummer": "1"},
        {"Kategorie": "Small", "Klasse": "1", "Startnummer": "2"},
        {"Kategorie": "Medium", "Klasse": "1", "Startnummer": "3"},
        {"Kategorie": "Intermediate", "Klasse": "1", "Startnummer": "4"},
    ]
    key = build_participant_sort_key({"primary": {"field": "category", "direction": "desc"}})
    sorted_entries = [p["Kategorie"] for p in sorted(participants, key=key)]
    assert sorted_entries == ["Large", "Intermediate", "Medium", "Small"]


def test_sort_class_asc_desc():
    participants = [
        {"Kategorie": "Large", "Klasse": "1", "Startnummer": "1"},
        {"Kategorie": "Large", "Klasse": "3", "Startnummer": "2"},
        {"Kategorie": "Large", "Klasse": "2", "Startnummer": "3"},
    ]
    asc_key = build_participant_sort_key({"primary": {"field": "class", "direction": "asc"}})
    desc_key = build_participant_sort_key({"primary": {"field": "class", "direction": "desc"}})
    assert [p["Klasse"] for p in sorted(participants, key=asc_key)] == ["1", "2", "3"]
    assert [p["Klasse"] for p in sorted(participants, key=desc_key)] == ["3", "2", "1"]


def test_primary_secondary_combo():
    participants = [
        {"Kategorie": "Large", "Klasse": "1", "Startnummer": "1"},
        {"Kategorie": "Large", "Klasse": "3", "Startnummer": "2"},
        {"Kategorie": "Large", "Klasse": "2", "Startnummer": "3"},
        {"Kategorie": "Intermediate", "Klasse": "1", "Startnummer": "4"},
        {"Kategorie": "Intermediate", "Klasse": "3", "Startnummer": "5"},
        {"Kategorie": "Medium", "Klasse": "2", "Startnummer": "6"},
        {"Kategorie": "Small", "Klasse": "1", "Startnummer": "7"},
    ]
    key = build_participant_sort_key({
        "primary": {"field": "category", "direction": "desc"},
        "secondary": {"field": "class", "direction": "desc"},
    })
    sorted_entries = [(p["Kategorie"], p["Klasse"]) for p in sorted(participants, key=key)]
    assert sorted_entries == [
        ("Large", "3"),
        ("Large", "2"),
        ("Large", "1"),
        ("Intermediate", "3"),
        ("Intermediate", "1"),
        ("Medium", "2"),
        ("Small", "1"),
    ]
