"""Regressionstests für die TKAMO-SM-Qualifikation (sm_qualification.py),
abgeleitet aus der Validierung gegen die TKAMO-SM-2024-Echtdaten:

  Fix 1: `starters` = alle GESTARTETEN (inkl. DIS), nur DNS zählt nicht
         (0.4·Gestartete reproduziert das reale Finalfeld; nicht-DIS wäre zu klein).
  Fix 2: Direktqualifizierte (Top 16 % je Lauf nach Rang) zählen auch dann, wenn sie
         im ANDEREN Lauf disqualifiziert sind — nur die Kombi-Nachrücker brauchen beide
         Läufe sauber.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "web_app"))

from sm_qualification import calculate_sm_qualification  # noqa: E402


def _clean(lic, platz, zeit):
    return {"Lizenznummer": lic, "Hundename": f"D{lic}", "Vorname": "V", "Nachname": lic,
            "fehler_total": 0, "fehler_parcours": 0, "zeit_total": zeit,
            "platz": platz, "disqualifikation": ""}


def _dis(lic, status="DIS"):
    return {"Lizenznummer": lic, "Hundename": f"D{lic}", "Vorname": "V", "Nachname": lic,
            "fehler_total": 999, "fehler_parcours": 0, "zeit_total": 999.99,
            "platz": None, "disqualifikation": status}


def _event(agility_entries, jumping_entries):
    return {"runs": [
        {"kategorie": "Large", "klasse": "3", "laufart": "Agility",
         "sm_run_type": "qual_agility", "entries": agility_entries},
        {"kategorie": "Large", "klasse": "3", "laufart": "Jumping",
         "sm_run_type": "qual_jumping", "entries": jumping_entries},
    ]}


def test_starters_counts_dis_but_not_dns():
    # 7 gestartete (A–G; G in Agility DIS), + ein DNS-Hund Z (zählt NICHT).
    agility = [_clean(c, i + 1, 30 + i) for i, c in enumerate("ABCDEF")] + [_dis("G")] + [_dis("Z", "DNS")]
    jumping = [_clean(c, i + 1, 30 + i) for i, c in enumerate("ACDEF")] + [_dis("B")] + [_clean("G", 6, 40)]
    out = calculate_sm_qualification(_event(agility, jumping))["Large"]
    assert out["starters"] == 7            # A–G; DNS-Hund Z ausgeschlossen
    assert out["final_spots"] == 10        # max(10, ceil(7*0.4))


def test_direct_qualifier_counts_despite_dis_in_other_run():
    # B ist in Agility Rang 2 (Top-16%-Direkt), im Jumping aber DIS → muss trotzdem
    # im Finale sein (Fix 2). Ohne Fix flöge B als kombi_dis raus.
    agility = [_clean(c, i + 1, 30 + i) for i, c in enumerate("ABCDEF")] + [_dis("G")]
    jumping = [_clean(c, i + 1, 30 + i) for i, c in enumerate("ACDEF")] + [_dis("B")] + [_clean("G", 6, 40)]
    out = calculate_sm_qualification(_event(agility, jumping))["Large"]
    final_lics = {r["license"] for r in out["final_list"]}
    assert "B" in final_lics
    # B ist als Direkt-Qualifizierter markiert (nicht als Kombi-Nachrücker).
    b = next(r for r in out["final_list"] if r["license"] == "B")
    assert b["is_direct"] is True


def test_kombi_nachruecker_require_both_runs_clean():
    # Ein Hund H nur in Agility sauber (kein Jumping-Ergebnis) ist KEIN Kombi-Nachrücker,
    # solange er nicht direkt qualifiziert ist.
    agility = [_clean(c, i + 1, 30 + i) for i, c in enumerate("ABCDEFGHIJKL")]
    jumping = [_clean(c, i + 1, 30 + i) for i, c in enumerate("ABCDEFGIJKL")] + [_dis("H")]
    out = calculate_sm_qualification(_event(agility, jumping))["Large"]
    h = next((r for r in out["final_list"] if r["license"] == "H"), None)
    # H ist Agility-Rang 8 (nicht Top-16% bei 12 Startern → direct_per_run=2), im Jumping DIS.
    # Als Nicht-Direkter mit kombi_dis darf er NICHT über die Kombi-Rangliste nachrücken.
    assert h is None
