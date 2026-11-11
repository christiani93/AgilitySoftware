"""
SWG-W-09 / Reglement Agility §5: Einzellauf-Klassierung nach
(1) Gesamtfehler, (2) weniger Parcoursfehler, (3) bessere Laufzeit; bei
Gleichstand aller drei Werte gleicher Rang mit übersprungenen Folgerängen.
"""
from utils import _calculate_run_results


def _run(entries):
    # Klasse 1 mit fixer Standardzeit 40 → Zeitfehler deterministisch.
    return {"laufart": "Agility", "kategorie": "Large", "klasse": "1",
            "laufdaten": {"standardzeit_sct": 40, "parcours_laenge": 100},
            "entries": entries}


def _e(lic, zeit, fehler=0, verw=0):
    return {"Lizenznummer": lic,
            "result": {"zeit": zeit, "fehler": fehler, "verweigerungen": verw}}


def _platz(results, lic):
    return next(r["platz"] for r in results if r["Lizenznummer"] == lic)


def test_parcoursfehler_tiebreaker_beats_time():
    # Beide Gesamtfehler 10: A rein über Zeitfehler (0 Parcoursfehler, zeit 50),
    # B über Parcoursfehler (2 Fehler = 10 Pkt, zeit 38). A hat weniger
    # Parcoursfehler → A vor B, obwohl A die schlechtere Zeit hat.
    res = _calculate_run_results(_run([_e("B", 38, fehler=2), _e("A", 50)]), {})
    assert _platz(res, "A") == 1
    assert _platz(res, "B") == 2


def test_ex_aequo_same_rank_and_skip():
    # A zeit37 (Platz1), B+C identisch zeit38 (Platz2+2), D zeit39 (Platz4).
    res = _calculate_run_results(
        _run([_e("D", 39), _e("B", 38), _e("A", 37), _e("C", 38)]), {})
    assert _platz(res, "A") == 1
    assert _platz(res, "B") == 2
    assert _platz(res, "C") == 2
    assert _platz(res, "D") == 4


def test_clean_run_beats_time_faults():
    # Fehlerfrei (zeit38, total0) vor Zeitfehler (zeit45, total5).
    res = _calculate_run_results(_run([_e("slow", 45), _e("clean", 38)]), {})
    assert _platz(res, "clean") == 1
    assert _platz(res, "slow") == 2


def test_dis_gets_no_platz():
    entries = [_e("ok", 38), {"Lizenznummer": "dis",
               "result": {"zeit": 38, "disqualifikation": "DIS"}}]
    res = _calculate_run_results(_run(entries), {})
    assert _platz(res, "ok") == 1
    dis = next(r for r in res if r["Lizenznummer"] == "dis")
    assert "platz" not in dis


def test_refusals_count_as_parcoursfehler():
    # Gleicher Gesamtfehler 5: A mit 1 Verweigerung (Parcoursfehler 5, zeit 40),
    # B rein über Zeit (0 Parcoursfehler, zeit 45). B hat weniger Parcoursfehler
    # → B vor A (Verweigerungen zählen als Parcoursfehler).
    res = _calculate_run_results(_run([_e("A", 40, verw=1), _e("B", 45)]), {})
    assert _platz(res, "B") == 1
    assert _platz(res, "A") == 2
