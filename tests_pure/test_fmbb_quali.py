"""
Pure-Python-Tests für FMBB-Quali-Modul.

Tests decken:
- is_fmbb_active / is_fmbb_entry Flag-Logik
- mark_fmbb_by_licenses Bulk-Setter (mit/ohne reset, unmatched-Liste)
- calculate_fmbb_quali Filter (Klasse, Laufart, FMBB-Marker)
- DIS-Handling in der Rangliste
"""
import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
WEB_APP_PATH = os.path.join(PROJECT_ROOT, "web_app")
if WEB_APP_PATH not in sys.path:
    sys.path.insert(0, WEB_APP_PATH)

from fmbb_quali import (   # noqa: E402
    is_fmbb_active,
    is_fmbb_entry,
    mark_fmbb_by_licenses,
    calculate_fmbb_quali,
    FMBB_ELIGIBLE_CLASSES,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _entry(license_no, rang, fehler_total=0, fehler_parcours=0, zeit_total=40.0,
           dis=None, is_fmbb=None):
    e = {
        "Lizenznummer":    license_no,
        "Hundename":       f"Hund_{license_no}",
        "Vorname":         "Max",
        "Nachname":        f"Muster_{license_no}",
        "platz":           rang,
        "fehler_total":    fehler_total,
        "fehler_parcours": fehler_parcours,
        "zeit_total":      zeit_total,
    }
    if dis:
        e["disqualifikation"] = dis
        e["fehler_total"] = 999
        e["platz"] = None
    if is_fmbb is not None:
        e["is_fmbb"] = is_fmbb
    return e


def _run(klasse, laufart, entries, kategorie="Large"):
    return {
        "kategorie": kategorie,
        "klasse":    klasse,
        "laufart":   laufart,
        "entries":   entries,
    }


# ---------------------------------------------------------------------------
# Flag-Logik
# ---------------------------------------------------------------------------

def test_is_fmbb_active_default_false():
    assert is_fmbb_active({}) is False
    assert is_fmbb_active({"fmbb_quali_active": False}) is False
    assert is_fmbb_active({"fmbb_quali_active": True}) is True


def test_is_fmbb_entry_default_false():
    """Ohne Flag → kein FMBB. Keine Rasse-Heuristik."""
    assert is_fmbb_entry({"Lizenznummer": "1", "Rasse": "Malinois"}) is False
    assert is_fmbb_entry({"Lizenznummer": "2", "is_fmbb": True}) is True
    assert is_fmbb_entry({"Lizenznummer": "3", "is_fmbb": False}) is False


# ---------------------------------------------------------------------------
# Bulk-Setter
# ---------------------------------------------------------------------------

def test_mark_fmbb_by_licenses_basic():
    event = {
        "runs": [
            _run("2", "Agility", [
                _entry("100", rang=1),
                _entry("200", rang=2),
                _entry("300", rang=3),
            ]),
        ],
    }
    stats = mark_fmbb_by_licenses(event, ["100", "300"])
    assert stats["matched"] == 2
    assert stats["unmatched"] == []
    assert stats["total_entries"] == 3
    entries = event["runs"][0]["entries"]
    assert entries[0]["is_fmbb"] is True
    assert entries[1]["is_fmbb"] is False    # reset=True default
    assert entries[2]["is_fmbb"] is True


def test_mark_fmbb_by_licenses_case_insensitive_and_whitespace():
    event = {
        "runs": [
            _run("2", "Agility", [
                _entry("AUT-100", rang=1),
                _entry("aut-200", rang=2),
            ]),
        ],
    }
    stats = mark_fmbb_by_licenses(event, [" aut-100 ", "AUT-200"])
    assert stats["matched"] == 2
    assert all(e["is_fmbb"] for e in event["runs"][0]["entries"])


def test_mark_fmbb_by_licenses_unmatched_reported():
    event = {
        "runs": [
            _run("2", "Agility", [_entry("100", rang=1)]),
        ],
    }
    stats = mark_fmbb_by_licenses(event, ["100", "999", "888"])
    assert stats["matched"] == 1
    assert stats["unmatched"] == ["888", "999"]


def test_mark_fmbb_by_licenses_no_reset_keeps_existing_flags():
    event = {
        "runs": [
            _run("2", "Agility", [
                _entry("100", rang=1, is_fmbb=True),
                _entry("200", rang=2, is_fmbb=True),    # bestehend, nicht in neuer Liste
                _entry("300", rang=3),
            ]),
        ],
    }
    stats = mark_fmbb_by_licenses(event, ["100", "300"], reset=False)
    assert stats["matched"] == 2
    entries = event["runs"][0]["entries"]
    assert entries[0]["is_fmbb"] is True
    assert entries[1]["is_fmbb"] is True   # unverändert wegen reset=False
    assert entries[2]["is_fmbb"] is True


# ---------------------------------------------------------------------------
# calculate_fmbb_quali
# ---------------------------------------------------------------------------

def test_calculate_filtert_klasse_und_marker():
    """Nur Klasse 2+3 + FMBB-markierte Teilnehmer kommen in die Rangliste."""
    event = {
        "fmbb_quali_active": True,
        "runs": [
            # Klasse 1 — wird komplett ignoriert (egal ob FMBB-markiert)
            _run("1", "Agility", [
                _entry("K1", rang=1, is_fmbb=True),
            ]),
            # Klasse 2 Agi — gemischt
            _run("2", "Agility", [
                _entry("F1", rang=1, is_fmbb=True),
                _entry("X1", rang=2, is_fmbb=False),   # nicht FMBB
                _entry("F2", rang=3, is_fmbb=True),
            ]),
            # Klasse 3 Jumping — alle FMBB
            _run("3", "Jumping", [
                _entry("F3", rang=1, is_fmbb=True),
                _entry("F4", rang=2, is_fmbb=True),
            ]),
        ],
    }
    result = calculate_fmbb_quali(event)
    assert result["active"] is True
    assert len(result["runs"]) == 2   # K1 filterung greift

    # Run K2 Agi
    k2_agi = next(r for r in result["runs"] if r["klasse"] == "2" and r["laufart"] == "Agility")
    licenses = [r["license"] for r in k2_agi["rankings"]]
    assert licenses == ["F1", "F2"]   # X1 raus, sortiert nach rang

    # unique FMBB-Lizenzen
    assert result["total_fmbb_teams"] == 4


def test_calculate_filtert_laufart():
    """Nur Agility/Jumping — Open-Läufe ignorieren."""
    event = {
        "fmbb_quali_active": True,
        "runs": [
            _run("3", "Open", [_entry("F1", rang=1, is_fmbb=True)]),
        ],
    }
    result = calculate_fmbb_quali(event)
    assert result["runs"] == []


def test_calculate_leere_runs_werden_uebergangen():
    """Run ohne FMBB-Teilnehmer kommt nicht in die Ausgabe."""
    event = {
        "fmbb_quali_active": True,
        "runs": [
            _run("2", "Agility", [
                _entry("X1", rang=1, is_fmbb=False),
                _entry("X2", rang=2, is_fmbb=False),
            ]),
        ],
    }
    result = calculate_fmbb_quali(event)
    assert result["runs"] == []
    assert result["total_fmbb_teams"] == 0


def test_calculate_dis_kommt_nach_platzierten():
    """DIS-Teams stehen am Ende der Rangliste, mit dis=True."""
    event = {
        "fmbb_quali_active": True,
        "runs": [
            _run("2", "Agility", [
                _entry("F1", rang=1, is_fmbb=True),
                _entry("F2", rang=None, dis="DIS", is_fmbb=True),
                _entry("F3", rang=2, is_fmbb=True),
            ]),
        ],
    }
    result = calculate_fmbb_quali(event)
    rankings = result["runs"][0]["rankings"]
    assert [r["license"] for r in rankings] == ["F1", "F3", "F2"]
    assert rankings[-1]["dis"] is True


def test_calculate_inactive_event_returnt_strukturiert_aber_leer_marker():
    """Bei nicht-aktiviertem FMBB-Flag wird active=False zurückgegeben (Berechnung läuft trotzdem)."""
    event = {
        "runs": [
            _run("2", "Agility", [_entry("F1", rang=1, is_fmbb=True)]),
        ],
    }
    # fmbb_quali_active fehlt
    result = calculate_fmbb_quali(event)
    assert result["active"] is False
    # Berechnung läuft trotzdem (kann z.B. für Vorschau-Modus genutzt werden)
    assert len(result["runs"]) == 1
