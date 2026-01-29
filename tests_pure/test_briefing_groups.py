from planner.briefing_groups import build_briefing_sessions, collect_participants_for_session, split_into_groups


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
