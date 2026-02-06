from planner.print_schedule_order import build_schedule_print_sections


def _entry(start_nr, license_nr, handler_name):
    return {
        "Startnummer": str(start_nr),
        "Lizenznummer": license_nr,
        "Hundefuehrer": handler_name,
        "Hundename": f"Hund {start_nr}",
    }


def test_schedule_block_order_and_sorting():
    event = {
        "runs": [
            {"id": "r1", "laufart": "Agility", "kategorie": "Small", "klasse": "1", "entries": [_entry(1, "L1", "A")]},
            {"id": "r2", "laufart": "Agility", "kategorie": "Large", "klasse": "1", "entries": [_entry(2, "L2", "B")]},
            {"id": "r3", "laufart": "Jumping", "kategorie": "Large", "klasse": "1", "entries": [_entry(3, "L3", "C")]},
            {"id": "r4", "laufart": "Jumping", "kategorie": "Small", "klasse": "1", "entries": [_entry(4, "L4", "D")]},
        ],
        "schedule": {
            "rings": {
                "1": {
                    "blocks": [
                        {
                            "type": "run",
                            "title": "Agility Block",
                            "timing_run_type": "agility",
                            "size_category": "all",
                            "classes": ["1"],
                            "sort": {"primary": {"field": "category", "direction": "asc"}},
                        },
                        {
                            "type": "run",
                            "title": "Jumping Block",
                            "timing_run_type": "jumping",
                            "size_category": "all",
                            "classes": ["1"],
                            "sort": {"primary": {"field": "category", "direction": "desc"}},
                        },
                    ]
                }
            }
        },
    }

    sections = build_schedule_print_sections(event)
    assert [section["title"] for section in sections] == ["Agility Block (S/M/I/L)", "Jumping Block (L/I/M/S)"]
    assert [p["Kategorie"] for p in sections[0]["participants"]] == ["Small", "Large"]
    assert [p["Kategorie"] for p in sections[1]["participants"]] == ["Large", "Small"]
