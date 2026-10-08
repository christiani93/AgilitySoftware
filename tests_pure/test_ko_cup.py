"""
Pure-Python-Tests für die KO-Cup-Bracket-Engine (Halloween Cup / American).

Abgedeckt:
- next_power_of_two
- build_bracket: Grössen 2/4/8/16, Rundenzahl, Spiel um Platz 3, R1-Paarung
  (tiefste vs höchste Losnummer)
- score_side: Straffsekunden (Fehler/Verweigerung/DIS), unvollständig → None
- compute_winner: Zeitauswertung, Gleichstand, Forfeit, manueller Sieger, Freilos
- recompute: Rundenautomatik, Halbfinal-Verlierer → Platz 3, Endrangliste 1–4,
  Viertelfinal-Verlierer-Rang
- Freilos (nicht-2er-Potenz)
- ring_assignment: tiefere Startnummer startet Ring 1 + Ringwechsel Lauf 2
"""
import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
WEB_APP_PATH = os.path.join(PROJECT_ROOT, "web_app")
if WEB_APP_PATH not in sys.path:
    sys.path.insert(0, WEB_APP_PATH)

from ko_cup import (   # noqa: E402
    next_power_of_two,
    build_bracket,
    score_side,
    compute_winner,
    is_tie,
    recompute,
    compute_results,
    ring_assignment,
    bracket_status,
    round_label,
)


# ---------------------------------------------------------------------------
# Fixtures / Helfer
# ---------------------------------------------------------------------------

def _participants(n, draws=None, starts=None):
    """n Teilnehmer p1..pn. draws[i]/starts[i] optional, sonst = i+1."""
    draws = draws or list(range(1, n + 1))
    starts = starts or list(range(1, n + 1))
    return [
        {
            "id": f"p{i+1}",
            "dog_name": f"Hund{i+1}",
            "handler_name": f"Fuehrer{i+1}",
            "license_no": f"L{i+1}",
            "start_number": starts[i],
            "seeding_rank": i + 1,
            "draw_number": draws[i],
            "source": "run",
        }
        for i in range(n)
    ]


def _final(n, **kw):
    parts = _participants(n, **kw)
    return {
        "id": "F1",
        "group_label": "Large",
        "category_code": "Large",
        "class_level": None,
        "participants": parts,
        "matchups": build_bracket(parts),
        "results": [],
        "is_published": False,
    }


def _set_total(matchup, side, total):
    """Setzt eine Seite auf eine saubere Gesamtzeit (run1=total, run2=0)."""
    matchup[side]["run1"] = {"time": total, "faults": 0, "refusals": 0, "dis": False}
    matchup[side]["run2"] = {"time": 0.0, "faults": 0, "refusals": 0, "dis": False}


def _find(final, round_no, matchup_no, mtype="winner"):
    return next(
        m for m in final["matchups"]
        if m["round_no"] == round_no and m["matchup_no"] == matchup_no
        and m["matchup_type"] == mtype
    )


def _rank_of(final, pid):
    return next((r["rank"] for r in final["results"] if r["participant_id"] == pid), None)


# ---------------------------------------------------------------------------
# next_power_of_two
# ---------------------------------------------------------------------------

def test_next_power_of_two():
    assert next_power_of_two(1) == 2
    assert next_power_of_two(2) == 2
    assert next_power_of_two(3) == 4
    assert next_power_of_two(5) == 8
    assert next_power_of_two(8) == 8
    assert next_power_of_two(9) == 16
    assert next_power_of_two(16) == 16
    assert next_power_of_two(17) == 32


# ---------------------------------------------------------------------------
# build_bracket – Struktur
# ---------------------------------------------------------------------------

def test_build_bracket_size2():
    f = _final(2)
    assert len(f["matchups"]) == 1  # nur das Final, kein Platz-3-Spiel
    m = f["matchups"][0]
    assert m["round_no"] == 1 and m["matchup_type"] == "winner"
    # tiefste (p1) vs höchste (p2) Losnummer
    assert {m["a_id"], m["b_id"]} == {"p1", "p2"}


def test_build_bracket_size4():
    f = _final(4)
    winners = [m for m in f["matchups"] if m["matchup_type"] == "winner"]
    thirds = [m for m in f["matchups"] if m["matchup_type"] == "third_place"]
    assert len(winners) == 3   # 2 Halbfinals + 1 Final
    assert len(thirds) == 1    # Spiel um Platz 3
    # Runde-1-Paarung: tiefste vs höchste
    r1m1 = _find(f, 1, 1)
    assert {r1m1["a_id"], r1m1["b_id"]} == {"p1", "p4"}
    r1m2 = _find(f, 1, 2)
    assert {r1m2["a_id"], r1m2["b_id"]} == {"p2", "p3"}


def test_build_bracket_size8_and_16():
    f8 = _final(8)
    assert len([m for m in f8["matchups"] if m["matchup_type"] == "winner"]) == 7
    assert len([m for m in f8["matchups"] if m["matchup_type"] == "third_place"]) == 1
    assert max(m["round_no"] for m in f8["matchups"]) == 3

    f16 = _final(16)
    assert len([m for m in f16["matchups"] if m["matchup_type"] == "winner"]) == 15
    assert max(m["round_no"] for m in f16["matchups"]) == 4


# ---------------------------------------------------------------------------
# score_side
# ---------------------------------------------------------------------------

def test_score_side_penalties():
    side = {
        "run1": {"time": 10.0, "faults": 1, "refusals": 0, "dis": False},  # +2
        "run2": {"time": 10.0, "faults": 0, "refusals": 1, "dis": True},   # +2 +5
    }
    assert score_side(side) == 29.0  # 10+2 + 10+2+5


def test_score_side_incomplete():
    side = {"run1": {"time": 10.0}, "run2": {"time": None}}
    assert score_side(side) is None


# ---------------------------------------------------------------------------
# compute_winner
# ---------------------------------------------------------------------------

def test_compute_winner_by_time():
    f = _final(2)
    m = f["matchups"][0]
    _set_total(m, "a", 30.0)
    _set_total(m, "b", 25.0)
    w, l = compute_winner(m)
    assert w == m["b_id"] and l == m["a_id"]


def test_compute_winner_tie():
    f = _final(2)
    m = f["matchups"][0]
    _set_total(m, "a", 30.0)
    _set_total(m, "b", 30.0)
    assert compute_winner(m) == (None, None)
    assert is_tie(m) is True
    # manueller Sieger bricht den Gleichstand
    m["manual_winner_id"] = m["a_id"]
    assert is_tie(m) is False
    w, l = compute_winner(m)
    assert w == m["a_id"] and l == m["b_id"]


def test_compute_winner_forfeit():
    f = _final(2)
    m = f["matchups"][0]
    m["forfeit_id"] = m["a_id"]
    w, l = compute_winner(m)
    assert w == m["b_id"] and l == m["a_id"]


def test_compute_winner_incomplete():
    f = _final(2)
    m = f["matchups"][0]
    _set_total(m, "a", 30.0)
    # b hat noch keine Zeit
    assert compute_winner(m) == (None, None)


# ---------------------------------------------------------------------------
# recompute – voller Durchlauf 4er-Bracket
# ---------------------------------------------------------------------------

def test_recompute_full_4():
    f = _final(4)
    # Halbfinals: p1 schlägt p4, p2 schlägt p3
    r1m1 = _find(f, 1, 1)   # p1 vs p4
    _set_total(r1m1, "a" if r1m1["a_id"] == "p1" else "b", 20.0)
    _set_total(r1m1, "b" if r1m1["a_id"] == "p1" else "a", 40.0)
    r1m2 = _find(f, 1, 2)   # p2 vs p3
    _set_total(r1m2, "a" if r1m2["a_id"] == "p2" else "b", 20.0)
    _set_total(r1m2, "b" if r1m2["a_id"] == "p2" else "a", 40.0)

    recompute(f)

    final_m = _find(f, 2, 1)           # Final: Sieger HF1 vs Sieger HF2
    assert {final_m["a_id"], final_m["b_id"]} == {"p1", "p2"}
    third_m = _find(f, 2, 2, "third_place")  # Verlierer HF1 vs Verlierer HF2
    assert {third_m["a_id"], third_m["b_id"]} == {"p3", "p4"}

    # Final: p1 gewinnt; Platz 3: p4 gewinnt
    _set_total(final_m, "a" if final_m["a_id"] == "p1" else "b", 18.0)
    _set_total(final_m, "b" if final_m["a_id"] == "p1" else "a", 22.0)
    _set_total(third_m, "a" if third_m["a_id"] == "p4" else "b", 19.0)
    _set_total(third_m, "b" if third_m["a_id"] == "p4" else "a", 25.0)

    recompute(f)

    assert bracket_status(f) == "done"
    assert _rank_of(f, "p1") == 1
    assert _rank_of(f, "p2") == 2
    assert _rank_of(f, "p4") == 3
    assert _rank_of(f, "p3") == 4


# ---------------------------------------------------------------------------
# recompute – 8er: Viertelfinal-Verlierer teilen Rang 5
# ---------------------------------------------------------------------------

def test_recompute_8_quarterfinal_losers_rank5():
    f = _final(8)
    # Alle Matchups: Seite A gewinnt immer (A = höhere Position/tiefere Losnummer-Hälfte)
    def _resolve_all():
        for m in f["matchups"]:
            if m["a_id"] and m["b_id"] and m["winner_id"] is None:
                _set_total(m, "a", 10.0)
                _set_total(m, "b", 20.0)
    # iterativ: Ergebnisse setzen + recompute bis Final entschieden
    for _ in range(4):
        _resolve_all()
        recompute(f)

    assert bracket_status(f) == "done"
    # Bei 8 Teilnehmern: Runde 1 = Viertelfinal, Runde 2 = Halbfinal, Runde 3 = Final.
    # Die 4 Viertelfinal-Verlierer (Runde 1) erreichen kein Halbfinal → Rang 5, geteilt.
    qf_losers = [m["loser_id"] for m in f["matchups"]
                 if m["round_no"] == 1 and m["loser_id"]]
    assert len(qf_losers) == 4
    for pid in qf_losers:
        assert _rank_of(f, pid) == 5
    # Halbfinal-Verlierer (Runde 2) landen via Spiel um Platz 3 auf Rang 3 und 4.
    sf_losers = [m["loser_id"] for m in f["matchups"]
                 if m["round_no"] == 2 and m["matchup_type"] == "winner" and m["loser_id"]]
    assert sorted(_rank_of(f, pid) for pid in sf_losers) == [3, 4]


# ---------------------------------------------------------------------------
# Freilos (nicht-2er-Potenz)
# ---------------------------------------------------------------------------

def test_bye_advances_automatically():
    f = _final(3)   # size 4, ein Freilos
    # p1 (tiefste Losnummer) trifft auf Freilos (Position 3 = None)
    r1m1 = _find(f, 1, 1)
    assert r1m1["a_id"] == "p1" and r1m1["b_id"] is None
    recompute(f)
    assert r1m1["winner_id"] == "p1"   # Bye → automatisch weiter
    # p1 steht im Final-Matchup als ein Teilnehmer
    final_m = _find(f, 2, 1)
    assert "p1" in {final_m["a_id"], final_m["b_id"]}


# ---------------------------------------------------------------------------
# ring_assignment
# ---------------------------------------------------------------------------

def test_ring_assignment_lower_start_number_ring1():
    # p1 Startnummer 5, p4 Startnummer 12 → p1 Ring 1 zuerst
    f = _final(4, starts=[5, 8, 9, 12])
    r1m1 = _find(f, 1, 1)   # p1 vs p4
    ra = ring_assignment(f, r1m1)
    a_is_p1 = r1m1["a_id"] == "p1"
    p1_side = "a" if a_is_p1 else "b"
    p4_side = "b" if a_is_p1 else "a"
    assert ra[p1_side]["run1"] == 1 and ra[p1_side]["run2"] == 2
    assert ra[p4_side]["run1"] == 2 and ra[p4_side]["run2"] == 1


# ---------------------------------------------------------------------------
# round_label
# ---------------------------------------------------------------------------

def test_round_label():
    assert round_label(3, 3) == "Final"
    assert round_label(2, 3) == "Halbfinal"
    assert round_label(1, 3) == "Viertelfinal"
    assert round_label(1, 4) == "Achtelfinal"
    assert round_label(2, 3, "third_place") == "Spiel um Platz 3"
