import math

from utils import _calculate_run_results


def pytest_approx(value, expected, tol=1e-6):
    """
    Kleine Approx-Hilfsfunktion, um Floats mit Toleranz zu vergleichen,
    ohne pytest.approx importieren zu müssen.
    """
    return abs(value - expected) <= tol


def test_sct_mct_rounding_class2_agility():
    """
    Klasse 2, Agility, Parcours 150m, Faktor 3.5:
    SCT = 150 / 3.5 = 42.857... -> gerundet 43
    MCT = 150 / 2.5 = 60 -> bleibt 60
    """
    run = {
        "klasse": "2",
        "laufart": "Agility",
        "laufdaten": {"parcours_laenge": "150"},
        "entries": []
    }
    settings = {"sct_factors": {"Agility": {"2": 3.5}}}

    results = _calculate_run_results(run, settings)
    assert isinstance(results, list)

    ld = run.get("laufdaten", {})
    sct_rounded = ld.get("standardzeit_sct_berechnet")
    mct_rounded = ld.get("maximalzeit_mct_berechnet")

    assert sct_rounded == math.ceil(150 / 3.5)
    assert mct_rounded == math.ceil(150 / 2.5)


def test_timefaults_use_rounded_sct():
    """
    Zeitfehler sollen mit ungerundeter Laufzeit, aber gerundeter SCT berechnet werden.
    Beispiel:
    - SCT_berechnet = 43
    - Laufzeit = 43.20
    -> fehler_zeit = 0.20
    """
    run = {
        "klasse": "2",
        "laufart": "Agility",
        "laufdaten": {"parcours_laenge": "150"},
        "entries": [
            {
                "lizenz": "A123",
                "zeit": "43.20",
                "fehler": "0",
                "verweigerungen": "0",
                "dis_abr": ""
            }
        ]
    }
    settings = {"sct_factors": {"Agility": {"2": 3.5}}}

    results = _calculate_run_results(run, settings)
    assert len(results) == 1
    entry = results[0]

    # Laufzeit bleibt ungerundet
    assert pytest_approx(entry["zeit_total"], 43.20)

    # SCT_rounded = 43 -> 43.20 - 43 = 0.20
    assert pytest_approx(entry["fehler_zeit"], 0.20)
    assert pytest_approx(entry["fehler_total"], 0.20)


def test_mct_exceed_sets_999():
    """
    Wenn die Laufzeit die MCT (gerundet) überschreitet, sollen die fehler_total = 999 sein.
    Beispiel:
    - MCT (150m Agility) = 60s
    - Laufzeit = 70s -> 999
    """
    run = {
        "klasse": "2",
        "laufart": "Agility",
        "laufdaten": {"parcours_laenge": "150"},
        "entries": [
            {
                "lizenz": "B999",
                "zeit": "70.00",
                "fehler": "0",
                "verweigerungen": "0",
                "dis_abr": ""
            }
        ]
    }
    settings = {"sct_factors": {"Agility": {"2": 3.5}}}

    results = _calculate_run_results(run, settings)
    assert len(results) == 1
    entry = results[0]

    assert entry["fehler_total"] == 999
    assert pytest_approx(entry["zeit_total"], 70.00)


def test_dis_abr_dns_handling():
    """
    DIS/ABR/DNS müssen korrekt als Spezialfälle behandelt werden,
    ohne Zeitfehlerberechnung.
    """
    run = {
        "klasse": "2",
        "laufart": "Agility",
        "laufdaten": {"parcours_laenge": "150"},
        "entries": [
            {"lizenz": "D1", "zeit": "", "fehler": "0", "verweigerungen": "0", "dis_abr": "DIS"},
            {"lizenz": "D2", "zeit": "", "fehler": "0", "verweigerungen": "0", "dis_abr": "ABR"},
            {"lizenz": "D3", "zeit": "", "fehler": "0", "verweigerungen": "0", "dis_abr": "DNS"},
        ]
    }
    settings = {"sct_factors": {"Agility": {"2": 3.5}}}

    results = _calculate_run_results(run, settings)
    assert len(results) == 3

    for entry in results:
        # Je nach Implementierung kann qualifikation oder fehler_total speziell gesetzt sein,
        # aber es darf kein Crash passieren und die Einträge müssen zurückgegeben werden.
        assert "lizenz" in entry


def test_empty_values_do_not_crash():
    """
    Leere Felder für Parcourslänge, Standardzeit, Geschwindigkeit dürfen keinen Crash erzeugen.
    """
    run = {
        "klasse": "1",
        "laufart": "Agility",
        "laufdaten": {
            "parcours_laenge": "",
            "standardzeit_sct": "",
            "geschwindigkeit": ""
        },
        "entries": []
    }
    settings = {}

    results = _calculate_run_results(run, settings)
    assert isinstance(results, list)
