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


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__]))
