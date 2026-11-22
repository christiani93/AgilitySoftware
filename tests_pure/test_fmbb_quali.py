"""
Pure-Python-Tests für FMBB-Quali-Modul (Reglement-Stand 2026-11-22).

Deckt:
- is_fmbb_active / is_fmbb_entry Flag-Logik
- mark_fmbb_by_licenses Bulk-Setter (reset, case-insensitive, unmatched)
- calculate_fmbb_quali: Filter (Klasse/Laufart/Marker), eigene FMBB-SCT
  (schnellster BSH × 1.15), L2+L3 gemeinsame Rangliste je Disziplin,
  Punktevergabe (Tabelle, ab 15 FP halbe, Zeitfehler → 0), DIS/MCT-Handling.
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
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _entry(license_no, zeit=None, fehler=0, verweigerungen=0, dis=None,
           is_fmbb=None, ausser_konkurrenz=None, klasse=None):
    """Entry im AgilitySoftware-Format mit Roh-result (so wie am Event erfasst)."""
    e = {
        "Lizenznummer": license_no,
        "Hundename":    f"Hund_{license_no}",
        "Vorname":      "Max",
        "Nachname":     f"Muster_{license_no}",
        "result": {
            "zeit":             zeit,
            "fehler":           fehler,
            "verweigerungen":   verweigerungen,
            "disqualifikation": dis,
        },
    }
    if is_fmbb is not None:
        e["is_fmbb"] = is_fmbb
    if ausser_konkurrenz is not None:
        e["ausser_konkurrenz"] = ausser_konkurrenz
    if klasse is not None:
        e["Klasse"] = klasse
    return e


def _run(klasse, laufart, entries, kategorie="Large", parcours=100):
    return {
        "kategorie": kategorie,
        "klasse":    klasse,
        "laufart":   laufart,
        "laufdaten": {"parcours_laenge": parcours},
        "entries":   entries,
    }


def _by_license(rankings):
    return {r["license"]: r for r in rankings}


# ---------------------------------------------------------------------------
# Flag-Logik
# ---------------------------------------------------------------------------

def test_is_fmbb_active_default_false():
    assert is_fmbb_active({}) is False
    assert is_fmbb_active({"fmbb_quali_active": False}) is False
    assert is_fmbb_active({"fmbb_quali_active": True}) is True


def test_is_fmbb_entry_default_false():
    assert is_fmbb_entry({"Lizenznummer": "1", "Rasse": "Malinois"}) is False
    assert is_fmbb_entry({"Lizenznummer": "2", "is_fmbb": True}) is True
    assert is_fmbb_entry({"Lizenznummer": "3", "is_fmbb": False}) is False


# ---------------------------------------------------------------------------
# Bulk-Setter
# ---------------------------------------------------------------------------

def test_mark_fmbb_by_licenses_basic():
    event = {"runs": [_run("2", "Agility", [
        _entry("100"), _entry("200"), _entry("300"),
    ])]}
    stats = mark_fmbb_by_licenses(event, ["100", "300"])
    assert stats["matched"] == 2
    assert stats["unmatched"] == []
    assert stats["total_entries"] == 3
    entries = event["runs"][0]["entries"]
    assert entries[0]["is_fmbb"] is True
    assert entries[1]["is_fmbb"] is False    # reset=True default
    assert entries[2]["is_fmbb"] is True


def test_mark_fmbb_by_licenses_case_insensitive_and_whitespace():
    event = {"runs": [_run("2", "Agility", [
        _entry("AUT-100"), _entry("aut-200"),
    ])]}
    stats = mark_fmbb_by_licenses(event, [" aut-100 ", "AUT-200"])
    assert stats["matched"] == 2
    assert all(e["is_fmbb"] for e in event["runs"][0]["entries"])


def test_mark_fmbb_by_licenses_unmatched_reported():
    event = {"runs": [_run("2", "Agility", [_entry("100")])]}
    stats = mark_fmbb_by_licenses(event, ["100", "999", "888"])
    assert stats["matched"] == 1
    assert stats["unmatched"] == ["888", "999"]


def test_mark_fmbb_by_licenses_no_reset_keeps_existing_flags():
    event = {"runs": [_run("2", "Agility", [
        _entry("100", is_fmbb=True),
        _entry("200", is_fmbb=True),   # bestehend, nicht in neuer Liste
        _entry("300"),
    ])]}
    stats = mark_fmbb_by_licenses(event, ["100", "300"], reset=False)
    assert stats["matched"] == 2
    entries = event["runs"][0]["entries"]
    assert entries[0]["is_fmbb"] is True
    assert entries[1]["is_fmbb"] is True   # unverändert wegen reset=False
    assert entries[2]["is_fmbb"] is True


# ---------------------------------------------------------------------------
# Filter
# ---------------------------------------------------------------------------

def test_calculate_filtert_klasse_laufart_marker():
    """Nur Klasse 2/3 + Agi/Jump + FMBB-markiert; je Disziplin eine Rangliste."""
    event = {
        "fmbb_quali_active": True,
        "runs": [
            _run("1", "Agility", [_entry("K1", zeit=30, is_fmbb=True)]),   # Kl.1 raus
            _run("3", "Open",    [_entry("O1", zeit=30, is_fmbb=True)]),   # Open raus
            _run("2", "Agility", [
                _entry("F1", zeit=30, is_fmbb=True),
                _entry("X1", zeit=28, is_fmbb=False),   # nicht FMBB → raus
                _entry("F2", zeit=33, is_fmbb=True),
            ]),
            _run("3", "Jumping", [
                _entry("F3", zeit=25, is_fmbb=True),
                _entry("F4", zeit=27, is_fmbb=True),
            ]),
        ],
    }
    result = calculate_fmbb_quali(event)
    assert result["active"] is True
    assert len(result["runs"]) == 2                      # Agility + Jumping
    # Jumping steht vor Agility (FMBB-WM-Laufreihenfolge).
    assert [r["laufart"] for r in result["runs"]] == ["Jumping", "Agility"]

    agi = next(r for r in result["runs"] if r["laufart"] == "Agility")
    assert "X1" not in {x["license"] for x in agi["rankings"]}
    assert result["total_fmbb_teams"] == 4


def test_calculate_leere_runs_werden_uebergangen():
    event = {"fmbb_quali_active": True, "runs": [_run("2", "Agility", [
        _entry("X1", zeit=30, is_fmbb=False),
        _entry("X2", zeit=31, is_fmbb=False),
    ])]}
    result = calculate_fmbb_quali(event)
    assert result["runs"] == []
    assert result["total_fmbb_teams"] == 0


def test_inactive_event_rechnet_trotzdem():
    event = {"runs": [_run("2", "Agility", [_entry("F1", zeit=30, is_fmbb=True)])]}
    result = calculate_fmbb_quali(event)
    assert result["active"] is False
    assert len(result["runs"]) == 1


# ---------------------------------------------------------------------------
# SCT (schnellster BSH × 1.15) + Rangfolge + Punkte
# ---------------------------------------------------------------------------

def test_sct_aus_schnellstem_bsh_und_punkte():
    # parcours 100 → MCT_agi = 40. Schnellster BSH 30s → SCT = ceil(30*1.15)=35.
    event = {"fmbb_quali_active": True, "runs": [_run("3", "Agility", [
        _entry("F1", zeit=30, is_fmbb=True),   # Basis, 0 Zeitfehler → Rang 1
        _entry("F2", zeit=33, is_fmbb=True),   # 33<35 → 0 Zeitfehler → Rang 2
        _entry("F3", zeit=36, is_fmbb=True),   # 36>35 → 1 Zeitfehler → 0 Punkte
    ])]}
    run = calculate_fmbb_quali(event)["runs"][0]
    assert run["sct"] == 35
    r = _by_license(run["rankings"])
    assert (r["F1"]["rang"], r["F2"]["rang"], r["F3"]["rang"]) == (1, 2, 3)
    assert r["F1"]["points"] == 20
    assert r["F2"]["points"] == 17
    # F3 hat Zeitfehler → keine Punkte, obwohl platziert.
    assert r["F3"]["zeitfehler"] == 1
    assert r["F3"]["points"] == 0.0


def test_l2_und_l3_gemeinsame_rangliste_und_sct_basis():
    """L2 läuft bei L3 (weisser Hund): gemeinsame Agility-Rangliste, gemeinsame
    SCT-Basis = schnellster BSH über BEIDE Klassen (hier der L2-Hund)."""
    event = {"fmbb_quali_active": True, "runs": [
        _run("3", "Agility", [
            _entry("L3a", zeit=30, is_fmbb=True),
            _entry("L3b", zeit=34, is_fmbb=True),
        ]),
        _run("2", "Agility", [
            _entry("L2a", zeit=28, is_fmbb=True, ausser_konkurrenz=True),  # schnellster BSH
        ]),
    ]}
    runs = calculate_fmbb_quali(event)["runs"]
    assert len(runs) == 1                      # eine gemeinsame Agility-Rangliste
    agi = runs[0]
    assert agi["klasse"] == "2+3"
    assert agi["sct"] == 33                     # ceil(28*1.15)=33
    assert [r["license"] for r in agi["rankings"]] == ["L2a", "L3a", "L3b"]
    r = _by_license(agi["rankings"])
    assert r["L2a"]["klasse"] == "2"
    assert r["L3a"]["klasse"] == "3"


def test_l2_hund_als_entry_im_l3_lauf():
    """Alternatives Setup: der L2-Hund steht als Entry (Klasse 2) direkt im L3-Lauf.
    Die FMBB-Wertung weist ihn als Klasse 2 aus und nimmt ihn in die gemeinsame
    Rangliste; die Disziplin-Klasse wird „2+3"."""
    event = {"fmbb_quali_active": True, "runs": [
        _run("3", "Agility", [
            _entry("L3a", zeit=30, is_fmbb=True, klasse="3"),
            _entry("L2a", zeit=28, is_fmbb=True, klasse="2"),   # weisser Hund im L3-Lauf
        ]),
    ]}
    agi = calculate_fmbb_quali(event)["runs"][0]
    assert agi["klasse"] == "2+3"
    r = _by_license(agi["rankings"])
    assert r["L2a"]["klasse"] == "2"
    assert r["L3a"]["klasse"] == "3"
    assert r["L2a"]["rang"] == 1   # 28s schnellster → SCT-Basis
    assert agi["sct"] == 33        # ceil(28*1.15)


def test_ab_15_parcoursfehler_halbe_punkte():
    # SCT = ceil(30*1.15)=35. F2: 3 Parcoursfehler (=15 FP), 31s < 35 → kein
    # Zeitfehler → halbe Punkte von Rang 2 (17/2 = 8.5).
    event = {"fmbb_quali_active": True, "runs": [_run("3", "Agility", [
        _entry("F1", zeit=30, is_fmbb=True),
        _entry("F2", zeit=31, fehler=3, is_fmbb=True),
    ])]}
    run = calculate_fmbb_quali(event)["runs"][0]
    r = _by_license(run["rankings"])
    assert r["F1"]["rang"] == 1 and r["F1"]["points"] == 20
    assert r["F2"]["rang"] == 2
    assert r["F2"]["fehler_parcours"] == 15
    assert r["F2"]["points"] == 8.5


def test_dis_und_mct_ans_ende_ohne_punkte():
    # parcours 100 → MCT_agi = 40. „SLOW" 45s > 40 → Auto-DIS. „OUT" explizit DIS.
    event = {"fmbb_quali_active": True, "runs": [_run("3", "Agility", [
        _entry("F1", zeit=30, is_fmbb=True),
        _entry("OUT", zeit=32, dis="DIS", is_fmbb=True),
        _entry("SLOW", zeit=45, is_fmbb=True),
    ])]}
    run = calculate_fmbb_quali(event)["runs"][0]
    ranking = run["rankings"]
    assert ranking[0]["license"] == "F1" and ranking[0]["rang"] == 1
    dis = {r["license"] for r in ranking if r["dis"]}
    assert dis == {"OUT", "SLOW"}
    for r in ranking:
        if r["dis"]:
            assert r["rang"] is None
            assert r["points"] == 0.0


def test_ex_aequo_gleicher_rang():
    # Zwei exakt gleiche Ergebnisse → gleicher Rang, nächster überspringt.
    event = {"fmbb_quali_active": True, "runs": [_run("3", "Agility", [
        _entry("A", zeit=30, is_fmbb=True),
        _entry("B", zeit=30, is_fmbb=True),
        _entry("C", zeit=33, is_fmbb=True),
    ])]}
    run = calculate_fmbb_quali(event)["runs"][0]
    r = _by_license(run["rankings"])
    assert r["A"]["rang"] == 1
    assert r["B"]["rang"] == 1
    assert r["C"]["rang"] == 3
