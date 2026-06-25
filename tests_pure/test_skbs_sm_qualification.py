"""
Pure-Python-Tests für SKBS-SM-Qualifikations-Service.

Edge Cases:
- Quote: 20% bei verschiedenen Teilnehmerzahlen, min-3-Schwelle
- Doppelqualifikation: Hund qualifiziert sich aus Agi + Jump
- Nachrücken: aus 2. Lauf → Klasse 3 → 2 → 1, max 10 FP
- Titelverteidiger: gilt qualifiziert, nimmt keinen direkten Slot weg
- Final-Tiebreaker: 3-stufig + ex aequo
- DIS/Nicht-Platzierte werden nicht qualifiziert
"""
import math
import os
import sys

# web_app importierbar machen
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
WEB_APP_PATH = os.path.join(PROJECT_ROOT, "web_app")
if WEB_APP_PATH not in sys.path:
    sys.path.insert(0, WEB_APP_PATH)

from skbs_sm_qualification import (   # noqa: E402
    calculate_skbs_sm_qualification,
    rank_final,
    _quota,
    MAX_NACHRUECK_FAULTS,
)


# ---------------------------------------------------------------------------
# Helpers — Test-Fixtures
# ---------------------------------------------------------------------------

def _entry(license_no, rang, fehler_total=0, fehler_parcours=0, zeit_total=40.0, dis=None):
    """Baut einen entry-Dict im AgilitySoftware-Format."""
    e = {
        "Lizenznummer":   license_no,
        "Hundename":      f"Hund_{license_no}",
        "Vorname":        "Max",
        "Nachname":       f"Muster_{license_no}",
        "platz":          rang,
        "fehler_total":   fehler_total,
        "fehler_parcours":fehler_parcours,
        "zeit_total":     zeit_total,
    }
    if dis:
        e["disqualifikation"] = dis
        e["fehler_total"] = 999
        e["platz"] = None
    return e


def _run(klasse, laufart, entries, is_final=False):
    return {
        "kategorie": "Large",
        "klasse":    klasse,
        "laufart":   laufart,
        "is_final":  is_final,
        "entries":   entries,
    }


# ---------------------------------------------------------------------------
# Tests Quote-Berechnung
# ---------------------------------------------------------------------------

def test_quote_min3_bei_wenigen_startern():
    # 0 Starter → 0
    assert _quota(0) == 0
    # 1 Starter → 3 (min 3, aber Quote rundet auf — hier greift min)
    assert _quota(1) == 3
    # 10 Starter → max(3, ceil(2)) = 3
    assert _quota(10) == 3
    # 14 Starter → max(3, ceil(2.8)) = 3
    assert _quota(14) == 3
    # 15 Starter → max(3, ceil(3.0)) = 3
    assert _quota(15) == 3


def test_quote_20pct_bei_vielen_startern():
    # 20 Starter → max(3, ceil(4)) = 4
    assert _quota(20) == 4
    # 25 Starter → max(3, ceil(5)) = 5
    assert _quota(25) == 5
    # 50 Starter → max(3, ceil(10)) = 10
    assert _quota(50) == 10
    # 51 Starter → ceil(10.2) = 11
    assert _quota(51) == 11


# ---------------------------------------------------------------------------
# Tests Hauptfunktion
# ---------------------------------------------------------------------------

def test_einfache_klasse3_quali_ohne_doppelqualifikation():
    """3 Teams in Klasse 3 Agi + Jump, alle unterschiedliche Lizenzen, keine Überschneidung."""
    event = {
        "runs": [
            _run("3", "Agility", [
                _entry("A", rang=1, fehler_total=0, zeit_total=35.0),
                _entry("B", rang=2, fehler_total=5, zeit_total=36.0),
                _entry("C", rang=3, fehler_total=10, zeit_total=37.0),
            ]),
            _run("3", "Jumping", [
                _entry("D", rang=1, fehler_total=0, zeit_total=25.0),
                _entry("E", rang=2, fehler_total=5, zeit_total=26.0),
                _entry("F", rang=3, fehler_total=10, zeit_total=27.0),
            ]),
        ],
    }
    result = calculate_skbs_sm_qualification(event)

    # 3 Starter pro Lauf → Quote = 3 (min)
    assert result["per_class"]["3"]["qa_quota"] == 3
    assert result["per_class"]["3"]["qj_quota"] == 3

    # Alle 6 sollten finalisiert sein (keine Doppelqualifikation)
    licenses = {f["license"] for f in result["finalists"]}
    assert licenses == {"A", "B", "C", "D", "E", "F"}
    assert result["open_spots"] == 0


def test_doppelqualifikation_loest_nachruecken_aus():
    """A qualifiziert sich in Agi+Jump Klasse 3 → Slot in Jump wird vom nächsten gefüllt."""
    event = {
        "runs": [
            _run("3", "Agility", [
                _entry("A", rang=1, fehler_total=0, zeit_total=35.0),
                _entry("B", rang=2, fehler_total=5, zeit_total=36.0),
                _entry("C", rang=3, fehler_total=10, zeit_total=37.0),
            ]),
            _run("3", "Jumping", [
                _entry("A", rang=1, fehler_total=0, zeit_total=25.0),   # doppelt
                _entry("D", rang=2, fehler_total=5, zeit_total=26.0),
                _entry("E", rang=3, fehler_total=8, zeit_total=27.0),
                _entry("F", rang=4, fehler_total=9, zeit_total=28.0),   # Nachrücker?
                _entry("G", rang=5, fehler_total=12, zeit_total=29.0),  # >10 FP, NICHT
            ]),
        ],
    }
    result = calculate_skbs_sm_qualification(event)

    licenses = [f["license"] for f in result["finalists"]]
    # A nur 1x, B/C aus Agi, D/E aus Jump → 5 direkte Plätze + 1 Nachrücker (F)
    assert licenses.count("A") == 1
    assert set(licenses[:5]) == {"A", "B", "C", "D", "E"}
    # Nachrücker: F (9 FP ≤ 10), G nicht (12 FP > 10)
    assert "F" in licenses
    assert "G" not in licenses
    # Slot bleibt offen (kein weiterer Nachrücker mit ≤10 FP)
    assert result["open_spots"] == 0  # F hat den offenen Slot gefüllt


def test_nachruecken_aus_klasse_2_max_10_fp():
    """K3 voll doppelqualifiziert → Lücken werden mit K2-Kandidaten (≤10 FP) gefüllt.

    K2 hat eigene Direkt-Quote (laut Reglement "pro Klasse"); Nachrück-Kandidaten
    sind diejenigen, die NICHT in der K2-Direktquote sind. Die 10-FP-Grenze
    gilt nur für Nachrücker, nicht für Direkt-Qualifizierte.
    """
    event = {
        "runs": [
            # K3 Agi: A, B, C direkt qualifiziert (Quote=3 min)
            _run("3", "Agility", [
                _entry("A", rang=1, fehler_total=0),
                _entry("B", rang=2, fehler_total=3),
                _entry("C", rang=3, fehler_total=5),
            ]),
            # K3 Jump: dieselben A, B, C → komplett doppelqualifiziert → 3 K3-Lücken
            _run("3", "Jumping", [
                _entry("A", rang=1, fehler_total=0),
                _entry("B", rang=2, fehler_total=2),
                _entry("C", rang=3, fehler_total=4),
            ]),
            # K2 Agi: 3 direkt qualifiziert + 1 Nachrück-Kandidat (≤10) + 1 (>10)
            _run("2", "Agility", [
                _entry("K2A", rang=1, fehler_total=2),    # direkt
                _entry("K2B", rang=2, fehler_total=4),    # direkt
                _entry("K2C", rang=3, fehler_total=6),    # direkt
                _entry("K2D", rang=4, fehler_total=8),    # Nachrücker (≤10)
                _entry("K2E", rang=5, fehler_total=15),   # KEIN Nachrücker (>10)
            ]),
        ],
    }
    result = calculate_skbs_sm_qualification(event)

    licenses = [f["license"] for f in result["finalists"]]
    # K3 direkt: A, B, C
    assert {"A", "B", "C"}.issubset(set(licenses))
    # K2 direkt: K2A, K2B, K2C (Quote=3, alle Top-3)
    assert {"K2A", "K2B", "K2C"}.issubset(set(licenses))
    # K2 Nachrücker: K2D (8 FP ≤10) füllt eine K3-Lücke
    assert "K2D" in licenses
    # K2E NICHT (15 FP > 10)
    assert "K2E" not in licenses
    # K2D-Source ist "nachruecker", nicht "agility"
    k2d_entry = next(f for f in result["finalists"] if f["license"] == "K2D")
    assert k2d_entry["source"] == "nachruecker"
    assert k2d_entry["from_class"] == 2
    # 2 K3-Lücken bleiben offen (K2 hatte nur 1 nachrückfähigen Kandidaten;
    # keine K1-Läufe vorhanden, also können diese nicht gefüllt werden)
    assert result["open_spots"] == 2


def test_titelverteidiger_zusaetzlich_qualifiziert():
    """Defending Champion zählt extra (auch wenn er nicht Top 20% wäre)."""
    event = {
        "runs": [
            _run("3", "Agility", [
                _entry("A", rang=1, fehler_total=0),
                _entry("B", rang=2, fehler_total=5),
                _entry("C", rang=3, fehler_total=10),
                _entry("CHAMP", rang=99, fehler_total=15),   # wäre nicht qualifiziert
            ]),
            _run("3", "Jumping", [
                _entry("CHAMP", rang=50, fehler_total=20),   # gestartet → eligible
            ]),
        ],
        "skbs_sm_config": {
            "defending_champion": {
                "license":      "CHAMP",
                "dog_name":     "Vorjahres-Hund",
                "handler_name": "Vorjahres-HF",
            },
        },
    }
    result = calculate_skbs_sm_qualification(event)

    licenses = {f["license"] for f in result["finalists"]}
    assert "CHAMP" in licenses

    # CHAMP-Eintrag hat source title_defender
    champ_entry = next(f for f in result["finalists"] if f["license"] == "CHAMP")
    assert champ_entry["source"] == "title_defender"


def test_titelverteidiger_nicht_eligible_wenn_nicht_gestartet():
    """CHAMP ohne Start in irgendeinem Quali-Lauf wird NICHT qualifiziert."""
    event = {
        "runs": [
            _run("3", "Agility", [_entry("A", rang=1)]),
        ],
        "skbs_sm_config": {
            "defending_champion": {
                "license":      "CHAMP_ABSENT",
                "dog_name":     "Vorjahres-Hund",
                "handler_name": "Vorjahres-HF",
            },
        },
    }
    result = calculate_skbs_sm_qualification(event)

    licenses = {f["license"] for f in result["finalists"]}
    assert "CHAMP_ABSENT" not in licenses


def test_dis_nicht_qualifiziert():
    """DIS-Teams sind auch nicht als Nachrücker qualifizierbar."""
    event = {
        "runs": [
            _run("3", "Agility", [
                _entry("A", rang=1, fehler_total=0),
                _entry("DIS_DOG", rang=None, dis="DIS"),
            ]),
        ],
    }
    result = calculate_skbs_sm_qualification(event)

    licenses = {f["license"] for f in result["finalists"]}
    assert "A" in licenses
    assert "DIS_DOG" not in licenses


# ---------------------------------------------------------------------------
# Final-Rangierung Tests
# ---------------------------------------------------------------------------

def test_final_rangierung_tiebreaker_gesamt_parcours_zeit():
    """3-stufiger Tiebreaker: Gesamt-FP → Parcours-FP → Zeit."""
    event = {
        "runs": [
            _run("3", "Agility", [
                _entry("X", rang=1, fehler_total=0, fehler_parcours=0, zeit_total=30.0),
                _entry("Y", rang=2, fehler_total=0, fehler_parcours=0, zeit_total=32.0),
                _entry("Z", rang=3, fehler_total=5, fehler_parcours=5, zeit_total=29.0),
                _entry("W", rang=4, fehler_total=5, fehler_parcours=3, zeit_total=33.0),
            ], is_final=True),
        ],
    }
    final = rank_final(event)
    order = [r["license"] for r in final]
    # X: 0 FP, 30s → rang 1
    # Y: 0 FP, 32s → rang 2
    # W: 5 FP, 3 Parcours → vor Z (5 Parcours)
    # Z: 5 FP, 5 Parcours
    assert order == ["X", "Y", "W", "Z"]
    assert final[0]["final_rang"] == 1
    assert final[1]["final_rang"] == 2
    assert final[2]["final_rang"] == 3
    assert final[3]["final_rang"] == 4


def test_final_ex_aequo_bei_voller_gleichheit():
    """Komplett identische Werte → gleicher Rang."""
    event = {
        "runs": [
            _run("3", "Agility", [
                _entry("P", rang=1, fehler_total=5, fehler_parcours=5, zeit_total=30.0),
                _entry("Q", rang=2, fehler_total=5, fehler_parcours=5, zeit_total=30.0),
                _entry("R", rang=3, fehler_total=10, fehler_parcours=10, zeit_total=35.0),
            ], is_final=True),
        ],
    }
    final = rank_final(event)
    # P und Q sind identisch → beide rang 1; R kommt auf rang 3 (nicht 2!)
    assert final[0]["final_rang"] == 1
    assert final[1]["final_rang"] == 1
    assert final[2]["final_rang"] == 3


def test_final_dis_kommen_ans_ende_ohne_rang():
    event = {
        "runs": [
            _run("3", "Agility", [
                _entry("A", rang=1, fehler_total=0),
                _entry("DIS_TEAM", rang=None, dis="DIS"),
            ], is_final=True),
        ],
    }
    final = rank_final(event)
    assert final[0]["license"] == "A"
    assert final[0]["final_rang"] == 1
    assert final[-1]["license"] == "DIS_TEAM"
    assert final[-1]["final_rang"] is None


def test_final_ohne_final_lauf_gibt_leere_liste():
    """Wenn kein is_final-Lauf existiert: leeres Resultat."""
    event = {
        "runs": [
            _run("3", "Agility", [_entry("A", rang=1)]),  # nur Quali
        ],
    }
    assert rank_final(event) == []
