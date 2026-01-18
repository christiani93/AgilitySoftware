import copy
import importlib

from planner import schedule_planner as sp


def test_s1_sorting_expansion():
    groups = sp.expand_size_class_groups(
        "all", ["2", "3"],
        primary_sort={"field": "category", "direction": "desc"},
        secondary_sort={"field": "class", "direction": "desc"},
    )
    assert groups == [
        ("large", "3"), ("large", "2"),
        ("intermediate", "3"), ("intermediate", "2"),
        ("medium", "3"), ("medium", "2"),
        ("small", "3"), ("small", "2"),
    ]


def test_s2_briefing_rule():
    base_settings = sp.upgrade_settings({})
    planning = base_settings["schedule_planning"]
    cases = [
        (49, (1, 8 * 60, 300)),
        (50, (2, 16 * 60, 0)),
        (99, (2, 16 * 60, 0)),
        (100, (3, 24 * 60, 0)),
    ]
    for participants, expected in cases:
        blocks, briefing_seconds, prep_seconds = sp.calculate_briefing_and_prep(participants, planning)
        assert (blocks, briefing_seconds, prep_seconds) == expected


def test_s3_mixed_per_class_participants():
    settings = sp.upgrade_settings({
        "schedule_planning": {"mixed_class_time_mode": "per_class_participants"},
        "start_time_seconds": {
            "agility": {
                "large": {"2": 65, "3": 70}
            }
        }
    })
    participants_by_class = {"2": 10, "3": 5}
    seconds = sp.calculate_run_seconds(participants_by_class, "agility", "large", ["2", "3"], settings)
    assert seconds == (10 * 65) + (5 * 70)


def test_s4_mixed_slowest_for_all():
    settings = sp.upgrade_settings({
        "schedule_planning": {"mixed_class_time_mode": "slowest_class_for_all"},
        "start_time_seconds": {
            "agility": {
                "large": {"2": 65, "3": 70}
            }
        }
    })
    participants_by_class = {"2": 10, "3": 5}
    seconds = sp.calculate_run_seconds(participants_by_class, "agility", "large", ["2", "3"], settings)
    assert seconds == 15 * 70


def test_s5_settings_matrix_upgrade_preserves_existing():
    custom_settings = {
        "schedule_planning": {"changeover_seconds": 999},
        "start_time_seconds": {
            "agility": {
                "small": {"1": 12}
            }
        }
    }
    upgraded = sp.upgrade_settings(copy.deepcopy(custom_settings))
    # preserve existing value
    assert upgraded["start_time_seconds"]["agility"]["small"]["1"] == 12
    # ensure defaults added
    assert upgraded["start_time_seconds"]["jumping"]["medium"]["2"] == 60
    # keep provided planning values
    assert upgraded["schedule_planning"]["changeover_seconds"] == 999


def test_computed_timeline_segments():
    settings = sp.upgrade_settings({})
    schedule = {
        "rings": {
            "1": {
                "start_time": "08:00",
                "blocks": [
                    {
                        "id": "blk_run",
                        "type": "run",
                        "run_format": "normal",
                        "timing_run_type": "agility",
                        "size_category": "large",
                        "classes": ["1"],
                        "sort": {"primary": {"field": "none"}, "secondary": {"field": "none"}},
                    }
                ],
            }
        }
    }
    runs = [{"laufart": "agility", "kategorie": "large", "klasse": "1", "entries": [{} for _ in range(49)]}]
    timeline = sp.compute_computed_timeline(schedule, event_runs=runs, settings=settings, start_times_by_ring={"ring_1": "08:00"}, event_date="2026-01-01")
    segments = [item["segment_type"] for item in timeline.get("1", [])]
    assert segments == ["changeover", "briefing", "prep_pause", "run"]
    last_segment = timeline["1"][-1]
    assert last_segment["num_starters"] == 49


def test_generate_title_with_sorting():
    block = {
        "run_format": "open",
        "timing_run_type": "agility",
        "size_category": "all",
        "classes": ["2", "3"],
        "sort": {"primary": {"field": "category", "direction": "desc"}},
    }
    assert sp.generate_run_title(block) == "Open Agility 2+3 Absteigend"


def test_rank_applies_preserved():
    settings = sp.upgrade_settings({})
    schedule = {
        "rings": {
            "1": {
                "start_time": "07:30",
                "blocks": [
                    {
                        "type": "rank_announcement",
                        "title": "Rangverkündung",
                        "duration_seconds": 120,
                        "applies_to": {"size_categories": ["small"], "classes": ["1", "2"]},
                    }
                ],
            }
        }
    }
    timeline = sp.compute_computed_timeline(schedule, settings=settings)
    block = timeline["1"][0]["block"]
    assert block.get("applies_to", {}).get("size_categories") == ["small"]


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__]))
