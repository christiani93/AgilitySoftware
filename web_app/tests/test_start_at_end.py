from utils import _place_entries_with_distance, sort_entries_for_startlist


def _entry(start_nr, handler, **extra):
    return {"Startnummer": str(start_nr), "Hundefuehrer": handler, **extra}


def test_sort_entries_for_startlist_moves_laeufig_and_manual_start_last_to_end():
    entries = [
        _entry(1, "A"),
        _entry(2, "B", is_in_season=True),
        _entry(3, "C", start_last=True),
        _entry(4, "D"),
    ]

    ordered = sort_entries_for_startlist(entries)

    assert [e["Startnummer"] for e in ordered] == ["1", "4", "2", "3"]


def test_sort_entries_for_startlist_laeufig_still_last_with_manual_start_order():
    """Regression 21.11.: sobald start_order gesetzt ist (Einweiser-Umreihung),
    wurde die Laeufig-Regel komplett ignoriert - eine laeufige Huendin konnte
    dann VOR normalen Startern landen, nur weil ihr start_order-Wert klein war."""
    entries = [
        _entry(1, "A", start_order=2),
        _entry(2, "B", is_in_season=True, start_order=0),
        _entry(3, "C", start_order=1),
    ]

    ordered = sort_entries_for_startlist(entries)

    assert [e["Startnummer"] for e in ordered] == ["3", "1", "2"]


def test_place_entries_with_distance_moves_laeufig_and_manual_start_last_to_end():
    entries = [
        _entry(1, "A"),
        _entry(2, "B", is_in_season=True),
        _entry(3, "C", start_last=True),
        _entry(4, "D"),
    ]

    final_order = _place_entries_with_distance(entries, distance=2)

    # Beide "ans Ende"-Gruende werden erfasst, kein Eintrag erscheint doppelt.
    assert [e["Startnummer"] for e in final_order] == ["1", "4", "2", "3"]
    assert len(final_order) == len(entries)
