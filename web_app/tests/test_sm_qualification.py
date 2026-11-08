"""SM-Qualifikation: zwei getrennte Bezugsgrößen (an TKAMO-SM-2026-Echtdaten verifiziert).

- 40 %-Finalplätze = ANGEMELDETE Läufer der Kategorie (Roster `event['sm_registered']`,
  inkl. später DNS), NICHT die effektiv Gestarteten.
- 16 %-Direktquote = GESTARTETE pro Lauf (Agility und Jumping getrennt; DIS zählt mit,
  DNS nicht). Ein Team, das im anderen Lauf DIS ist, qualifiziert sich NUR, wenn es im
  sauberen Lauf innerhalb der 16 %-Rang-Grenze dieses Laufs liegt.
"""
from sm_qualification import calculate_sm_qualification


def _e(lic, platz, fehler=0.0, zeit=30.0, dis="", parcours=0):
    return {
        "Lizenznummer": lic, "platz": platz, "fehler_total": fehler,
        "fehler_parcours": parcours, "zeit_total": zeit, "disqualifikation": dis,
        "Hundename": f"Dog{lic}", "Vorname": "V", "Nachname": lic,
    }


def _run(sm_run_type, cat, entries):
    return {"id": f"{cat}_{sm_run_type}", "kategorie": cat, "klasse": "3",
            "sm_run_type": sm_run_type,
            "laufart": "Agility" if "agility" in sm_run_type else "Jumping",
            "entries": entries}


def test_final_spots_based_on_registered_roster():
    """final_spots = ceil(Angemeldete × 0.40), nicht ceil(Gestartete × 0.40)."""
    qa = [_e(str(i), i, zeit=30 + i * 0.1) for i in range(1, 21)]
    qj = [_e(str(i), i, zeit=31 + i * 0.1) for i in range(1, 21)]
    event = {"runs": [_run("qual_agility", "Large", qa), _run("qual_jumping", "Large", qj)],
             "sm_registered": {"Large": 30}, "sm_config": {}}
    cd = calculate_sm_qualification(event)["Large"]
    assert cd["registered"] == 30
    assert cd["starters"] == 20
    assert cd["final_spots"] == 12          # ceil(30*0.4) — NICHT ceil(20*0.4)=8


def test_registered_fallback_to_started_union_when_absent():
    """Ohne sm_registered (reiner Resultat-Import) = alte Semantik: Gestartete-Union."""
    qa = [_e(str(i), i) for i in range(1, 21)]
    qj = [_e(str(i), i) for i in range(1, 21)]
    event = {"runs": [_run("qual_agility", "Large", qa), _run("qual_jumping", "Large", qj)],
             "sm_config": {}}
    cd = calculate_sm_qualification(event)["Large"]
    assert cd["registered"] == 20
    assert cd["final_spots"] == 10          # max(10, ceil(20*0.4)=8) = 10


def test_direct_quota_per_run_and_dis_boundary():
    """16 % getrennt je Lauf; ein im anderen Lauf DIS-Team muss im sauberen Lauf
    INNERHALB der Rang-Grenze liegen, sonst kein Finalist."""
    qa = [_e(str(i), i, zeit=30 + i * 0.1) for i in range(1, 26)]            # 25 Starter Agility
    # Jumping: 12 Starter, Teams '4' und '5' hier DIS (im Agility sauber Rang 4/5)
    qj = [(_e(str(i), None, dis="DIS") if i in (4, 5) else _e(str(i), i, zeit=31 + i * 0.1))
          for i in range(1, 13)]
    event = {"runs": [_run("qual_agility", "Large", qa), _run("qual_jumping", "Large", qj)],
             "sm_registered": {"Large": 60}, "sm_config": {}}
    cd = calculate_sm_qualification(event)["Large"]
    assert cd["direct_per_run_qa"] == 4     # ceil(25*0.16)
    assert cd["direct_per_run_qj"] == 2     # ceil(12*0.16)
    fin = {r["license"] for r in cd["final_list"]}
    assert "4" in fin                        # Agility-Rang 4 (DIS Jumping) → direkt drin
    assert "5" not in fin                    # Agility-Rang 5 (DIS Jumping) → draußen


def test_defending_champion_counts_into_final():
    """Titelverteidiger ist direkt gesetzt (zählt in die 40 %) und als is_defending markiert."""
    qa = [_e(str(i), i) for i in range(1, 21)]
    qj = [_e(str(i), i) for i in range(1, 21)]
    event = {"runs": [_run("qual_agility", "Large", qa), _run("qual_jumping", "Large", qj)],
             "sm_registered": {"Large": 30},
             "sm_config": {"Large": {"defending_champion": {"license": "7"}}}}
    cd = calculate_sm_qualification(event)["Large"]
    champ = next(r for r in cd["final_list"] if r["license"] == "7")
    assert champ["is_defending"] is True
