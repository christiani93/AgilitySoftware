"""
Pure-Python-Tests für Team-Challenge-Wertungsservice.

Edge Cases:
- Normale Team-Wertung: Summe Fehler + Summe Zeit, sortiert (fehler, zeit)
- Separate Ranglisten pro (kategorie, level)
- Ex-aequo-Rangvergabe
- Unvollständiges Team (ein Mitglied DIS) → zählt weiter, ans Gruppenende
- Team ohne jegliche Lauf-Zuordnung → kein Rang, aber in Ergebnisliste sichtbar
- Lauf noch nicht gewertet (pending) → Team-Status "pending", kein definitiver Rang nötig
"""
import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
WEB_APP_PATH = os.path.join(PROJECT_ROOT, "web_app")
if WEB_APP_PATH not in sys.path:
    sys.path.insert(0, WEB_APP_PATH)

from team_challenge_qualification import (   # noqa: E402
    calculate_team_challenge_results,
    group_by_category_and_level,
)


# ---------------------------------------------------------------------------
# Helpers — Test-Fixtures
# ---------------------------------------------------------------------------

def _entry(lizenz, fehler_total, zeit_total, platz=None, dis=None):
    e = {
        "Lizenznummer": lizenz,
        "Hundename": f"Hund_{lizenz}",
        "Vorname": "Max",
        "Nachname": f"Muster_{lizenz}",
        "fehler_total": fehler_total,
        "zeit_total": zeit_total,
        "platz": platz,
    }
    if dis:
        e["disqualifikation"] = dis
    return e


def _run(laufart, team_level, entries):
    return {
        "is_team_challenge": True,
        "team_level": team_level,
        "laufart": laufart,
        "entries": entries,
    }


def _team(ext_id, kategorie, level, agi_lizenz, jump_lizenz, name=""):
    return {
        "external_id": ext_id,
        "name": name,
        "kategorie": kategorie,
        "level": level,
        "mitglied_agility_lizenz": agi_lizenz,
        "mitglied_jumping_lizenz": jump_lizenz,
        "source": "software",
    }


def _event(teams, runs):
    return {"teams": teams, "runs": runs}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_einfache_team_wertung_summe_und_sortierung():
    runs = [
        _run("Agility", "soft", [
            _entry("A1", fehler_total=0, zeit_total=30.0, platz=1),
            _entry("A2", fehler_total=5, zeit_total=32.0, platz=2),
        ]),
        _run("Jumping", "soft", [
            _entry("J1", fehler_total=0, zeit_total=25.0, platz=1),
            _entry("J2", fehler_total=0, zeit_total=20.0, platz=2),
        ]),
    ]
    teams = [
        _team("T1", "Large", "soft", "A1", "J1"),   # total: 0+55=55 faults 0, time 55
        _team("T2", "Large", "soft", "A2", "J2"),   # faults 5, time 52
    ]
    event = _event(teams, runs)

    results = calculate_team_challenge_results(event)
    t1 = next(r for r in results if r["external_id"] == "T1")
    t2 = next(r for r in results if r["external_id"] == "T2")

    assert t1["total_faults"] == 0
    assert t1["total_time"] == 55.0
    assert t2["total_faults"] == 5
    assert t2["total_time"] == 52.0

    # T1 hat weniger Fehler -> Rang 1, trotz langsamerer Zeit
    assert t1["rank"] == 1
    assert t2["rank"] == 2


def test_zeit_entscheidet_bei_gleichen_fehlern():
    runs = [
        _run("Agility", "soft", [
            _entry("A1", 0, 30.0), _entry("A2", 0, 28.0),
        ]),
        _run("Jumping", "soft", [
            _entry("J1", 0, 20.0), _entry("J2", 0, 20.0),
        ]),
    ]
    teams = [
        _team("T1", "Large", "soft", "A1", "J1"),  # 50.0
        _team("T2", "Large", "soft", "A2", "J2"),  # 48.0
    ]
    results = calculate_team_challenge_results(_event(teams, runs))
    t1 = next(r for r in results if r["external_id"] == "T1")
    t2 = next(r for r in results if r["external_id"] == "T2")
    assert t1["total_faults"] == t2["total_faults"] == 0
    assert t2["rank"] == 1  # schneller
    assert t1["rank"] == 2


def test_separate_ranglisten_pro_kategorie_und_level():
    runs = [
        _run("Agility", "soft", [_entry("LA", 0, 30.0), _entry("MA", 0, 30.0)]),
        _run("Jumping", "soft", [_entry("LJ", 0, 20.0), _entry("MJ", 0, 20.0)]),
        _run("Agility", "expert", [_entry("LA3", 0, 25.0)]),
        _run("Jumping", "expert", [_entry("LJ3", 0, 18.0)]),
    ]
    teams = [
        _team("L-soft", "Large", "soft", "LA", "LJ"),
        _team("M-soft", "Medium", "soft", "MA", "MJ"),
        _team("L-expert", "Large", "expert", "LA3", "LJ3"),
    ]
    results = calculate_team_challenge_results(_event(teams, runs))
    grouped = group_by_category_and_level(results)

    assert set(grouped.keys()) == {("Large", "soft"), ("Medium", "soft"), ("Large", "expert")}
    # Jede Gruppe rankt unabhängig -> beide "soft"-Teams Rang 1 in ihrer eigenen Gruppe
    l_soft = next(r for r in results if r["external_id"] == "L-soft")
    m_soft = next(r for r in results if r["external_id"] == "M-soft")
    assert l_soft["rank"] == 1
    assert m_soft["rank"] == 1


def test_ex_aequo_gleicher_rang():
    runs = [
        _run("Agility", "soft", [_entry("A1", 0, 30.0), _entry("A2", 0, 30.0)]),
        _run("Jumping", "soft", [_entry("J1", 0, 20.0), _entry("J2", 0, 20.0)]),
    ]
    teams = [
        _team("T1", "Large", "soft", "A1", "J1"),
        _team("T2", "Large", "soft", "A2", "J2"),
    ]
    results = calculate_team_challenge_results(_event(teams, runs))
    t1 = next(r for r in results if r["external_id"] == "T1")
    t2 = next(r for r in results if r["external_id"] == "T2")
    assert t1["rank"] == t2["rank"] == 1


def test_dis_eines_mitglieds_team_zaehlt_unvollstaendig_weiter():
    runs = [
        _run("Agility", "soft", [
            _entry("A1", 0, 30.0),
            _entry("A2", fehler_total=999, zeit_total=999.99, dis="DIS"),
        ]),
        _run("Jumping", "soft", [
            _entry("J1", 0, 20.0),
            _entry("J2", 0, 18.0),
        ]),
    ]
    teams = [
        _team("T1", "Large", "soft", "A1", "J1"),
        _team("T2", "Large", "soft", "A2", "J2"),  # Agility-Mitglied DIS
    ]
    results = calculate_team_challenge_results(_event(teams, runs))
    t1 = next(r for r in results if r["external_id"] == "T1")
    t2 = next(r for r in results if r["external_id"] == "T2")

    assert t1["status"] == "ok"
    assert t2["status"] == "incomplete"
    # T2 bleibt in der Rangliste, aber weit hinten (Sentinel-Fehler)
    assert t2["total_faults"] >= 999
    assert t1["rank"] < t2["rank"]


def test_team_ohne_lauf_zuordnung_bleibt_ohne_rang():
    runs = [
        _run("Agility", "soft", [_entry("A1", 0, 30.0)]),
        _run("Jumping", "soft", [_entry("J1", 0, 20.0)]),
    ]
    teams = [
        _team("T1", "Large", "soft", "A1", "J1"),
        _team("Tx", "Large", "soft", "UNKNOWN1", "UNKNOWN2"),
    ]
    results = calculate_team_challenge_results(_event(teams, runs))
    tx = next(r for r in results if r["external_id"] == "Tx")
    assert tx["status"] == "no_entries"
    assert tx["rank"] is None


def test_lauf_noch_nicht_gewertet_status_pending():
    # fehler_total/zeit_total fehlen (Lauf noch nicht gelaufen/berechnet)
    runs = [
        _run("Agility", "soft", [{"Lizenznummer": "A1"}]),
        _run("Jumping", "soft", [{"Lizenznummer": "J1"}]),
    ]
    teams = [_team("T1", "Large", "soft", "A1", "J1")]
    results = calculate_team_challenge_results(_event(teams, runs))
    t1 = results[0]
    assert t1["status"] == "pending"
