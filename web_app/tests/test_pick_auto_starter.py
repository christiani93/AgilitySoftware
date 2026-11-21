from web_app.blueprints.routes_live import _pick_auto_starter


def test_no_ready_mark_follows_strict_order():
    unfinished = [{"Lizenznummer": "A"}, {"Lizenznummer": "B"}, {"Lizenznummer": "C"}]
    current, next_ = _pick_auto_starter(unfinished)
    assert current["Lizenznummer"] == "A"
    assert next_["Lizenznummer"] == "B"


def test_ready_mark_only_promotes_next_not_current():
    """Kernverhalten (Chris 2026-11-21): 'Bereit' treibt NUR die 'Naechster'-
    Anzeige, 'current' bleibt strikt die Startlisten-Reihenfolge."""
    unfinished = [
        {"Lizenznummer": "A"},
        {"Lizenznummer": "B"},
        {"Lizenznummer": "C", "einweiser_mark": "ready"},
    ]
    current, next_ = _pick_auto_starter(unfinished)
    assert current["Lizenznummer"] == "A"
    assert next_["Lizenznummer"] == "C"


def test_ready_mark_on_current_itself_has_no_effect():
    unfinished = [
        {"Lizenznummer": "A", "einweiser_mark": "ready"},
        {"Lizenznummer": "B"},
    ]
    current, next_ = _pick_auto_starter(unfinished)
    assert current["Lizenznummer"] == "A"
    assert next_["Lizenznummer"] == "B"


def test_single_unfinished_entry_has_no_next():
    unfinished = [{"Lizenznummer": "A"}]
    current, next_ = _pick_auto_starter(unfinished)
    assert current["Lizenznummer"] == "A"
    assert next_ == {}


def test_empty_unfinished_returns_empty_dicts():
    assert _pick_auto_starter([]) == ({}, {})


def test_later_marked_entry_is_skipped_for_current_and_next():
    """'kommt später' (Chris 2026-11-21): Ring-PC soll den Teilnehmer komplett
    uebergehen, ohne ihn umzureihen."""
    unfinished = [
        {"Lizenznummer": "A", "einweiser_mark": "later"},
        {"Lizenznummer": "B"},
        {"Lizenznummer": "C"},
    ]
    current, next_ = _pick_auto_starter(unfinished)
    assert current["Lizenznummer"] == "B"
    assert next_["Lizenznummer"] == "C"


def test_later_and_ready_combine_current_strict_next_ready():
    unfinished = [
        {"Lizenznummer": "A", "einweiser_mark": "later"},
        {"Lizenznummer": "B"},
        {"Lizenznummer": "C", "einweiser_mark": "ready"},
    ]
    current, next_ = _pick_auto_starter(unfinished)
    assert current["Lizenznummer"] == "B"
    assert next_["Lizenznummer"] == "C"


def test_all_later_falls_back_instead_of_blocking_run():
    """Sind ALLE verbliebenen Starter 'later' markiert, darf der Lauf nicht
    komplett ohne current_starter haengen bleiben."""
    unfinished = [
        {"Lizenznummer": "A", "einweiser_mark": "later"},
        {"Lizenznummer": "B", "einweiser_mark": "later"},
    ]
    current, next_ = _pick_auto_starter(unfinished)
    assert current["Lizenznummer"] == "A"
    assert next_["Lizenznummer"] == "B"
