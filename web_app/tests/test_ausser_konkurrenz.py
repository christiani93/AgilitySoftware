"""
„Weisser Hund" / ausser Konkurrenz (`entry["ausser_konkurrenz"]`).

Ein so markierter Hund läuft mit und wird gemessen, darf aber die NORMALE
Lauf-Rangliste nicht beeinflussen:
  (a) er erhält keinen `platz` und verschiebt die Nummerierung der Gewerteten nicht,
  (b) er zählt nicht für die Standardzeit-Basis des normalen Laufs.
Sein Ergebnis (zeit_total/fehler_total) wird trotzdem berechnet, damit die
FMBB-Quali-Auswertung es nutzen kann (L2 läuft bei L3 als weisser Hund).
"""
from utils import _calculate_run_results


def test_weisser_hund_bekommt_keinen_platz_und_stoert_rangliste_nicht():
    # Kl.1: SCT fix 40 → deterministisch. W wäre mit 30s der Schnellste,
    # ist aber ausser Konkurrenz → kein Platz; A/B/C bleiben 1/2/3.
    run = {
        "klasse": "1",
        "laufart": "Agility",
        "laufdaten": {"standardzeit_sct": "40"},
        "entries": [
            {"lizenz": "A", "zeit": "39.0"},
            {"lizenz": "B", "zeit": "41.0"},
            {"lizenz": "C", "zeit": "43.0"},
            {"lizenz": "W", "zeit": "30.0", "ausser_konkurrenz": True},
        ],
    }
    results = _calculate_run_results(run, {})
    res = {r["lizenz"]: r for r in results}

    # Normale Hunde: lückenlose Plätze 1/2/3 (W verschiebt nichts).
    assert res["A"]["platz"] == 1
    assert res["B"]["platz"] == 2
    assert res["C"]["platz"] == 3
    # Weisser Hund: kein Platz.
    assert res["W"]["platz"] is None
    # Ergebnis trotzdem berechnet (für die FMBB-Wertung nutzbar).
    assert res["W"]["zeit_total"] == 30.0
    assert res["W"]["fehler_total"] == 0  # 30s < SCT 40 → kein Zeitfehler


def test_weisser_hund_zaehlt_nicht_fuer_sct_basis():
    # Kl.3 Agility, Parcours 100m. Normale Basis = schnellster gewerteter Hund (30s),
    # SCT = ceil(30 * 1.3) = 39. Der weisse Hund mit 20s dürfte die Basis NICHT
    # auf 20 (→ SCT 26) drücken.
    run = {
        "klasse": "3",
        "laufart": "Agility",
        "laufdaten": {"parcours_laenge": "100"},
        "entries": [
            {"lizenz": "N1", "zeit": "30.0"},
            {"lizenz": "N2", "zeit": "32.0"},
            {"lizenz": "W", "zeit": "20.0", "ausser_konkurrenz": True},
        ],
    }
    results = _calculate_run_results(run, {})
    laufdaten = run["laufdaten"]
    res = {r["lizenz"]: r for r in results}

    # SCT aus den gewerteten Hunden (30s), nicht aus dem weissen Hund (20s).
    assert laufdaten["standardzeit_sct_berechnet"] == 39
    # Gewertete Rangfolge unberührt.
    assert res["N1"]["platz"] == 1
    assert res["N2"]["platz"] == 2
    # Weisser Hund: kein Platz, aber Ergebnis vorhanden.
    assert res["W"]["platz"] is None
    assert res["W"]["zeit_total"] == 20.0


def test_ohne_flag_unveraendertes_verhalten():
    # Regression: ohne ausser_konkurrenz zählt der schnellste Hund normal.
    run = {
        "klasse": "1",
        "laufart": "Agility",
        "laufdaten": {"standardzeit_sct": "40"},
        "entries": [
            {"lizenz": "A", "zeit": "39.0"},
            {"lizenz": "B", "zeit": "41.0"},
            {"lizenz": "FAST", "zeit": "30.0"},
        ],
    }
    results = _calculate_run_results(run, {})
    res = {r["lizenz"]: r for r in results}
    assert res["FAST"]["platz"] == 1
    assert res["A"]["platz"] == 2
    assert res["B"]["platz"] == 3
