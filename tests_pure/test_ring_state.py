from web_app.live.ring_state import (
    apply_result_saved,
    apply_start_impulse,
    build_view_model_from_state,
    init_ring_entry_state,
)


def _entry(license_nr, first="A", dog="Dog"):
    return {"Lizenznummer": license_nr, "Vorname": first, "Hundename": dog}


def test_start_impulse_only_moves_ready():
    startlist = [_entry("A", "Anna"), _entry("B", "Berta"), _entry("C", "Carla")]
    state = {"current_entry_id": "A", "ready_entry_id": "B"}
    new_state = apply_start_impulse(state, startlist)
    assert new_state["current_entry_id"] == "A"
    assert new_state["ready_entry_id"] == "C"


def test_result_saved_moves_current():
    startlist = [_entry("A", "Anna"), _entry("B", "Berta"), _entry("C", "Carla")]
    state = {"current_entry_id": "A", "ready_entry_id": "B"}
    new_state = apply_result_saved(state, startlist, "A")
    assert new_state["current_entry_id"] == "B"
    assert new_state["ready_entry_id"] == "C"


def test_result_saved_ignores_wrong_entry():
    startlist = [_entry("A", "Anna"), _entry("B", "Berta"), _entry("C", "Carla")]
    state = {"current_entry_id": "A", "ready_entry_id": "B"}
    new_state = apply_result_saved(state, startlist, "X")
    assert new_state == state


def test_view_model_keys_and_names():
    startlist = [_entry("A", "Anna", "Ava"), _entry("B", "Berta", "Balu")]
    state = init_ring_entry_state(startlist)
    vm = build_view_model_from_state(state, startlist, run_meta={"title": "Run 1"})
    assert "run_meta" in vm
    assert "current" in vm
    assert "ready" in vm
    assert "startlist_next" in vm
    assert "ranking_top" in vm
    assert "last_results" in vm
    assert vm["current"]["name"] == "Anna Ava"
    assert vm["ready"]["name"] == "Berta Balu"
