from planner.print_order import get_ordered_runs_for_print, build_briefing_sessions


def _entry(start_nr, license_nr, handler_name):
    return {
        "Startnummer": str(start_nr),
        "Lizenznummer": license_nr,
        "Hundefuehrer": handler_name,
        "Hundename": f"Hund {start_nr}",
    }


def test_print_order_follows_run_order():
    event = {
        "runs": [
            {"id": "ag1", "laufart": "Agility", "kategorie": "Large", "klasse": "1", "entries": [_entry(1, "L1", "A")]},
            {"id": "ag2", "laufart": "Agility", "kategorie": "Small", "klasse": "1", "entries": [_entry(2, "S1", "B")]},
            {"id": "jump1", "laufart": "Jumping", "kategorie": "Large", "klasse": "1", "entries": [_entry(3, "L2", "C")]},
        ],
        "run_order": [
            {"laufart": "Agility", "kategorie": "Alle", "klasse": "Alle"},
            {"laufart": "Pause"},
            {"laufart": "Jumping", "kategorie": "Large", "klasse": "1"},
        ],
    }

    ordered = get_ordered_runs_for_print(event)
    assert [run["id"] for run in ordered] == ["ag1", "ag2", "jump1"]


def test_print_order_falls_back_to_event_runs_when_missing_order():
    event = {
        "runs": [
            {"id": "jump_small", "laufart": "Jumping", "kategorie": "Small", "klasse": "1", "entries": [_entry(2, "S1", "B"), _entry(1, "S2", "A")]},
            {"id": "ag_large", "laufart": "Agility", "kategorie": "Large", "klasse": "1", "entries": [_entry(3, "L1", "C")]},
            {"id": "ag_small", "laufart": "Agility", "kategorie": "Small", "klasse": "1", "entries": [_entry(4, "S3", "D")]},
        ],
        "run_order": [],
    }

    ordered = get_ordered_runs_for_print(event)

    assert [run["id"] for run in ordered] == ["ag_large", "ag_small", "jump_small"]
    assert [entry["Startnummer"] for entry in ordered[0]["entries"]] == ["3"]
    assert [entry["Startnummer"] for entry in ordered[1]["entries"]] == ["4"]
    assert [entry["Startnummer"] for entry in ordered[2]["entries"]] == ["1", "2"]


def test_briefing_sessions_split_by_briefing_blocks():
    event = {
        "runs": [
            {"id": "ag1", "laufart": "Agility", "kategorie": "Large", "klasse": "1", "entries": [_entry(1, "L1", "A"), _entry(2, "L2", "B"), _entry(3, "L3", "C")]},
            {"id": "jump1", "laufart": "Jumping", "kategorie": "Large", "klasse": "1", "entries": [_entry(2, "L2", "B"), _entry(4, "L4", "D")]},
            {"id": "ag2", "laufart": "Agility", "kategorie": "Large", "klasse": "2", "entries": [_entry(5, "L5", "E"), _entry(6, "L6", "F"), _entry(7, "L7", "G")]},
        ],
        "run_order": [
            {"laufart": "Briefing", "label": "Begehung 1"},
            {"laufart": "Agility", "kategorie": "Large", "klasse": "1"},
            {"laufart": "Jumping", "kategorie": "Large", "klasse": "1"},
            {"laufart": "Briefing", "label": "Begehung 2"},
            {"laufart": "Agility", "kategorie": "Large", "klasse": "2"},
        ],
    }

    sessions = build_briefing_sessions(event, group_size=3)
    assert len(sessions) == 2

    first_groups = sessions[0]["groups"]
    assert len(first_groups) == 2
    assert first_groups[0]["start_nr_von"] == "1"
    assert first_groups[0]["start_nr_bis"] == "3"
    assert first_groups[1]["start_nr_von"] == "4"
    assert first_groups[1]["start_nr_bis"] == "4"

    second_groups = sessions[1]["groups"]
    assert len(second_groups) == 1
    assert second_groups[0]["start_nr_von"] == "5"
    assert second_groups[0]["start_nr_bis"] == "7"


def test_briefing_sessions_respect_filters_all_vs_specific():
    event = {
        "runs": [
            {"id": "ag_small", "laufart": "Agility", "kategorie": "Small", "klasse": "1", "entries": [_entry(1, "S1", "Small")]} ,
            {"id": "ag_large", "laufart": "Agility", "kategorie": "Large", "klasse": "1", "entries": [_entry(2, "L1", "Large")]},
        ],
        "run_order": [
            {"laufart": "Briefing", "label": "Alle"},
            {"laufart": "Agility", "kategorie": "Alle", "klasse": "Alle"},
            {"laufart": "Briefing", "label": "Large"},
            {"laufart": "Agility", "kategorie": "Large", "klasse": "1"},
        ],
    }

    sessions = build_briefing_sessions(event, group_size=50)
    assert len(sessions) == 2

    session_all = sessions[0]["groups"][0]["participants"]
    session_large = sessions[1]["groups"][0]["participants"]

    assert {p["Lizenznummer"] for p in session_all} == {"S1", "L1"}
    assert {p["Lizenznummer"] for p in session_large} == {"L1"}
