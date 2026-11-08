"""SM-Final-Auswertung (§3.5): Kombirangliste, umgekehrte Startreihenfolge 2. Lauf,
Live-Übernahme-Vorgabe.

Entries werden wie nach recalc_and_store aufgebaut (platz/fehler_total/fehler_parcours/
zeit_total direkt gesetzt) — genau das liest sm_qualification._get_results_from_run.
"""
from sm_final import (
    calculate_sm_final, derive_final_run2_startorder, live_run2_board, rank_final_run,
)


def _e(lic, platz, fehler=0.0, zeit=30.0, dis="", parcours=0):
    return {
        "Lizenznummer": lic, "platz": platz, "fehler_total": fehler,
        "fehler_parcours": parcours, "zeit_total": zeit, "disqualifikation": dis,
        "Hundename": f"Dog{lic}", "Vorname": "V", "Nachname": lic,
    }


def _run(sm_run_type, cat, entries, sct=None):
    laufdaten = {}
    if sct is not None:
        laufdaten = {"standardzeit_sct_gerundet": sct}
    return {"id": f"{cat}_{sm_run_type}", "kategorie": cat, "klasse": "3",
            "sm_run_type": sm_run_type,
            "laufart": "Agility" if "agility" in sm_run_type else "Jumping",
            "is_final": True, "laufdaten": laufdaten, "entries": entries}


def _open_entry(lic):
    """Entry im 2. Lauf, der noch nicht gestartet ist (kein Resultat) -> fehler_total 998."""
    return {"Lizenznummer": lic, "platz": None, "fehler_total": 998,
            "fehler_parcours": 0, "zeit_total": 998.99, "disqualifikation": "",
            "Hundename": f"Dog{lic}", "Vorname": "V", "Nachname": lic}


# ── §3.5 umgekehrte Startreihenfolge 2. Lauf ────────────────────────────────────

def test_run2_startorder_is_reverse_of_run1_ranking():
    # Jumping (Lauf 1): Rang 1..4 = Lizenzen A,B,C,D
    run1 = _run("final_jumping", "Large", [
        _e("A", 1, zeit=30.0), _e("B", 2, zeit=31.0),
        _e("C", 3, zeit=32.0), _e("D", 4, zeit=33.0)])
    event = {"runs": [run1], "sm_config": {}}
    order = derive_final_run2_startorder(event, "Large")
    assert [r["license"] for r in order] == ["D", "C", "B", "A"]   # umgekehrt
    assert order[0]["start_pos"] == 1 and order[0]["run1_rang"] == 4
    assert order[-1]["license"] == "A" and order[-1]["run1_rang"] == 1


def test_run2_startorder_dis_in_run1_starts_first():
    run1 = _run("final_jumping", "Large", [
        _e("A", 1, zeit=30.0), _e("B", 2, zeit=31.0),
        _e("X", None, dis="DIS")])
    event = {"runs": [run1], "sm_config": {}}
    order = derive_final_run2_startorder(event, "Large")
    # DIS steht in Lauf-1-Rangliste zuletzt -> nach Umkehrung ZUERST
    assert order[0]["license"] == "X" and order[0]["run1_dis"] is True
    assert [r["license"] for r in order] == ["X", "B", "A"]


# ── Final-Kombirangliste / Schweizermeister ─────────────────────────────────────

def test_combined_ranking_champion_by_total_fault_points():
    # A: Ju 0/30 + Ag 5/30 = 5 Fp ; B: Ju 0/31 + Ag 0/31 = 0 Fp -> B ist Meister
    run_ju = _run("final_jumping", "Large", [_e("A", 1, fehler=0, zeit=30.0),
                                             _e("B", 2, fehler=0, zeit=31.0)])
    run_ag = _run("final_agility", "Large", [_e("A", 2, fehler=5, zeit=30.0, parcours=5),
                                             _e("B", 1, fehler=0, zeit=31.0)])
    event = {"runs": [run_ju, run_ag], "sm_config": {}}
    cat = calculate_sm_final(event)["Large"]
    assert cat["champion"]["license"] == "B"
    assert cat["combined"][0]["license"] == "B"
    assert cat["combined"][0]["kombi_fehler"] == 0
    assert cat["combined"][1]["license"] == "A"
    assert cat["combined"][1]["kombi_fehler"] == 5


def test_combined_tiebreak_by_total_time_when_faults_equal():
    # Beide 0 Fp -> kleinere Summe Laufzeit entscheidet. A: 30+30=60 ; B: 31+30=61 -> A
    run_ju = _run("final_jumping", "Large", [_e("A", 1, fehler=0, zeit=30.0),
                                             _e("B", 2, fehler=0, zeit=31.0)])
    run_ag = _run("final_agility", "Large", [_e("A", 1, fehler=0, zeit=30.0),
                                             _e("B", 2, fehler=0, zeit=30.0)])
    event = {"runs": [run_ju, run_ag], "sm_config": {}}
    cat = calculate_sm_final(event)["Large"]
    assert cat["champion"]["license"] == "A"


def test_dis_in_one_final_run_not_classified_in_combination():
    run_ju = _run("final_jumping", "Large", [_e("A", 1, fehler=0, zeit=30.0),
                                             _e("B", 2, fehler=0, zeit=31.0)])
    run_ag = _run("final_agility", "Large", [_e("A", None, dis="DIS"),
                                             _e("B", 1, fehler=0, zeit=31.0)])
    event = {"runs": [run_ju, run_ag], "sm_config": {}}
    cat = calculate_sm_final(event)["Large"]
    assert cat["champion"]["license"] == "B"
    a = next(r for r in cat["combined"] if r["license"] == "A")
    assert a["kombi_dis"] is True and a["kombi_rang"] is None


# ── Live-Board 2. Lauf: Übernahme-Vorgabe + Reststarter ─────────────────────────

def test_live_board_current_runner_and_remaining():
    # Lauf 1 fertig (A Rang1, B Rang2, C Rang3) -> Lauf-2-Start: C, B, A
    run_ju = _run("final_jumping", "Large", [
        _e("A", 1, fehler=0, zeit=30.0), _e("B", 2, fehler=0, zeit=31.0),
        _e("C", 3, fehler=5, zeit=32.0, parcours=5)])
    # Lauf 2 (Agility): C schon gelaufen (0/40), B & A noch offen. SCT 40.
    run_ag = _run("final_agility", "Large", [
        _e("C", 1, fehler=0, zeit=40.0), _open_entry("B"), _open_entry("A")], sct=40.0)
    event = {"runs": [run_ju, run_ag], "sm_config": {}}
    board = live_run2_board(event, "Large")
    assert board["remaining"] == 2
    # Startreihenfolge Lauf 2 = C, B, A ; C done -> aktueller Läufer = B
    assert [r["license"] for r in board["start_order"]] == ["C", "B", "A"]
    assert board["current"]["license"] == "B"
    # Führender = C (einziger mit beiden Läufen): Kombi 5 Fp, Zeit 72
    assert board["leader"]["license"] == "C"
    assert board["leader"]["kombi_fehler"] == 5


def test_live_board_takeover_allowance_margin():
    # Führender C: Kombi 5 Fp. Aktueller B hat Lauf1 0 Fp -> darf im Lauf2 bis 5 Fp.
    run_ju = _run("final_jumping", "Large", [
        _e("A", 1, fehler=0, zeit=30.0), _e("B", 2, fehler=0, zeit=31.0),
        _e("C", 3, fehler=5, zeit=32.0, parcours=5)])
    run_ag = _run("final_agility", "Large", [
        _e("C", 1, fehler=0, zeit=40.0), _open_entry("B"), _open_entry("A")], sct=40.0)
    event = {"runs": [run_ju, run_ag], "sm_config": {}}
    board = live_run2_board(event, "Large")
    to = board["current_takeover"]
    assert to["possible"] is True
    assert to["max_fault_points"] == 5           # 5 (Führender) - 0 (B Lauf1)
    assert to["max_clean_time"] == 45.0          # sct2 40 + margin 5


def test_live_board_takeover_impossible_when_run1_too_weak():
    # Führender hat Kombi 0 Fp; aktueller Läufer hat im Lauf1 schon 5 Fp -> nicht mehr möglich
    run_ju = _run("final_jumping", "Large", [
        _e("A", 1, fehler=0, zeit=30.0), _e("B", 2, fehler=5, zeit=31.0, parcours=5)])
    run_ag = _run("final_agility", "Large", [
        _e("A", 1, fehler=0, zeit=40.0), _open_entry("B")], sct=40.0)
    event = {"runs": [run_ju, run_ag], "sm_config": {}}
    board = live_run2_board(event, "Large")
    # Startreihenfolge Lauf2 = B, A ; A noch offen? nein A done. B offen -> current B
    assert board["current"]["license"] == "B"
    assert board["leader"]["license"] == "A"
    to = board["current_takeover"]
    assert to["possible"] is False
    assert to["max_fault_points"] is None
