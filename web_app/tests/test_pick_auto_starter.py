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
